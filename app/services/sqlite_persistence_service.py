from __future__ import annotations

import json
import os
import sqlite3
import threading
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

DEFAULT_DB_PATH = "data/waiting_list.sqlite3"


class SQLitePersistenceService:
    def __init__(self, initial_state: dict, db_path: str | None = None):
        self._initial_state = deepcopy(initial_state)
        self._db_path = db_path or os.getenv("WAITING_LIST_DB_PATH") or DEFAULT_DB_PATH
        self._lock = threading.RLock()
        self._ensure_parent_dir()
        self._initialize_schema()
        self._initialize_if_empty()

    def _ensure_parent_dir(self) -> None:
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

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
            columns = {row[1] for row in conn.execute("PRAGMA table_info(participants)").fetchall()}
            if "declared_player_name" not in columns:
                conn.execute("ALTER TABLE participants ADD COLUMN declared_player_name TEXT NULL")

    def _is_empty(self) -> bool:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS count FROM app_state").fetchone()
            return row["count"] == 0

    def _initialize_if_empty(self) -> None:
        if self._is_empty():
            self.set_state(deepcopy(self._initial_state))

    def get_state(self) -> dict:
        with self._connect() as conn:
            app_state_rows = conn.execute("SELECT key, value FROM app_state").fetchall()
            app_state = {row["key"]: row["value"] for row in app_state_rows}
            participants = conn.execute("""
                SELECT user_id, display_name, declared_player_name, status, participation_count, created_at, updated_at
                FROM participants
                ORDER BY status, position
                """).fetchall()
            logs = conn.execute("SELECT message FROM operation_logs ORDER BY id DESC LIMIT 30").fetchall()

        current, waiting = [], []
        for row in participants:
            user = {
                "user_id": row["user_id"],
                "display_name": row["display_name"],
                "declared_player_name": row["declared_player_name"],
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

        return {
            "is_open": app_state.get("is_open", "1") == "1",
            "priority_mode": app_state.get("priority_mode", "1") == "1",
            "cooldown_seconds": int(app_state.get("cooldown_seconds", "40")),
            "show_declared_player_name_on_overlay": app_state.get("show_declared_player_name_on_overlay", "0") == "1",
            "user_action_locks": user_action_locks,
            "current": current,
            "waiting": waiting,
            "logs": [row["message"] for row in reversed(logs)],
        }

    def set_state(self, state: dict) -> None:
        with self._lock:
            timestamp = self._now()
            with self._connect() as conn:
                conn.execute("DELETE FROM app_state")
                conn.executemany("INSERT INTO app_state(key, value) VALUES(?, ?)", [
                ("is_open", "1" if state["is_open"] else "0"),
                ("priority_mode", "1" if state["priority_mode"] else "0"),
                ("cooldown_seconds", str(state["cooldown_seconds"])),
                ("show_declared_player_name_on_overlay", "1" if state.get("show_declared_player_name_on_overlay", False) else "0"),
                ("user_action_locks", json.dumps(state.get("user_action_locks", {}), ensure_ascii=False)),
            ])
                conn.execute("DELETE FROM participants")
                for status in ("current", "waiting"):
                    for position, user in enumerate(state.get(status, [])):
                        if user.get("is_placeholder") or user.get("display_name") == "参加者募集中":
                            continue
                        conn.execute("""
                        INSERT INTO participants(user_id, display_name, declared_player_name, status, position, participation_count, created_at, updated_at)
                        VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                    """, (user["user_id"], user["display_name"], user.get("declared_player_name"), status, position, user.get("participation_count", 0), user.get("created_at", timestamp), timestamp))
                conn.execute("DELETE FROM operation_logs")
                for message in state.get("logs", [])[-30:]:
                    conn.execute("INSERT INTO operation_logs(message, created_at) VALUES(?, ?)", (message, timestamp))

    def reset_state(self) -> dict:
        with self._lock:
            self.set_state(deepcopy(self._initial_state))
            return self.get_state()

    def mutate_state(self, callback: Callable[[dict], None]) -> dict:
        with self._lock:
            state = self.get_state()
            callback(state)
            self.set_state(state)
            return state
