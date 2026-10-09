"""Shared Bot: OneComme receives comments; Google credentials stay on the server."""
import ctypes
from ctypes import wintypes
from collections import OrderedDict, deque
from contextlib import contextmanager
import hashlib
import json
import math
import re
import secrets
import sqlite3
from threading import Event, Lock, RLock, Thread
import time
import unicodedata
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4
import httpx
from pydantic import BaseModel, ConfigDict, StrictBool, field_validator
from app.services.user_identity_service import UserIdentityService

BOT_ORIGIN = 'https://joinqueue-bot-backend.joinqueue.workers.dev'
BOT_ID = 'UCV3VeoFI04L79MqwuApT-Hg'
BOT_HANDLE = '@JoinQueueBot'
POSITION_REPLY_COOLDOWN_SECONDS = 180
ERRORS = {
    'SERVICE_DISABLED': '共通Botは運営側で停止中です。',
    'UNAUTHENTICATED': '接続が失効しました。接続解除後に再接続してください。',
    'CHANNEL_NOT_LINKED': '配信チャンネルを接続してください。',
    'AUTH_IN_PROGRESS': 'Google認証の結果を処理中です。少し待って「認証結果を確認」を押してください。',
    'CHANNEL_AUTH_UNAVAILABLE': '配信者のGoogle権限を確認できません。時間をおいて接続を確認してください。',
    'BOT_AUTH_EXPIRED': '共通BotのGoogle認証が期限切れです。運営者によるBotの再認証が必要です。配信チャンネルの再接続は不要です。通知は再送しません。',
    'BOT_UNAVAILABLE': '共通Botの認証またはYouTube接続を確認できません。運営者による確認が必要です。通知は再送しません。',
    'CHANNEL_MISMATCH': '接続したチャンネルと配信の所有者が一致しません。',
    'LIVE_NOT_ACTIVE': '対象がライブ配信の枠ではないか、終了済み・利用不可です。わんコメの接続先を確認してください。',
    'STREAM_NOT_SELECTED': 'わんコメで対象のYouTube枠に接続してください。開始前の枠も選択できます。',
    'CHAT_UNAVAILABLE': '対象配信のチャット接続先をYouTube公式APIで確認できません。チャットの有効設定・公開範囲を確認してください。',
    'BOT_PERMISSION_REQUIRED': '@JoinQueueBotのモデレーター登録を確認してください。',
    'RATE_LIMITED': '間隔が短すぎます。時間を空けてください。この通知は再送しません。',
    'QUOTA_EXHAUSTED': '共通Botの利用上限に達しました。',
    'INVALID_MESSAGE': '通知の名前の長さ・人数・形式を確認してください。',
    'REQUEST_EXPIRED': '通知の期限が切れました。再送しません。',
    'DUPLICATE_CONFLICT': '通知IDの重複を検出しました。この通知は再送しません。',
    'DELIVERY_UNKNOWN': '投稿結果が不明です。二重投稿を避けるため再送しません。',
}
class BotError(ValueError):
    def __init__(self, code='UNAVAILABLE'):
        self.code = code
        super().__init__(ERRORS.get(code, '共通Botサーバーに接続できません。通知は再送しません。'))

class BotSettings(BaseModel):
    model_config = ConfigDict(extra='forbid')
    enabled: StrictBool = False
    announce_now: StrictBool = True
    reply_position: StrictBool = True
    periodic: StrictBool = True
    interval_minutes: int = 30
    initial_delay_minutes: int = 30

    @field_validator('initial_delay_minutes', mode='before')
    @classmethod
    def initial_delay(cls, value):
        if type(value) is not int or value not in (15, 30, 45, 60):
            raise ValueError('15・30・45・60分のいずれかを指定してください')
        return value

    @field_validator('interval_minutes', mode='before')
    @classmethod
    def interval(cls, value):
        if type(value) is not int or value not in (15, 30):
            raise ValueError('15分または30分を指定してください')
        return value

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
        raw = protect(row[0], True) if key in ('shared_device', 'shared_pairing', 'credentials') else row[0]
        return json.loads(raw)

    def write(self, key, value):
        raw = json.dumps(value, ensure_ascii=False).encode('utf8')
        if key in ('shared_device', 'shared_pairing', 'credentials'):
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


