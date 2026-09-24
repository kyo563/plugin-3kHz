from __future__ import annotations
from app.schemas.description import DEFAULT_DESCRIPTION, LEGACY_DEFAULT_DESCRIPTION

from app.schemas.avatar import normalize_avatar_url

from app.schemas.command_settings import CommandSettings

import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterator

from app.schemas.overlay_settings import OverlaySettings

DEFAULT_DB_PATH = "data/waiting_list.sqlite3"


class SQLitePersistenceService:
    def __init__(self, initial_state: dict, db_path: str | None = None):
        self._initial_state = deepcopy(initial_state)
        self._db_path = db_path or os.getenv("WAITING_LIST_DB_PATH") or DEFAULT_DB_PATH
        self._lock = threading.RLock()
        self.revision = 0
        self._undo = None
        self._ensure_parent_dir()
        self._initialize_schema()
        self._initialize_if_empty()
        with self._connect() as conn:
            row = conn.execute("SELECT value FROM app_state WHERE key='revision'").fetchone()
            self.revision = int(row["value"]) if row else 0

    def _ensure_parent_dir(self) -> None:
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _initialize_schema(self) -> None:
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS app_state (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS participants (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    declared_player_name TEXT NULL,
                    status TEXT NOT NULL CHECK(status IN ('current','waiting','done','cancelled')),
                    position INTEGER NOT NULL,
                    participation_count INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS operation_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """)
            conn.execute("CREATE TABLE IF NOT EXISTS font_assets (id TEXT PRIMARY KEY, name TEXT NOT NULL, mime TEXT NOT NULL, data BLOB NOT NULL)")
            columns = {row[1] for row in conn.execute("PRAGMA table_info(participants)").fetchall()}
            if "declared_player_name" not in columns:
                conn.execute("ALTER TABLE participants ADD COLUMN declared_player_name TEXT NULL")

            for field in ('youtube_handle', 'youtube_nickname', 'avatar_url', 'onecomme_memo'):
                if field not in columns:
                    conn.execute(f"ALTER TABLE participants ADD COLUMN {field} TEXT NULL")

    def _is_empty(self) -> bool:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS count FROM app_state").fetchone()
            return row["count"] == 0

    def _initialize_if_empty(self) -> None:
        if self._is_empty():
            self.set_state(deepcopy(self._initial_state))

    def _sanitize_participation_counts(self, raw: object) -> dict[str, int]:
        if not isinstance(raw, dict):
            return {}
        sanitized: dict[str, int] = {}
        for key, value in raw.items():
            user_id = str(key)
            try:
                count = int(value)
            except (TypeError, ValueError):
                count = 0
            sanitized[user_id] = max(0, count)
        return sanitized

    def get_state(self) -> dict:
        with self._connect() as conn:
            # sqlite3 does not start a transaction for SELECT automatically.
            # All three reads must describe the same committed state.
            conn.execute("BEGIN")
            app_state_rows = conn.execute("SELECT key, value FROM app_state").fetchall()
            app_state = {row["key"]: row["value"] for row in app_state_rows}
            participants = conn.execute("""
                SELECT user_id, display_name, declared_player_name, youtube_handle, youtube_nickname, avatar_url, onecomme_memo, status, participation_count, created_at, updated_at
                FROM participants
                ORDER BY status, position
                """).fetchall()
            logs = conn.execute("SELECT message FROM operation_logs ORDER BY id DESC LIMIT 30").fetchall()

        current, waiting = [], []
        for row in participants:
            if row["status"] not in {"current", "waiting"}:
                continue
            user = {
                "user_id": row["user_id"],
                "display_name": row["display_name"],
                "declared_player_name": row["declared_player_name"],
                "youtube_handle": row["youtube_handle"],
                "youtube_nickname": row["youtube_nickname"],
                "avatar_url": normalize_avatar_url(row["avatar_url"]),
                "onecomme_memo": row["onecomme_memo"],
                "participation_count": row["participation_count"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
            (current if row["status"] == "current" else waiting).append(user)

        user_action_locks = {}
        raw_user_action_locks = app_state.get("user_action_locks")
        if raw_user_action_locks:
            try:
                parsed = json.loads(raw_user_action_locks)
                if isinstance(parsed, dict):
                    user_action_locks = {str(k): str(v) for k, v in parsed.items()}
            except (TypeError, ValueError, json.JSONDecodeError):
                user_action_locks = {}
        participation_counts = {}
        raw_participation_counts = app_state.get("participation_counts")
        if raw_participation_counts:
            try:
                participation_counts = self._sanitize_participation_counts(json.loads(raw_participation_counts))
            except (TypeError, ValueError, json.JSONDecodeError):
                participation_counts = {}

        # Reconcile active rows and the aggregate without reducing either count.
        for user in current + waiting:
            user_id = user["user_id"]
            row_count = self._sanitize_participation_counts({user_id: user["participation_count"]})[user_id]
            count = max(participation_counts.get(user_id, 0), row_count)
            participation_counts[user_id] = count
            user["participation_count"] = count

        return {
            "name_overrides": json.loads(app_state["name_overrides"]) if "name_overrides" in app_state else {u["user_id"]: u["declared_player_name"] for u in current + waiting if u.get("declared_player_name")},
            "overlay_settings": OverlaySettings.model_validate(json.loads(app_state.get("overlay_settings", "{}"))).model_dump(),
            "description_text": (DEFAULT_DESCRIPTION if app_state.get("description_text") == LEGACY_DEFAULT_DESCRIPTION
                                 else app_state.get("description_text", DEFAULT_DESCRIPTION)),
            "comment_names": json.loads(app_state["comment_names"]) if "comment_names" in app_state else {u["user_id"]: u["declared_player_name"] for u in current + waiting if u.get("declared_player_name") and u["declared_player_name"] != (u.get("youtube_nickname") or u.get("display_name"))},
            "participation_history": json.loads(app_state.get("participation_history", "[]")),
            "total_match_count": int(app_state.get("total_match_count", "0")),
            "is_open": app_state.get("is_open", "1") == "1",
            "priority_mode": app_state.get("priority_mode", "1") == "1",
            "command_settings": json.loads(app_state["command_settings"]) if "command_settings" in app_state else CommandSettings().model_dump(),
            "cooldown_seconds": int(app_state.get("cooldown_seconds", "40")),
            "show_declared_player_name_on_overlay": app_state.get("show_declared_player_name_on_overlay", "0") == "1",
            "user_action_locks": user_action_locks,
            "participation_counts": participation_counts,
            "current": current,
            "waiting": waiting,
            "logs": [row["message"] for row in reversed(logs)],
        }

    def set_state(self, state: dict) -> None:
        with self._lock:
            timestamp = self._now()
            with self._connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                row = conn.execute("SELECT value FROM app_state WHERE key='revision'").fetchone()
                next_revision = max(self.revision, int(row["value"]) if row else 0) + 1
                conn.execute("DELETE FROM app_state")
                conn.executemany("INSERT INTO app_state(key, value) VALUES(?, ?)", [
                ("revision", str(next_revision)),
                ("comment_names", json.dumps(state.get("comment_names", {}), ensure_ascii=False)),
                ("participation_history", json.dumps(state.get("participation_history", []), ensure_ascii=False)),
                ("description_text", state.get("description_text", DEFAULT_DESCRIPTION)),
                ("total_match_count", str(state.get("total_match_count", 0))),
                ("name_overrides", json.dumps(state.get("name_overrides", {}), ensure_ascii=False)),
                ("overlay_settings", json.dumps(state.get("overlay_settings", OverlaySettings().model_dump()), ensure_ascii=False)),
                ("is_open", "1" if state["is_open"] else "0"),
                ("priority_mode", "1" if state["priority_mode"] else "0"),
                ("cooldown_seconds", str(state["cooldown_seconds"])),
                ("command_settings", json.dumps(state.get("command_settings", CommandSettings().model_dump()), ensure_ascii=False)),
                ("show_declared_player_name_on_overlay", "1" if state.get("show_declared_player_name_on_overlay", False) else "0"),
                ("user_action_locks", json.dumps(state.get("user_action_locks", {}), ensure_ascii=False)),
                ("participation_counts", json.dumps(self._sanitize_participation_counts(state.get("participation_counts", {})), ensure_ascii=False)),
            ])
                previous = {row["user_id"]: row for row in conn.execute("SELECT * FROM participants")}
                conn.execute("DELETE FROM participants WHERE status IN ('current', 'waiting')")
                for status in ("current", "waiting"):
                    for position, user in enumerate(state.get(status, [])):
                        if user.get("is_placeholder") or user.get("display_name") == "参加者募集中":
                            continue
                        prior = previous.get(user["user_id"])
                        unchanged = prior is not None and (
                            prior["display_name"], prior["declared_player_name"], prior["status"], prior["position"], prior["participation_count"]
                        ) == (user["display_name"], user.get("declared_player_name"), status, position, user.get("participation_count", 0))
                        updated_at = prior["updated_at"] if unchanged else timestamp
                        conn.execute("""
                        INSERT INTO participants(user_id, display_name, declared_player_name, status, position, participation_count, created_at, updated_at, youtube_handle, youtube_nickname, avatar_url, onecomme_memo)
                        VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (user["user_id"], user["display_name"], user.get("declared_player_name"), status, position, user.get("participation_count", 0), user.get("created_at", timestamp), updated_at, user.get("youtube_handle"), user.get("youtube_nickname"), normalize_avatar_url(user.get("avatar_url")), user.get("onecomme_memo")))
                conn.execute("DELETE FROM operation_logs")
                for message in state.get("logs", [])[-30:]:
                    conn.execute("INSERT INTO operation_logs(message, created_at) VALUES(?, ?)", (message, timestamp))

            self.revision = next_revision
            self._undo = None

    def reset_state(self) -> dict:
        with self._lock:
            state = deepcopy(self._initial_state)
            previous = self.get_state()
            state['description_text'] = previous['description_text']
            state['participation_counts'] = deepcopy(previous['participation_counts'])
            for user in state['current'] + state['waiting']:
                user['participation_count'] = state['participation_counts'].setdefault(user['user_id'], user.get('participation_count', 0))
            self.set_state(state)
            return self.get_state()

    def mutate_state(self, callback: Callable[[dict], None]) -> dict:
        with self._lock:
            state = self.get_state()
            callback(state)
            self.set_state(state)
            return state

    def manual_mutate(self, callback) -> dict:
        with self._lock:
            before = self.get_state()
            result = self.mutate_state(callback)
            self._undo = (self.revision, before)
            return result

    def undo_available(self) -> bool:
        with self._lock:
            return self._undo is not None and self._undo[0] == self.revision

    def undo(self) -> None:
        with self._lock:
            if not self.undo_available():
                raise ValueError("戻せる操作がありません。コメント受信・別操作・再起動後は戻せません。")
            state = deepcopy(self._undo[1])
            state["logs"].append("直前の手動操作を元に戻しました")
            self.set_state(state)
            self._undo = None

    @contextmanager
    def serialized(self):
        """Keep multi-step service operations indivisible to UI mutations."""
        with self._lock:
            yield

    def snapshot(self) -> tuple[dict, int, bool]:
        with self._lock:
            return self.get_state(), self.revision, self.undo_available()

    def restore(self, state: dict, expected_revision: int) -> None:
        with self._lock:
            if expected_revision != self.revision:
                raise ValueError("確認中に状態が変わりました。内容を再確認して復元してください。")
            self.set_state(state)
            self._undo = None


    def list_fonts(self):
        with self._connect() as conn:
            return [dict(row) for row in conn.execute("SELECT id, name FROM font_assets ORDER BY name, id")]

    def get_font(self, font_id):
        with self._connect() as conn:
            return conn.execute("SELECT mime, data FROM font_assets WHERE id=?", (font_id,)).fetchone()

    def store_font(self, font_id, name, mime, data):
        with self._lock, self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            if conn.execute("SELECT 1 FROM font_assets WHERE id=?", (font_id,)).fetchone():
                return
            count, total = conn.execute("SELECT count(*), coalesce(sum(length(data)),0) FROM font_assets").fetchone()
            if count >= 20 or total + len(data) > 64 * 1024 * 1024:
                raise ValueError("保存できるフォントは20個・合計64 MiBまでです")
            conn.execute("INSERT INTO font_assets VALUES (?, ?, ?, ?)", (font_id, name, mime, data))
