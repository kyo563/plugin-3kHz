import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.services.state_change_cooldown_service import StateChangeCooldownService


def _state(cooldown_seconds=40):
    return {"cooldown_seconds": cooldown_seconds, "user_action_locks": {}, "declared_player_name": "x"}


def test_lock_and_unlock_by_elapsed_time():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    service = StateChangeCooldownService(now_provider=lambda: now)
    state = _state()
    service.mark_changed(state, "u1")
    assert service.is_locked(state, "u1") is True

    later_service = StateChangeCooldownService(now_provider=lambda: now + timedelta(seconds=41))
    assert later_service.is_locked(state, "u1") is False


def test_clear_expired_removes_entries_and_other_users_not_affected():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    state = _state()
    state["user_action_locks"] = {
        "u1": (now - timedelta(seconds=1)).isoformat(),
        "u2": (now + timedelta(seconds=60)).isoformat(),
    }
    service = StateChangeCooldownService(now_provider=lambda: now)
    service.clear_expired(state)
    assert "u1" not in state["user_action_locks"]
    assert service.is_locked(state, "u2") is True


def test_non_positive_cooldown_disables_lock():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    service = StateChangeCooldownService(now_provider=lambda: now)
    state = _state(cooldown_seconds=0)
    service.mark_changed(state, "u1")
    assert service.is_locked(state, "u1") is False
