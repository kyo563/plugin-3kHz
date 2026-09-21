"""Opt-in YouTube announcements. Reception continues through OneComme only."""
import base64
import ctypes
from ctypes import wintypes
from collections import OrderedDict, deque
from contextlib import contextmanager
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import math
from pathlib import Path
import re
import secrets
import sqlite3
from threading import Event, RLock, Thread
import time
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx
from pydantic import BaseModel, Field, field_validator
from app.services.user_identity_service import UserIdentityService

SCOPE = 'https://www.googleapis.com/auth/youtube.force-ssl'
DEFAULT_GUIDE = '参加希望とコメントしてください。ゲーム内の名前が異なる場合は「参加希望 『名前』」。待機中の辞退は「参加辞退」。'


class BotSettings(BaseModel):
    enabled: bool = False
    announce_now: bool = True
    reply_position: bool = True
    periodic: bool = True
    interval_minutes: int = 10
    guide: str = Field(default=DEFAULT_GUIDE, min_length=1, max_length=200)

    @field_validator('interval_minutes')
    @classmethod
    def interval(cls, v):
        if v not in (10, 30):
            raise ValueError('10分または30分を指定してください')
        return v

    @field_validator('guide')
    @classmethod
    def guide_text(cls, v):
        if not v.strip():
            raise ValueError('参加方法を入力してください')
        return ' '.join(v.split())


def protect(data: bytes, decrypt=False) -> bytes:
    """Windows user-bound DPAPI. Never fall back to plaintext."""
    class Blob(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_char))]
    buf = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    output = Blob()
    crypt = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    func = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    func.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                     ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    func.restype = wintypes.BOOL
    if not func(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(output)):
        raise ValueError('Windowsの認証情報保護を利用できません')
    try:
        return ctypes.string_at(output.data, output.size)
    finally:
        kernel.LocalFree(output.data)


class BotStore:
    def __init__(self, path):
        self.path = str(path)
        with self.connection() as c:
            c.execute('CREATE TABLE IF NOT EXISTS bot_data (key TEXT PRIMARY KEY, value BLOB NOT NULL)')

    @contextmanager
    def connection(self):
        connection = sqlite3.connect(self.path, timeout=5)
        connection.execute('PRAGMA secure_delete=ON')
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def read(self, key, default=None):
        with self.connection() as c:
            row = c.execute('SELECT value FROM bot_data WHERE key=?', (key,)).fetchone()
        if not row:
            return default
        raw = protect(row[0], True) if key == 'credentials' else row[0]
        return json.loads(raw)

    def write(self, key, value):
        raw = json.dumps(value, ensure_ascii=False).encode('utf8')
        if key == 'credentials':
            raw = protect(raw)
        with self.connection() as c:
            c.execute('INSERT OR REPLACE INTO bot_data VALUES (?,?)', (key, raw))

    def forget_credentials(self):
        with self.connection() as c:
            c.execute('DELETE FROM bot_data WHERE key=?', ('credentials',))

    def save_connection(self, credentials, account):
        encrypted = protect(json.dumps(credentials).encode('utf8'))
        with self.connection() as c:
            c.execute('INSERT OR REPLACE INTO bot_data VALUES (?,?)', ('credentials', encrypted))
            c.execute('INSERT OR REPLACE INTO bot_data VALUES (?,?)', ('account', json.dumps(account).encode('utf8')))


