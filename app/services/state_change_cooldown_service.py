from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Callable


class StateChangeCooldownService:
    def __init__(self, now_provider: Callable[[], datetime] | None = None) -> None:
        self._now_provider = now_provider or (lambda: datetime.now(timezone.utc))

    def _now(self) -> datetime:
        now = self._now_provider()
        if now.tzinfo is None:
            return now.replace(tzinfo=timezone.utc)
        return now

    def _cooldown_seconds(self, state: dict) -> int:
        return int(state.get("cooldown_seconds", 40))

    def clear_expired(self, state: dict) -> None:
        locks = state.setdefault("user_action_locks", {})
        now = self._now()
        expired_keys = []
        for user_id, expires_at_raw in locks.items():
            try:
                expires_at = datetime.fromisoformat(expires_at_raw)
            except (TypeError, ValueError):
                expired_keys.append(user_id)
                continue
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at <= now:
                expired_keys.append(user_id)

        for key in expired_keys:
            locks.pop(key, None)

    def is_locked(self, state: dict, user_id: str) -> bool:
        cooldown_seconds = self._cooldown_seconds(state)
        if cooldown_seconds <= 0:
            return False

        self.clear_expired(state)
        expires_at_raw = state.setdefault("user_action_locks", {}).get(user_id)
        if not expires_at_raw:
            return False

        try:
            expires_at = datetime.fromisoformat(expires_at_raw)
        except ValueError:
            state["user_action_locks"].pop(user_id, None)
            return False

        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        return expires_at > self._now()

    def mark_changed(self, state: dict, user_id: str) -> None:
        cooldown_seconds = self._cooldown_seconds(state)
        if cooldown_seconds <= 0:
            return

        expires_at = self._now() + timedelta(seconds=cooldown_seconds)
        state.setdefault("user_action_locks", {})[user_id] = expires_at.isoformat()


    def configure(self, state: dict, seconds: int) -> None:
        previous = self._cooldown_seconds(state)
        self.clear_expired(state)
        locks = state.setdefault("user_action_locks", {})
        if seconds == 0:
            locks.clear()
        else:
            # Preserve the original change time for active locks; never resurrect
            # expired locks when increasing the configured duration.
            for user_id, value in list(locks.items()):
                expiry = datetime.fromisoformat(value)
                if expiry.tzinfo is None:
                    expiry = expiry.replace(tzinfo=timezone.utc)
                adjusted = expiry + timedelta(seconds=seconds - previous)
                if adjusted <= self._now():
                    locks.pop(user_id, None)
                else:
                    locks[user_id] = adjusted.isoformat()
        state["cooldown_seconds"] = seconds
