"""Read-only OneComme bridge. Queue rules remain in ApplicationServices."""
from collections import OrderedDict
from datetime import datetime, timezone, timedelta
from html.parser import HTMLParser
from threading import RLock
import time

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
    def __init__(self, services, preferences=None):
        self.services = services
        self.services.receive_service.quoted_names_only = True
        self.lock = RLock()
        self.frames = OrderedDict()
        self.preferences = preferences
        self.selected = preferences.read('selected_frame', '') if preferences else ''
        if self.selected:
            self.frames[self.selected] = '前回の配信（コメント再受信待ち）'
        self.results = {}
        self.last_result = ''
        self.since = datetime.now(timezone.utc)
        self.heartbeat_at = 0
        self.received = 0
        self.commands = 0
        self.dropped = 0

    def heartbeat(self, dropped=0):
        with self.lock:
            self.heartbeat_at = time.monotonic()
            self.dropped = dropped

    def snapshot(self):
        with self.lock:
            return {"connected": time.monotonic() - self.heartbeat_at < 6,
                    "frames": [{"id": k, "name": v} for k, v in self.frames.items()],
                    "selected": self.selected, "received": self.received,
                    "commands": self.commands, "dropped": self.dropped,
                    "results": dict(self.results), "last_result": self.last_result}

    def select(self, frame_id):
        with self.lock:
            if frame_id and frame_id not in self.frames:
                raise ValueError("わんコメで対象配信のコメントを1件受信してください")
            if self.preferences:
                self.preferences.write('selected_frame', frame_id)
            self.selected = frame_id
            self.since = datetime.now(timezone.utc)
            return self.snapshot()

    def record(self, result):
        status = result.get('status', 'processed')
        self.last_result = status
        self.results[status] = self.results.get(status, 0) + 1
        return result

    def receive(self, frame_id, frame_name, comment):
        with self.lock:
            self.frames[frame_id] = frame_name
            self.frames.move_to_end(frame_id)
            while len(self.frames) > 32:
                self.frames.popitem(last=False)
            self.received += 1
            if frame_id != self.selected:
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