class AnnouncementBot:
    def __init__(self, services, bridge, store, *, client=None, clock=time.monotonic):
        self.services, self.bridge, self.store = services, bridge, store
        self.clock = clock
        self.http = client or httpx.Client(timeout=10, trust_env=False)
        self.lock, self.stopped = RLock(), Event()
        self.settings = BotSettings(**(store.read('settings', {}) or {}))
        self.account = store.read('account', {}) or {}
        self.credentials = None
        self.error = ''
        try:
            self.credentials = store.read('credentials')
        except Exception:
            self.error = '保存したログイン情報を開けません。再接続してください。'
        self.queue = deque(maxlen=100)
        self.seen, self.reply_times = OrderedDict(), OrderedDict()
        self.last_sent = -100.0
        self.next_guide = self.clock() + self.settings.interval_minutes * 60
        self.last_frame = ''
        self.chat_id = ''
        self.token = ''
        self.expires = 0
        self.retry_after = 0
        self.last_result = ''
        self.generation = 0
        self.auth_server = None
        self.auth_pending = None
        self.auth_thread = None
        self.now_events = OrderedDict()
        self.thread = None
        self.initial_announced = False

    def start(self):
        self.thread = Thread(target=self._run, daemon=True, name='queue-bot')
        self.thread.start()

    def stop(self):
        self.stopped.set()
        with self.lock:
            self.generation += 1
            self.queue.clear()
            self.auth_pending = None
        if self.thread:
            self.thread.join(timeout=12)
        if self.auth_thread:
            self.auth_thread.join(timeout=22)
        self.http.close()

    def status(self):
        with self.lock:
            return {'settings': self.settings.model_dump(), 'account': dict(self.account),
                    'authenticated': bool(self.credentials),
                    'ready': bool(self.settings.enabled and self.credentials and self.chat_id and not self.error),
                    'error': self.error, 'last_result': self.last_result,
                    'pending': len(self.queue), 'login_pending': self.auth_pending is not None,
                    'needs_setup': not self.account}

    def configure(self, settings):
        with self.lock:
            self.store.write('settings', settings.model_dump())
            self.settings = settings
            self.generation += 1
            self.queue.clear()
            self.next_guide = self.clock() + settings.interval_minutes * 60
            self.retry_after = 0
            self.error = ''
        return self.status()

    def disconnect(self):
        with self.lock:
            self.store.forget_credentials()
            self.credentials = None
            self.token = self.chat_id = ''
            self.auth_pending = None
            self.generation += 1
            self.queue.clear()
            self.error = ''
            # Keep the channel ID excluded even when posting is disabled.
        return self.status()

    def is_self(self, comment):
        return comment.source == 'youtube' and comment.user_key == self.account.get('id')

    def _enqueue(self, kind, data):
        with self.lock:
            if not self.settings.enabled or not self.credentials:
                return
            frame = self.bridge.selected
            if frame:
                self.queue.append((self.clock(), self.generation, frame, kind, data))

    def announce(self):
        state = self.services.build_view_state()
        current = state['current']
        ids = tuple(u['user_id'] for u in current)
        if ids:
            with self.lock:
                key = (self.bridge.selected, state.get('total_match_count', 0), ids)
                self.initial_announced = True
                if key in self.now_events:
                    return
                self.now_events[key] = True
                while len(self.now_events) > 1000:
                    self.now_events.popitem(last=False)
                self._enqueue('now', ids)

    def receive(self, comment):
        """True consumes a bot query before join/leave command detection."""
        if self.is_self(comment):
            return True
        handle = self.account.get('handle', '')
        if not handle.startswith('@') or not re.search(r'(?<![\w@])' + re.escape(handle) + r'(?![\w.-])', comment.message, re.I):
            return False
        with self.lock:
            if not self.settings.enabled or not self.settings.reply_position:
                return False
            key = comment.external_message_id
            now = self.clock()
            if key in self.seen:
                return True
            self.seen[key] = now
            while len(self.seen) > 2000:
                self.seen.popitem(last=False)
            uid = comment.user_key
            if now - self.reply_times.get(uid, -100) < 30:
                return True
            self.reply_times[uid] = now
            while len(self.reply_times) > 1000:
                self.reply_times.popitem(last=False)
            self._enqueue('position', (uid, comment.youtube_handle or comment.display_name))
            return True

    def _message(self, kind, data):
        state = self.services.build_view_state()
        def name(u):
            return ' '.join(str(u.get('declared_player_name') or u.get('youtube_handle') or u.get('display_name') or '参加者').split())[:40]
        if kind == 'guide':
            return self.settings.guide if self.settings.periodic and state.get('is_open') else None
        if kind == 'now':
            if not self.settings.announce_now or tuple(u['user_id'] for u in state['current']) != data:
                return None
            return '、'.join(name(u) + 'さん' for u in state['current']) + ' 入室お願いします'
        if not self.settings.reply_position:
            return None
        uid, display = data
        identity = UserIdentityService().build_comment_user_id('youtube', uid)
        mention = '@' + ' '.join(display.lstrip('@').split())[:50] + 'さん'
        if any(u['user_id'] == identity for u in state['current']):
            return mention + 'は現在NOWの対局メンバーです'
        for i, u in enumerate(state['waiting'], 1):
            if u['user_id'] == identity:
                return f'{mention}は{i}番目/第{math.ceil(i / 3)}グループです'
        return mention + 'は現在待機列に登録されていません'

    def _request(self, method, url, **kwargs):
        if self.stopped.is_set():
            raise ValueError('Botを停止しました')
        r = self.http.request(method, url, **kwargs)
        if r.status_code >= 400:
            raise ValueError(f'YouTubeへの接続に失敗しました（HTTP {r.status_code}）。ログイン・配信状態・API利用上限を確認してください。')
        return r.json()

    def _access_token(self):
        if self.token and self.clock() < self.expires:
            return self.token
        c = self.credentials
        generation = self.generation
        if not c:
            raise ValueError('Bot専用アカウントでログインしてください')
        result = self._request('POST', 'https://oauth2.googleapis.com/token', data={
            'client_id': c['client_id'], 'client_secret': c['client_secret'],
            'refresh_token': c['refresh_token'], 'grant_type': 'refresh_token'})
        with self.lock:
            if generation != self.generation or c is not self.credentials or self.stopped.is_set():
                raise ValueError('接続設定が変更されました')
            self.token = result['access_token']
            self.expires = self.clock() + max(0, int(result.get('expires_in', 300)) - 60)
            return self.token

    def tick(self):
        bridge = self.bridge.snapshot()
        frame = bridge['selected']
        with self.lock:
            if frame != self.last_frame:
                self.last_frame = frame
                self.chat_id = ''
                self.queue.clear()
                self.initial_announced = False
                self.next_guide = self.clock() + self.settings.interval_minutes * 60
                self.retry_after = 0
            if not self.settings.enabled or not self.credentials or not frame or not bridge['connected']:
                self.chat_id = ''
                return
            generation = self.generation
        if self.clock() < self.retry_after:
            return
        if not re.fullmatch(r'[A-Za-z0-9_-]{11}', frame):
            raise ValueError('配信IDを確認できません。わんコメでYouTube配信を選び直してください。')
        headers = {'Authorization': 'Bearer ' + self._access_token()}
        if not self.chat_id:
            info = self._request('GET', 'https://www.googleapis.com/youtube/v3/videos',
                                 params={'part': 'liveStreamingDetails', 'id': frame}, headers=headers)
            items = info.get('items', [])
            chat_id = items[0].get('liveStreamingDetails', {}).get('activeLiveChatId') if items else None
            if not chat_id:
                raise ValueError('投稿先チャットを取得できません。配信中か、Botが閲覧できる配信か確認してください。')
            with self.lock:
                if generation != self.generation or self.bridge.selected != frame or self.stopped.is_set():
                    return
                self.chat_id = chat_id
                self.error = ''
        state = self.services.build_view_state()
        if not self.initial_announced and len(state['current']) == 3:
            self.announce()
        if self.clock() >= self.next_guide:
            self.next_guide = self.clock() + self.settings.interval_minutes * 60
            self._enqueue('guide', None)
        with self.lock:
            if not self.queue or self.clock() - self.last_sent < 5:
                return
            at, event_generation, target, kind, data = self.queue.popleft()
            if (event_generation != generation or generation != self.generation or target != frame
                    or self.clock() - at > 60 or self.bridge.selected != frame or self.stopped.is_set()):
                return
            message = self._message(kind, data)
            if not message:
                return
            self.last_sent = self.clock()
            chat_id = self.chat_id
        if generation != self.generation or self.bridge.selected != frame or self.stopped.is_set():
            return
        # No retries after an ambiguous response: avoid duplicate public posts.
        self._request('POST', 'https://www.googleapis.com/youtube/v3/liveChat/messages',
                      params={'part': 'snippet'}, headers=headers, json={'snippet': {
                          'liveChatId': chat_id, 'type': 'textMessageEvent',
                          'textMessageDetails': {'messageText': message[:200]}}})
        with self.lock:
            self.error = ''
            self.last_result = '投稿しました：' + message

    def _run(self):
        while not self.stopped.wait(1):
            try:
                self.tick()
            except Exception as exc:
                with self.lock:
                    self.error = str(exc) if isinstance(exc, ValueError) else '接続エラーです。1分後に接続を再確認します。'
                    self.retry_after = self.clock() + 60
                    self.chat_id = ''
                    self.queue.clear()

    def begin_login(self, document):
        installed = document.get('installed', {})
        client_id, secret = installed.get('client_id', ''), installed.get('client_secret', '')
        if not isinstance(client_id, str) or not client_id.endswith('.apps.googleusercontent.com') or not isinstance(secret, str) or not secret:
            raise ValueError('デスクトップアプリ用のOAuthクライアントJSONを選んでください')
        with self.lock:
            if self.auth_pending:
                raise ValueError('ログイン画面を開いています。完了または10分後に再試行してください')
            self.settings = self.settings.model_copy(update={'enabled': False})
            self.store.write('settings', self.settings.model_dump())
            self.generation += 1
            self.queue.clear()
            state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(48)
            self.auth_pending = state
            auth_generation = self.generation
        owner = self
        class Callback(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_GET(self):
                query = parse_qs(urlsplit(self.path).query)
                supplied = query.get('state', [''])[0]
                if urlsplit(self.path).path != '/callback' or not secrets.compare_digest(supplied, state):
                    self.send_error(400)
                    return
                with owner.lock:
                    valid = owner.auth_pending == state and not owner.stopped.is_set()
                    owner.auth_pending = None
                if not valid:
                    self.send_error(400)
                    return
                message = 'ログインできませんでした。管理画面から再試行してください。'
                try:
                    if query.get('error') or not query.get('code'):
                        raise ValueError('Googleログインがキャンセルされました')
                    token = owner._request('POST', 'https://oauth2.googleapis.com/token', data={
                        'client_id': client_id, 'client_secret': secret, 'code': query['code'][0],
                        'code_verifier': verifier, 'redirect_uri': redirect, 'grant_type': 'authorization_code'})
                    if not token.get('refresh_token'):
                        raise ValueError('再接続用の認証を取得できませんでした')
                    data = owner._request('GET', 'https://www.googleapis.com/youtube/v3/channels',
                        params={'part': 'snippet', 'mine': 'true'}, headers={'Authorization': 'Bearer ' + token['access_token']})
                    channel = data.get('items', [])[0]
                    account = {'id': channel['id'], 'name': channel['snippet']['title'],
                               'handle': channel['snippet'].get('customUrl', '')}
                    if not re.fullmatch(r'UC[A-Za-z0-9_-]{22}', account['id']):
                        raise ValueError('YouTubeチャンネルを確認できません')
                    with owner.lock:
                        if owner.generation != auth_generation or owner.stopped.is_set():
                            raise ValueError('接続処理が取り消されました')
                        credentials = {'client_id': client_id, 'client_secret': secret, 'refresh_token': token['refresh_token']}
                        owner.store.save_connection(credentials, account)
                        owner.credentials, owner.account = credentials, account
                        owner.token = ''
                        owner.chat_id = ''
                        owner.generation += 1
                        owner.error = ''
                        owner.retry_after = 0
                    message = '接続できました。この画面を閉じて管理画面でBotを有効にしてください。'
                except Exception:
                    with owner.lock:
                        owner.error = message
                body = message.encode('utf8')
                self.send_response(200)
                self.send_header('Content-Type', 'text/plain; charset=utf-8')
                self.send_header('Cache-Control', 'no-store')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
        class LocalCallbackServer(HTTPServer):
            def get_request(self):
                connection, address = super().get_request()
                connection.settimeout(5)
                return connection, address
        server = LocalCallbackServer(('127.0.0.1', 0), Callback)
        server.timeout = 1
        self.auth_server = server
        redirect = f'http://127.0.0.1:{server.server_port}/callback'
        def listen():
            deadline = time.monotonic() + 600
            try:
                while not self.stopped.is_set() and time.monotonic() < deadline and self.auth_pending == state:
                    server.handle_request()
            finally:
                server.server_close()
                with self.lock:
                    if self.auth_pending == state:
                        self.auth_pending = None
        self.auth_thread = Thread(target=listen, daemon=True, name='bot-oauth')
        self.auth_thread.start()
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
        return 'https://accounts.google.com/o/oauth2/v2/auth?' + urlencode({
            'client_id': client_id, 'redirect_uri': redirect, 'response_type': 'code', 'scope': SCOPE,
            'state': state, 'code_challenge': challenge, 'code_challenge_method': 'S256',
            'access_type': 'offline', 'prompt': 'consent select_account'})
