import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.schemas.comment import CommentReceiveResult, ReceivedComment
from app.services.comment_queue_apply_service import CommentQueueApplyService
from app.services.persistence_service import PersistenceService
from app.services.queue_service import QueueService
from app.services.user_identity_service import UserIdentityService


def _state(is_open=True):
    return {
        "is_open": is_open,
        "priority_mode": False,
        "cooldown_seconds": 40,
        "current": [],
        "waiting": [],
        "show_declared_player_name_on_overlay": False,
        "logs": [],
    }


def _comment(user_key="k1", message="参加希望", source="external", display_name="Aさん"):
    return ReceivedComment(
        source=source,
        externalMessageId=None,
        receivedAt="2026-01-01T00:00:00Z",
        displayName=display_name,
        userKey=user_key,
        message=message,
        badges={"owner": False, "moderator": False, "member": False},
    )


def _result(command="join", duplicate=False, declared=None):
    return CommentReceiveResult(status="accepted", duplicate=duplicate, command=command, declared_player_name=declared)


def test_rejoin_moves_to_waiting_tail_not_duplicated_and_updates_declared_name():
    p = PersistenceService(initial_state=_state())
    service = CommentQueueApplyService(p, QueueService(), UserIdentityService())

    c = _comment(user_key="same", display_name="Aさん")
    service.apply(c, _result("join", False, None))
    service.apply(_comment(user_key="same", display_name="Aさん改"), _result("join", False, "たなかたろう"))

    st = p.get_state()
    all_users = st["current"] + st["waiting"]
    assert len([u for u in all_users if u["user_id"] == all_users[-1]["user_id"]]) == 1
    assert st["waiting"][-1]["declared_player_name"] == "たなかたろう"


def test_duplicate_and_ignore_do_nothing():
    p = PersistenceService(initial_state=_state())
    service = CommentQueueApplyService(p, QueueService(), UserIdentityService())
    before = p.get_state()

    service.apply(_comment(), _result("join", True, None))
    service.apply(_comment(), _result("ignore", False, None))

    after = p.get_state()
    assert after["current"] == before["current"]
    assert after["waiting"] == before["waiting"]


def test_cancel_removes_target_user():
    p = PersistenceService(initial_state=_state())
    q = QueueService()
    u = UserIdentityService()
    service = CommentQueueApplyService(p, q, u)

    c = _comment(user_key="target")
    service.apply(c, _result("join", False, None))
    service.apply(c, _result("cancel", False, None))
    st = p.get_state()
    assert len(st["current"]) + len(st["waiting"]) == 0
