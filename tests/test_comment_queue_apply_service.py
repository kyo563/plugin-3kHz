import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.schemas.comment import CommentReceiveResult, ReceivedComment
from app.services.comment_queue_apply_service import CommentQueueApplyService
from app.services.persistence_service import PersistenceService
from app.services.queue_service import QueueService
from app.services.state_change_cooldown_service import StateChangeCooldownService
from app.services.user_identity_service import UserIdentityService


class MutableNow:
    def __init__(self, now: datetime):
        self.now = now


def _state(is_open=True):
    return {
        "is_open": is_open,
        "priority_mode": False,
        "cooldown_seconds": 40,
        "current": [],
        "waiting": [],
        "show_declared_player_name_on_overlay": False,
        "user_action_locks": {},
        "participation_counts": {},
        "logs": [],
    }


def _comment(user_key="k1", message="参加希望", source="external", display_name="Aさん"):
    return ReceivedComment(source=source, externalMessageId=None, receivedAt="2026-01-01T00:00:00Z", displayName=display_name, userKey=user_key, message=message, badges={"owner": False, "moderator": False, "member": False})


def _result(command="join", duplicate=False, declared=None):
    return CommentReceiveResult(status="accepted", duplicate=duplicate, command=command, declared_player_name=declared)


def _service(p, mutable_now):
    return CommentQueueApplyService(p, QueueService(), UserIdentityService(), StateChangeCooldownService(now_provider=lambda: mutable_now.now))


def test_join_then_immediate_cancel_is_ignored_by_lock():
    p = PersistenceService(initial_state=_state())
    clock = MutableNow(datetime(2026, 1, 1, tzinfo=timezone.utc))
    s = _service(p, clock)
    c = _comment(user_key="same")
    s.apply(c, _result("join"))
    s.apply(c, _result("cancel"))
    st = p.get_state()
    assert len(st["current"]) + len(st["waiting"]) == 1


def test_lock_expires_then_cancel_can_apply():
    p = PersistenceService(initial_state=_state())
    clock = MutableNow(datetime(2026, 1, 1, tzinfo=timezone.utc))
    s = _service(p, clock)
    c = _comment(user_key="same")
    s.apply(c, _result("join"))
    clock.now = datetime(2026, 1, 1, 0, 0, 41, tzinfo=timezone.utc)
    s.apply(c, _result("cancel"))
    st = p.get_state()
    assert len(st["current"]) + len(st["waiting"]) == 0


def test_lock_blocks_declared_name_update_for_rejoin():
    p = PersistenceService(initial_state=_state())
    clock = MutableNow(datetime(2026, 1, 1, tzinfo=timezone.utc))
    s = _service(p, clock)
    c = _comment(user_key="same")
    s.apply(c, _result("join"))
    s.apply(c, _result("join", declared="たなかたろう"))
    st = p.get_state()
    user = (st["current"] + st["waiting"])[0]
    assert user.get("declared_player_name") is None


def test_duplicate_ignore_closed_join_and_missing_cancel_do_not_set_lock():
    p = PersistenceService(initial_state=_state(is_open=False))
    clock = MutableNow(datetime(2026, 1, 1, tzinfo=timezone.utc))
    s = _service(p, clock)
    s.apply(_comment(user_key="d"), _result("join", duplicate=True))
    s.apply(_comment(user_key="i"), _result("ignore"))
    s.apply(_comment(user_key="j"), _result("join"))
    s.apply(_comment(user_key="c"), _result("cancel"))
    assert p.get_state().get("user_action_locks", {}) == {}


def test_join_reflects_saved_participation_count_and_invalid_falls_back_zero():
    st = _state()
    identity = UserIdentityService()
    uid1 = identity.build_comment_user_id("external", "k1")
    uid2 = identity.build_comment_user_id("external", "k2")
    st["participation_counts"] = {uid1: 2, uid2: "bad"}
    p = PersistenceService(initial_state=st)
    clock = MutableNow(datetime(2026, 1, 1, tzinfo=timezone.utc))
    s = _service(p, clock)
    s.apply(_comment(user_key="k1"), _result("join"))
    user = (p.get_state()["current"] + p.get_state()["waiting"])[0]
    assert user["participation_count"] == 2

    clock.now = datetime(2026, 1, 1, 0, 0, 41, tzinfo=timezone.utc)
    s.apply(_comment(user_key="k2", display_name="Bさん"), _result("join"))
    users = p.get_state()["current"] + p.get_state()["waiting"]
    b = [u for u in users if u["display_name"] == "Bさん"][0]
    assert b["participation_count"] == 0
