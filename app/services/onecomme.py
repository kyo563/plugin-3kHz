"""Read-only OneComme bridge. Queue rules remain in ApplicationServices."""
from collections import OrderedDict
from datetime import datetime, timezone, timedelta
from html.parser import HTMLParser
from threading import RLock
import time
import re
import unicodedata
from urllib.parse import urlsplit, parse_qs

from app.services.command_detector import CommandDetector
from app.services.comment_normalizer import CommentNormalizer


class PlainText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)

    def handle_starttag(self, tag, attrs):
        if tag == "br":
            self.parts.append(" ")
        elif tag == "img":
            self.parts.append(dict(attrs).get("alt", ""))


class OneCommeBridge:
    @staticmethod
    def video_url(value):
        # Parse locally; never fetch user-supplied URLs or perform YouTube search.
        value = value.strip()
        if any(unicodedata.category(c) in ('Cc', 'Cf', 'Cs') for c in value):
            raise ValueError('YouTubeのライブ配信URLを入力してください。')
        try:
            url = urlsplit(value)
            if url.scheme != 'https' or url.username or url.password or url.port:
                raise ValueError()
            if url.hostname == 'youtu.be':
                video = url.path.removeprefix('/')
            elif url.hostname in ('youtube.com', 'www.youtube.com', 'm.youtube.com'):
                if url.path == '/watch':
                    videos = parse_qs(url.query).get('v', [])
                    video = videos[0] if len(videos) == 1 else ''
                else:
                    match = re.fullmatch(r'/(?:live|embed)/([A-Za-z0-9_-]{11})/?', url.path)
                    video = match[1] if match else ''
            else:
                video = ''
            if not re.fullmatch(r'[A-Za-z0-9_-]{11}', video):
                raise ValueError()
        except ValueError:
            raise ValueError('YouTubeのライブ配信URLを入力してください。チャンネルURLではなく動画のURLが必要です。') from None
        return video, 'https://www.youtube.com/watch?v=' + video

    @staticmethod
    def frame_key(frame):
        # Queue identity can be supplied by OneComme even when video metadata
        # is unavailable. It is not a Google authorization or a Bot chat ID.
        return frame.get('receive_id') or frame['id']

    def __init__(self, services, preferences=None):
        self.services = services
        self.services.receive_service.quoted_names_only = True
        self.lock = RLock()
        self.frames = OrderedDict()
        self.preferences = preferences
        self.selected = preferences.read('selected_frame', '') if preferences else ''
        self.selection_mode = preferences.read('selection_mode', 'auto') if preferences else 'auto'
        self.pinned_service = preferences.read('pinned_service', '') if preferences else ''
        self.pin_confirmed = preferences.read('pin_confirmed', bool(self.pinned_service)) if preferences else False
        self.pin_explicit = preferences.read('pin_explicit', False) if preferences else False
        self.url_target = preferences.read('url_target', None) if preferences else None
        self.pending = None
        if self.selected:
            self.services.persistence_service.adopt_video(self.selected)
        self.service_frames = None
        self.selection_reason = 'waiting'
        if self.selected:
            self.frames[self.selected] = '前回の配信（コメント再受信待ち）'
        self.results = {}
        self.last_result = ''
        self.since = datetime.now(timezone.utc)
        self.heartbeat_at = 0
        self.received = 0
        self.commands = 0
        self.dropped = 0

    def heartbeat(self, dropped=0, services=None):
        with self.lock:
            self.heartbeat_at = time.monotonic()
            self.dropped = dropped
            if services is not None:
                self.service_frames = services
                self.frames = OrderedDict((self.frame_key(s), s['name']) for s in services if self.frame_key(s))
                if self.selection_mode == 'auto':
                    self._auto_select()
                elif self.url_target:
                    self._url_select()
                elif self.pending:
                    self._target(self.pending['video_id'] if self.pending['video_id'] in self.frames else '')
                elif self.selected and self.selected not in self.frames:
                    self._target('')

    def _set_selected(self, frame_id):
        if self.selected == frame_id:
            return
        if self.preferences:
            self.preferences.write('selected_frame', frame_id)
        self.selected = frame_id
        self.since = datetime.now(timezone.utc)
        if getattr(self, 'bot', None):
            self.bot.pause()

    def _target(self, frame_id, preserve_since=False):
        boundary = self.since
        persistence = self.services.persistence_service
        with self.services.comment_lock, persistence.serialized():
            active = persistence.active_video()
            if frame_id and active and active != frame_id:
                # Invalidate queued Bot messages before replacing operational data.
                self._set_selected('')
                state, revision, _ = persistence.snapshot()
                if state['current'] or state['waiting']:
                    self.pending = {'video_id': frame_id, 'name': self.frames.get(frame_id, frame_id),
                                    'current_count': len(state['current']), 'waiting_count': len(state['waiting']),
                                    'revision': revision, 'saved': persistence.has_saved_video(frame_id)}
                    self._set_selected('')
                    self.selection_reason = 'confirm'
                    return
            if frame_id:
                persistence.switch_video(frame_id)
            self.pending = None
            self._set_selected(frame_id)
            if preserve_since:
                # The first received comment preceded this heartbeat. Keep the
                # existing startup/reconnection boundary, never replay history.
                self.since = boundary

    def remember(self, service_id):
        with self.lock:
            if not any(s['service_id'] == service_id for s in (self.service_frames or [])):
                raise ValueError('わんコメの接続枠が見つかりません。接続を確認してください。')
            if self.preferences:
                self.preferences.write('url_target', None)
                self.preferences.write('pinned_service', service_id)
                self.preferences.write('pin_confirmed', True)
                self.preferences.write('pin_explicit', True)
                self.preferences.write('selection_mode', 'auto')
            self.pinned_service, self.selection_mode = service_id, 'auto'
            self.pin_confirmed = True
            self.pin_explicit = True
            self.url_target = None
            self._auto_select()
            return self.snapshot()

    def select_url(self, value, service_id=None):
        video, url = self.video_url(value)
        with self.lock:
            if service_id:
                row = next((s for s in (self.service_frames or []) if s.get('service_id') == service_id), None)
                if row is None or not row['enabled'] or row['state'] == 'ended':
                    raise ValueError('わんコメで受信中の接続枠を選択してください。')
                if row['id'] and row['id'] != video:
                    raise ValueError('入力したURLと選択した接続枠が異なります。わんコメの接続先を確認してください。')
            self.url_target = {'video_id':video, 'url':url, 'service_id':service_id or ''}
            self.selection_mode = 'manual'
            if self.preferences:
                self.preferences.write('url_target', self.url_target)
                self.preferences.write('selection_mode', 'manual')
            self.since = datetime.now(timezone.utc)
            self._url_select()
            return self.snapshot()

    def _url_select(self):
        target = self.url_target
        rows = self.service_frames or []
        if target['service_id']:
            choice = next((s for s in rows if s.get('service_id') == target['service_id']), None)
        else:
            matches = [s for s in rows if s['enabled'] and s['state'] != 'ended'
                       and (s['id'] == target['video_id'] or s.get('receive_id') == target['video_id'])]
            choice = matches[0] if len(matches) == 1 else None
            if choice:
                self.url_target = {**target, 'service_id':choice['service_id']}
                if self.preferences:
                    self.preferences.write('url_target', self.url_target)
        if choice is None or not choice['enabled'] or choice['state'] == 'ended':
            self.selection_reason = 'url_waiting'
            self._target('')
        elif choice['id'] and choice['id'] != target['video_id']:
            self.selection_reason = 'url_mismatch'
            self._target('')
        elif target.get('receive_id') and choice.get('receive_id') and target['receive_id'] != choice['receive_id']:
            self.selection_reason = 'url_mismatch'
            self._target('')
        else:
            if choice.get('receive_id') and not target.get('receive_id'):
                self.url_target = {**self.url_target, 'receive_id':choice['receive_id']}
                if self.preferences:
                    self.preferences.write('url_target', self.url_target)
            self.selection_reason = 'url_receiving'
            self._target(self.frame_key(choice), preserve_since=bool(choice.get('receive_id')))

    def confirm_transition(self, video_id, carry, revision):
        with self.lock, self.services.comment_lock:
            if not self.pending or self.pending['video_id'] != video_id or time.monotonic() - self.heartbeat_at >= 6:
                raise ValueError('対象配信が変わったか切断されました。接続を確認してください。')
            self.services.persistence_service.switch_video(video_id, carry, revision)
            self.pending = None
            self._set_selected(video_id)
            self.selection_reason = 'remembered' if self.selection_mode == 'auto' else 'manual'
            return self.snapshot()

    def _auto_select(self):
        if self.service_frames is None:
            self.selection_reason = 'waiting'
            return
        saved_active = any(s['service_id'] == self.pinned_service and s['enabled'] and s['state'] != 'ended' for s in self.service_frames)
        if not self.pin_confirmed or (not self.pin_explicit and not saved_active):
            receiving = [s for s in self.service_frames if s['enabled'] and s['state'] != 'ended' and s.get('receive_id')]
            if len(receiving) == 1:
                # Before any actual receipt, metadata selection is provisional.
                # The real comment source wins, not a guessed latest video.
                self.pinned_service = receiving[0]['service_id']
                self.pin_confirmed = True
                if self.preferences:
                    self.preferences.write('pinned_service', self.pinned_service)
                    self.preferences.write('pin_confirmed', True)
        if self.pinned_service:
            choice = next((s for s in self.service_frames if s['service_id'] == self.pinned_service), None)
            self.selection_reason = ('missing' if choice is None else
                                     'waiting' if not choice['enabled'] or choice['state'] == 'ended' else
                                     'receiving' if choice.get('receive_id') else
                                     'resolving' if not choice['id'] else 'remembered')
            linked = self.selection_reason in ('remembered', 'receiving')
            self._target(self.frame_key(choice) if linked else '', preserve_since=linked and bool(choice.get('receive_id')))
            return
        connected = [s for s in self.service_frames if s['enabled']]
        active = [s for s in connected if s['state'] != 'ended']
        # OneComme's enabled connection takes precedence over saved/disabled rows.
        candidates = active if connected else [s for s in self.service_frames if s['state'] != 'ended']
        choice = candidates[0] if len(candidates) == 1 else None
        reason = 'onecomme' if active else 'configured'
        if len(candidates) > 1:
            receiving = [s for s in candidates if s.get('receive_id')]
            if len(receiving) == 1:
                choice, reason = receiving[0], 'receiving'
            # Only choose a latest stream when every candidate has comparable metadata.
            if choice is None and all(s['id'] and s['start_time'] for s in candidates):
                times = [(s['start_time'] * 1000 if s['start_time'] < 1e12 else s['start_time'], s) for s in candidates]
                latest = max(t for t, _ in times)
                newest = [s for t, s in times if t == latest]
                if len(newest) == 1:
                    choice, reason = newest[0], 'latest'
            if choice is None:
                reason = 'multiple'
        if choice is not None and choice.get('receive_id'):
            reason = 'receiving'
        elif choice is not None and not choice['id']:
            reason = 'resolving'
        if not candidates:
            reason = 'waiting'
        self.selection_reason = reason
        if choice is not None:
            self.pinned_service = choice['service_id']
            self.pin_confirmed = bool(choice.get('receive_id'))
            if self.preferences:
                self.preferences.write('pinned_service', self.pinned_service)
                self.preferences.write('pin_confirmed', self.pin_confirmed)
            if not choice['enabled']:
                self.selection_reason = 'waiting'
        self._target(self.frame_key(choice) if choice and choice['enabled'] else '',
                     preserve_since=bool(choice and choice.get('receive_id')))

    def snapshot(self):
        with self.lock:
            if self.pending:
                state, revision, _ = self.services.persistence_service.snapshot()
                self.pending = {**self.pending, 'current_count':len(state['current']),
                                'waiting_count':len(state['waiting']), 'revision':revision}
            connected = time.monotonic() - self.heartbeat_at < 6
            source = self.url_target['service_id'] if self.selection_mode == 'manual' and self.url_target else self.pinned_service
            row = next((s for s in (self.service_frames or []) if s.get('service_id') == source), None)
            ready = connected and not self.pending and (bool(self.selected) or
                    ((self.selection_mode == 'auto' or (self.url_target and self.selection_reason == 'url_receiving'))
                     and row is not None and row['enabled'] and row['state'] != 'ended'))
            return {"connected": connected, "ready_to_receive": ready,
                    "frames": [{"id": k, "name": v} for k, v in self.frames.items()],
                    "selected": self.selected, "received": self.received,
                    "selection_mode": self.selection_mode, "selection_reason": self.selection_reason,
                    "selected_name": self.frames.get(self.selected, '') or (row['name'] if ready and row else ''),
                    "pinned_service": self.pinned_service, "pending": self.pending,
                    "manual_url": self.url_target['url'] if self.url_target else '',
                    "url_service_id": self.url_target['service_id'] if self.url_target else '',
                    "services": [{**s, 'queue_id': self.frame_key(s)} for s in (self.service_frames or [])],
                    "commands": self.commands, "dropped": self.dropped,
                    "results": dict(self.results), "last_result": self.last_result}

    def select(self, frame_id, mode='manual'):
        with self.lock:
            if mode == 'manual' and frame_id and frame_id not in self.frames:
                raise ValueError("わんコメの配信情報を受信してから選択してください")
            if self.preferences:
                self.preferences.write('url_target', None)
                self.preferences.write('selection_mode', mode)
            self.url_target = None
            self.selection_mode = mode
            if mode == 'auto':
                self._auto_select()
            else:
                self.selection_reason = 'manual' if frame_id else 'stopped'
                self._target(frame_id)
                self.since = datetime.now(timezone.utc)
            return self.snapshot()

    def record(self, result):
        status = result.get('status', 'processed')
        self.last_result = status
        self.results[status] = self.results.get(status, 0) + 1
        return result

    def receive(self, frame_id, frame_name, comment, service_id=None):
        with self.lock:
            if self.service_frames is None:
                self.frames[frame_id] = frame_name
                self.frames.move_to_end(frame_id)
            while len(self.frames) > 32:
                self.frames.popitem(last=False)
            self.received += 1
            row = next((s for s in (self.service_frames or []) if s['service_id'] == service_id), None)
            if service_id is not None and (row is None or not row['enabled'] or row['state'] == 'ended' or self.frame_key(row) != self.selected
                    or (self.selection_mode == 'auto' and service_id != self.pinned_service)
                    or (self.url_target and service_id != self.url_target['service_id'])):
                return self.record({'status': 'unselected'})
            matches_alias = row is not None and self.selected and frame_id in (row['id'], row.get('receive_id'))
            if frame_id != self.selected and not matches_alias:
                return self.record({"status": "unselected"})
            try:
                at = datetime.fromisoformat(comment.received_at.replace("Z", "+00:00"))
                # Windows JS timestamps can lag the Python clock by one 15.6 ms
                # system tick. Allow only that precision boundary, not old pages.
                if at.tzinfo is None or at + timedelta(milliseconds=20) < self.since or (at - datetime.now(timezone.utc)).total_seconds() > 60:
                    return self.record({"status": "history"})
            except ValueError:
                return self.record({"status": "invalid_timestamp"})
            parser = PlainText()
            parser.feed(comment.message)
            parser.close()
            comment.message = "".join(parser.parts)
            self.services.update_comment_memo(comment)
            if getattr(self, 'bot', None) and self.bot.receive(comment):
                return self.record({'status': 'bot_handled'})
            settings = self.services.persistence_service.get_state()["command_settings"]
            if CommandDetector().detect(CommentNormalizer().normalize(comment.message), settings) == "ignore":
                return self.record({"status": "ignored"})
            result = self.services.receive_comment(comment)
            if not result.duplicate:
                self.commands += 1
            return self.record(result.model_dump())