class UnavailableBotStore:
    """Fail closed without replacing/deleting an unreadable Bot database."""
    def read(self, *args):
        raise ValueError('Bot保存データを読み取れません')

    def write(self, *args):
        raise ValueError('Bot保存データを変更できません')


class AnnouncementBot:
    def __init__(self, services, bridge, store, *, client=None, clock=time.monotonic, wall_clock=time.time):
        self.services, self.bridge, self.store, self.clock = services, bridge, store, clock
        self.wall_clock = wall_clock
        self.http = client or httpx.Client(timeout=25, trust_env=False, follow_redirects=False)
        self.lock, self.command_lock, self.send_lock = RLock(), Lock(), Lock()
        self.stopped = Event()
        self.device, self.error = None, ''
        try:
            raw = store.read('shared_settings')
            if raw is None:
                legacy = store.read('settings', {}) or {}
                raw = {k: legacy[k] for k in ('announce_now', 'reply_position', 'periodic') if k in legacy}
                raw['interval_minutes'] = legacy.get('interval_minutes') if legacy.get('interval_minutes') in (15, 30) else 30
            self.settings = BotSettings(**raw).model_copy(update={'enabled': False})
        except Exception:
            self.settings = BotSettings()
            self.error = 'Bot保存設定を読み取れないためBotを停止しています。保存データは保持しました。待機列・OBSは利用できます。'
        try:
            device = store.read('shared_device')
            if device is not None and (not isinstance(device, str) or not re.fullmatch(r'[A-Za-z0-9_-]{43}', device)):
                raise ValueError()
            self.device = device
        except Exception:
            self.error = self.error or '保存した接続キーを復元できません。元のWindowsユーザーで開いてください。'
        self.storage_error = bool(self.error)
        # Old Google credentials are never read, reused, uploaded or deleted.
        self.connection = self.authorization_url = self.confirmation = self.checked = None
        self.authorization_expires_at = None
        self.auth_preparing = self.auth_expired = self.auth_pending = False
        if self.device and not self.storage_error:
            try:
                pairing = store.read('shared_pairing')
                if pairing is not None:
                    if not isinstance(pairing, dict) or pairing.get('deviceHash') != hashlib.sha256(self.device.encode()).hexdigest():
                        raise ValueError()
                    self._restore_pairing(pairing)
            except Exception:
                # A damaged/old pending link must not strand an otherwise valid device.
                self.error = '認証リンクを復元できません。「認証を再開・やり直す」で接続状態を確認してください。接続キーは保持しています。'
        self.bot_profile = {'id': BOT_ID, 'name': 'JoinQueueBot', 'handle': BOT_HANDLE}
        self.test_available = False
        self.deletion_available = False
        self.running, self.active_video = False, ''
        self.queue = deque(maxlen=20)
        self.seen, self.reply_times, self.now_events = OrderedDict(), OrderedDict(), OrderedDict()
        self.last_sent, self.next_guide, self.last_result = -100.0, None, ''
        self.first_guide_pending = True
        self.last_test = -100.0
        self.generation, self.thread = 0, None

    def start(self):
        self.thread = Thread(target=self._run, daemon=True, name='shared-queue-bot')
        self.thread.start()

    def pause(self):
        with self.lock:
            self.running, self.active_video = False, ''
            self.generation += 1
            self.queue.clear()
            self.next_guide = self.checked = None
            self.settings = self.settings.model_copy(update={'enabled': False})

    def stop(self):
        self.stopped.set()
        self.pause()
        if self.thread:
            self.thread.join(timeout=27)
        self.http.close()

    def status(self):
        with self.lock:
            live_pairing = self._pairing_live() and self.connection is None
            expired = self.auth_expired or (self.authorization_expires_at is not None and not live_pairing)
            auth_state = ('authenticated' if self.connection else 'preparing' if self.auth_preparing else
                          'expired' if expired else 'pending' if self.auth_pending else 'unverified' if self.device else 'disconnected')
            return {'settings': self.settings.model_dump(),
                    'account': self.bot_profile.copy(), 'test_available': self.test_available,
                    'deletion_available': self.deletion_available,
                    'authenticated': self.connection is not None, 'ready': self.running,
                    'channel_id': self.connection['channelId'] if self.connection else None,
                    'error': self.error, 'last_result': self.last_result, 'pending': len(self.queue),
                    'authorization_url': self.authorization_url if live_pairing else None,
                    'confirmation': self.confirmation if live_pairing else None,
                    'authorization_expires_at': self.authorization_expires_at,
                    'auth_state': auth_state,
                    'has_connection_key': self.device is not None, 'login_pending': live_pairing,
                    'next_announcement_seconds': max(0, math.ceil(self.next_guide - self.clock())) if self.running and self.next_guide is not None else None}

    def _pairing_live(self):
        return bool(self.authorization_url and self.authorization_expires_at is not None
                    and self.wall_clock() * 1000 < self.authorization_expires_at)

    def _restore_pairing(self, data):
        url = urlsplit(data.get('authorizationUrl', ''))
        query = parse_qs(url.query, keep_blank_values=True)
        confirmation, expires = data.get('confirmation'), data.get('expiresAt')
        if (url.scheme + '://' + url.netloc != BOT_ORIGIN or url.path != '/connect' or url.fragment
                or set(query) != {'id', 'key'} or any(len(v) != 1 for v in query.values())
                or not re.fullmatch(r'[a-f0-9-]{36}', query['id'][0])
                or not re.fullmatch(r'[A-Za-z0-9_-]{43}', query['key'][0])
                or not isinstance(confirmation, str) or not re.fullmatch(r'[a-f0-9]{8}', confirmation)
                or confirmation != query['id'][0][:8] or type(expires) is not int or expires <= 0):
            raise BotError()
        self.authorization_url, self.confirmation, self.authorization_expires_at = data['authorizationUrl'], confirmation, expires
        self.auth_expired = False
        self.auth_pending = True

    def _clear_pairing(self):
        self.store.write('shared_pairing', None)
        self.authorization_url = self.confirmation = self.authorization_expires_at = None
        self.auth_pending = False

    def _accept_connection(self, data):
        if (data.get('status') != 'connected' or not re.fullmatch(r'UC[\w-]{22}', str(data.get('channelId', '')))
                or not re.fullmatch(r'[a-f0-9-]{36}', str(data.get('connectionId', '')))):
            raise BotError()
        self._clear_pairing()
        self.connection = {k: data[k] for k in ('channelId', 'connectionId')}
        self.auth_expired = False
        self.test_available = isinstance(data.get('features'), dict) and data['features'].get('connectionTest') is True
        self.deletion_available = isinstance(data.get('features'), dict) and data['features'].get('dataDeletion') is True
        profile = data.get('bot')
        if isinstance(profile, dict) and profile.get('id') == BOT_ID:
            from app.schemas.avatar import normalize_avatar_url
            name = profile.get('name')
            if isinstance(name, str) and 0 < len(name) <= 200:
                self.bot_profile = {'id': BOT_ID, 'name': name, 'handle': BOT_HANDLE,
                                    'icon': normalize_avatar_url(profile.get('icon'))}

    def _observe_pending(self, data):
        if self.connection:
            self.pause()
            self.connection = None
        # Once the Google form was submitted its landing URL is no longer usable.
        cached_id = parse_qs(urlsplit(self.authorization_url).query).get('id', [None])[0] if self.authorization_url else None
        if (data.get('stage') in ('pending', 'consumed')
                or (data.get('pairingId') is not None and data['pairingId'] != cached_id)):
            self._clear_pairing()
        self.auth_pending = True
        self.auth_expired = False
        self.error = ''

    def configure(self, settings):
        with self.lock:
            if self.storage_error:
                raise ValueError(self.error)
            if settings.enabled and not self.running:
                raise ValueError('接続確認後に「Botを起動」を押してください。')
            old = self.settings
            self.store.write('shared_settings', settings.model_copy(update={'enabled': False}).model_dump())
            self.settings = settings
            self.generation += 1
            self.queue.clear()
            if not settings.enabled:
                self.pause()
            elif not settings.periodic:
                self.next_guide = None
            elif not old.periodic or old.initial_delay_minutes != settings.initial_delay_minutes:
                self.first_guide_pending = True
                self.next_guide = self.clock() + settings.initial_delay_minutes * 60
            elif not self.first_guide_pending and old.interval_minutes != settings.interval_minutes:
                self.next_guide = self.clock() + settings.interval_minutes * 60
        return self.status()

    def _api(self, path, body=None):
        if not self.device:
            raise BotError('CHANNEL_NOT_LINKED')
        try:
            with self.http.stream('POST', BOT_ORIGIN + path, headers={'Authorization': 'Bearer ' + self.device},
                                  json=body or {}, follow_redirects=False) as response:
                raw = bytearray()
                for part in response.iter_bytes():
                    raw.extend(part)
                    if len(raw) > 8192:
                        raise BotError()
                data = json.loads(raw)
                if not isinstance(data, dict):
                    raise BotError()
                if not 200 <= response.status_code < 300:
                    code = data.get('error', {}).get('code') if isinstance(data.get('error'), dict) else ''
                    raise BotError(code if code in ERRORS else 'UNAVAILABLE')
                return data
        except BotError:
            raise
        except Exception:
            raise BotError() from None

    def command(self, action):
        if action == 'stop':
            self.pause()
            return self.status()
        if not self.command_lock.acquire(blocking=False):
            raise ValueError('接続処理中です。少し待ってください。')
        try:
            if self.storage_error or self.stopped.is_set():
                raise BotError()
            bridge = self.bridge.snapshot()
            video = bridge['selected'] if bridge['connected'] and re.fullmatch(r'[A-Za-z0-9_-]{11}', bridge['selected']) else ''
            epoch = self.generation
            if action == 'connect':
                self.auth_preparing = True
                if self.device:
                    try:
                        data = self._api('/v1/connections/status')
                    except BotError as exc:
                        if exc.code != 'UNAUTHENTICATED':
                            raise
                        self.pause()
                        epoch = self.generation
                        self.connection = None
                        self._clear_pairing()
                        self.auth_expired = True
                    else:
                        if data.get('status') == 'connected':
                            with self.lock:
                                self._accept_connection(data)
                            self.error = ''
                            return self.status()
                        if data.get('status') != 'pending':
                            raise BotError()
                        self._observe_pending(data)
                        if self._pairing_live():
                            self.auth_preparing = False
                            return self.status()
                else:
                    token = secrets.token_urlsafe(32)
                    self.store.write('shared_device', token)
                    self.device = token
                # Reuse the device: server atomically restarts only UNAUTHENTICATED
                # pairings and preserves a connection that completed concurrently.
                data = self._api('/v1/connections/start')
                with self.lock:
                    if epoch != self.generation or self.stopped.is_set():
                        raise BotError()
                    if data.get('status') == 'connected':
                        self._accept_connection(data)
                    else:
                        self._restore_pairing(data)
                        if not self._pairing_live():
                            raise BotError()
                        self.store.write('shared_pairing', {k: data[k] for k in ('authorizationUrl', 'confirmation', 'expiresAt')} |
                                         {'deviceHash': hashlib.sha256(self.device.encode()).hexdigest()})
                self.auth_preparing = False
            elif action == 'disconnect':
                self.pause()
                if self.device:
                    try:
                        self._api('/v1/connections/disconnect')
                    except BotError as exc:
                        if exc.code != 'UNAUTHENTICATED':
                            raise
                self.store.write('shared_device', None)
                self._clear_pairing()
                self.auth_expired = False
                self.device = self.connection = self.authorization_url = self.confirmation = None
                self.test_available = self.deletion_available = False
            elif action == 'erase':
                if not self.deletion_available or not self.connection:
                    raise ValueError('認証結果を確認してください。サーバー記録の削除は対応サーバーとの接続時のみ利用できます。')
                channel_id = self.connection['channelId']
                self.pause()
                if not self.send_lock.acquire(blocking=False):
                    raise ValueError('投稿処理中です。Botは停止しました。処理完了後に削除をやり直してください。')
                try:
                    data = self._api('/v1/connections/erase', {'confirmation': channel_id})
                    if data.get('status') != 'deleted' or data.get('securityRetentionHours') != 25:
                        raise BotError()
                    self.store.write('shared_device', None)
                    self._clear_pairing()
                    self.auth_expired = False
                    self.device = self.connection = self.authorization_url = self.confirmation = None
                    self.test_available = self.deletion_available = False
                    self.last_result = 'サーバーの接続情報・投稿台帳を削除しました。短期の制限用ハッシュは最長25時間で削除します。PC内の待機列・設定とYouTube投稿は変更していません。'
                finally:
                    self.send_lock.release()
            elif action in ('status', 'check', 'start', 'test'):
                if action != 'status' and not video:
                    raise BotError('STREAM_NOT_SELECTED')
                with self.lock:
                    if action == 'start' and self.running and self.active_video == video:
                        return self.status()
                if action in ('start', 'test') and self.checked and self.checked[0] == video and self.clock() - self.checked[1] < 60:
                    data = self.checked[2]
                else:
                    data = self._api('/v1/connections/' + ('status' if action == 'status' else 'check'), {'videoId': video or None})
                current = self.bridge.snapshot()
                with self.lock:
                    if epoch != self.generation or self.stopped.is_set():
                        raise BotError()
                    if data.get('status') == 'pending':
                        self._observe_pending(data)
                        if action != 'status':
                            raise BotError('CHANNEL_NOT_LINKED')
                        return self.status()
                    self._accept_connection(data)
                    if action != 'status':
                        self.checked = (video, self.clock(), data)
                    if action == 'test':
                        if not self.test_available:
                            raise ValueError('接続テストはサーバー側の更新待ちです。通常のBot通知は引き続き利用できます。')
                        if data.get('serviceEnabled') is not True:
                            raise BotError('SERVICE_DISABLED')
                        if current['selected'] != video or not current['connected']:
                            raise BotError('LIVE_NOT_ACTIVE')
                        if self.clock() - self.last_test < 60 or self.clock() - self.last_sent < 10:
                            raise BotError('RATE_LIMITED')
                        if not self.send_lock.acquire(blocking=False):
                            raise ValueError('投稿処理中です。少し待ってから再試行してください。')
                        try:
                            self.last_test = self.last_sent = self.clock()
                            result = self._api('/v1/bot/posts', {'channelConnectionId':self.connection['connectionId'],
                                'eventId':str(uuid4()), 'videoId':video, 'createdAt':int(time.time()*1000),
                                'templateId':'connection-test', 'variables':{}})
                            if result.get('status') != 'sent':
                                raise BotError('DELIVERY_UNKNOWN')
                            self.last_result = '接続テストを投稿しました。配信チャットで確認してください。'
                        except BotError:
                            self.pause()
                            raise
                        finally:
                            self.send_lock.release()
                    if action == 'start':
                        if data.get('serviceEnabled') is not True:
                            raise BotError('SERVICE_DISABLED')
                        if current['selected'] != video or not current['connected']:
                            raise BotError('LIVE_NOT_ACTIVE')
                        self.generation += 1
                        self.queue.clear()
                        self.running, self.active_video = True, video
                        self.settings = self.settings.model_copy(update={'enabled': True})
                        self.first_guide_pending = True
                        self.next_guide = self.clock() + self.settings.initial_delay_minutes * 60 if self.settings.periodic else None
            else:
                raise ValueError('未対応の接続操作です。')
            self.error = ''
            return self.status()
        except ValueError as exc:
            if isinstance(exc, BotError) and exc.code == 'UNAUTHENTICATED':
                self.pause()
                self.connection = None
                self._clear_pairing()
                self.auth_expired = True
            self.error = ('認証サーバーに接続できません。接続キーは保持しています。通信復旧後に再試行してください。'
                          if action in ('connect', 'status') and isinstance(exc, BotError) and exc.code == 'UNAVAILABLE' else str(exc))
            if self.error != str(exc):
                raise ValueError(self.error) from None
            raise
        except Exception:
            self.error = '接続設定を保存できません。保存先と接続状態を確認してください。'
            raise ValueError(self.error) from None
        finally:
            self.auth_preparing = False
            self.command_lock.release()

    def disconnect(self):
        return self.command('disconnect')

    def is_self(self, comment):
        return comment.source == 'youtube' and (comment.user_key == BOT_ID or (comment.youtube_handle or '').lower() == BOT_HANDLE.lower())

    def _enqueue(self, kind, data, event_id=None):
        with self.lock:
            flags = {'called': self.settings.announce_now, 'position': self.settings.reply_position, 'announcement': self.settings.periodic}
            if self.running and self.settings.enabled and flags[kind]:
                self.queue.append((self.clock(), self.generation, self.active_video, kind, data, event_id or str(uuid4())))

    def announce(self):
        state = self.services.build_view_state()
        ids = tuple(u['user_id'] for u in state['current'] if not u.get('is_placeholder'))
        if not ids:
            return
        with self.lock:
            if not self.running or not self.settings.announce_now:
                return
            key = (self.active_video, state.get('total_match_count', 0), ids)
            if key in self.now_events:
                return
            self.now_events[key] = True
            while len(self.now_events) > 1000:
                self.now_events.popitem(last=False)
        self._enqueue('called', ids)

    def receive(self, comment):
        if self.is_self(comment):
            return True
        if comment.source != 'youtube' or not re.search(r'(?<![\w@.·-])@JoinQueueBot(?![\w.·-])', comment.message, re.I):
            return False
        with self.lock:
            key = comment.external_message_id
            if not key or key in self.seen:
                return True
            self.seen[key] = True
            while len(self.seen) > 2000:
                self.seen.popitem(last=False)
            if not self.running or not self.settings.reply_position:
                return True
            uid = comment.user_key
            now = self.clock()
            previous = self.reply_times.get(uid)
            if previous is not None and now - previous < POSITION_REPLY_COOLDOWN_SECONDS:
                return True
            self.reply_times[uid] = now
            while len(self.reply_times) > 1000:
                self.reply_times.popitem(last=False)
        event = 'mention-' + hashlib.sha256((self.active_video + ':' + key).encode()).hexdigest()
        self._enqueue('position', (uid, comment.youtube_handle, comment.display_name), event)
        return True

    @staticmethod
    def _name(user):
        handle = user.get('youtube_handle')
        # Keep a real handle intact or omit it: truncating it could mention someone else.
        if not (isinstance(handle, str) and handle.startswith('@') and 1 < len(handle.encode('utf-16-le', errors='replace')) // 2 <= 45
                and 'www.' not in handle.lower()
                and all(c in '_.·-' or unicodedata.category(c)[0] in 'LMN' for c in handle[1:])):
            handle = None
        name = handle or user.get('declared_player_name') or user.get('display_name') or '参加者'
        if not handle:
            name = ''.join(c for c in name if unicodedata.category(c) not in ('Cc', 'Cf', 'Cs'))
            name = re.sub(r'www\.', 'ｗｗｗ．', name, flags=re.I).translate(str.maketrans({'/': '／', ':': '：', '@': '＠', '\\': '＼'}))
            # Three names plus template text fit within the 200-character YouTube limit.
            name = name.encode('utf-16-le')[:90].decode('utf-16-le', errors='ignore').strip() or '参加者'
        return {'name': name, **({'handle': handle} if handle else {})}

    def _variables(self, kind, data, state):
        group = state.get('total_match_count', 0) + 1
        if kind == 'called':
            members = [u for u in state['current'] if not u.get('is_placeholder')]
            if tuple(u['user_id'] for u in members) != data:
                return None
            return {'members': [self._name(u) for u in members], 'group': group}
        if kind == 'announcement':
            count = len(state['waiting'])
            return {'waitingCount': count, 'groupCount': math.ceil(count / 3), 'groupSize': 3}
        uid, handle, display = data
        identity = UserIdentityService().build_comment_user_id('youtube', uid)
        variables = self._name({'youtube_handle': handle, 'display_name': display})
        if any(u['user_id'] == identity for u in state['current']):
            return {**variables, 'state': 'now'}
        for i, user in enumerate(state['waiting'], 1):
            if user['user_id'] == identity:
                return {**variables, 'state': 'waiting', 'position': i, 'group': math.ceil(i / 3)}
        return {**variables, 'state': 'not-queued'}

    def tick(self):
        if not self.send_lock.acquire(blocking=False):
            return
        try:
            bridge = self.bridge.snapshot()
            if not self.running:
                return
            if not bridge['connected'] or bridge['selected'] != self.active_video:
                self.pause()
                self.error = '配信変更または切断のため停止しました。接続確認して起動してください。'
                return
            now = self.clock()
            with self.lock:
                if self.settings.periodic and self.next_guide is not None and now >= self.next_guide:
                    late = now - self.next_guide
                    self.first_guide_pending = False
                    self.next_guide = now + self.settings.interval_minutes * 60
                    if late <= 60:
                        self._enqueue('announcement', None)
                if not self.queue or now - self.last_sent < 10:
                    return
                at, epoch, video, kind, data, event_id = self.queue.popleft()
                if now - at > 60 or epoch != self.generation or not self.connection:
                    return
            variables = self._variables(kind, data, self.services.build_view_state())
            current = self.bridge.snapshot()
            with self.lock:
                if variables is None or epoch != self.generation or not self.running or current['selected'] != video or not current['connected']:
                    return
                candidate = {'channelConnectionId': self.connection['connectionId'], 'eventId': event_id,
                             'videoId': video, 'createdAt': int(time.time() * 1000),
                             'templateId': kind, 'variables': variables}
                if kind == 'position':
                    candidate['recipient'] = {'service': 'youtube', 'userId': data[0]}
                self.last_sent = now
            try:
                result = self._api('/v1/bot/posts', candidate)
                if epoch == self.generation:
                    self.last_result = 'Bot通知を送信しました。' if result.get('status') == 'sent' else ERRORS['DELIVERY_UNKNOWN']
            except BotError as exc:
                if epoch == self.generation:
                    self.error = str(exc)
                    if exc.code not in ('RATE_LIMITED', 'INVALID_MESSAGE', 'REQUEST_EXPIRED', 'DUPLICATE_CONFLICT'):
                        self.pause()
        finally:
            self.send_lock.release()

    def _run(self):
        while not self.stopped.wait(1):
            try:
                self.tick()
            except Exception:
                self.pause()
                self.error = '通知処理に失敗したため停止しました。通知は再送しません。'
