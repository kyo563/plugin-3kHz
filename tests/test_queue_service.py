import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.services.queue_service import QueueService


def _base_state(is_open: bool = True) -> dict:
    return {
        "is_open": is_open,
        "current": [],
        "waiting": [],
        "logs": [],
        "priority_mode": False,
    }


def _user(user_id: str, display_name: str, declared_player_name=None, participation_count=0):
    return {
        "user_id": user_id,
        "display_name": display_name,
        "declared_player_name": declared_player_name,
        "participation_count": participation_count,
    }


def test_join_or_requeue_adds_new_user_normally():
    service = QueueService()
    state = _base_state()
    service.join_or_requeue_user_by_id(state, _user("u1", "Aさん"))
    assert len(state["current"]) == 1
    assert state["current"][0]["user_id"] == "u1"


def test_join_or_requeue_moves_user_from_current_to_waiting_tail():
    service = QueueService()
    state = _base_state()
    state["current"] = [_user("u1", "A旧", "旧名", 5), _user("u2", "B", None, 0), _user("u3", "C", None, 0)]
    state["waiting"] = [_user("u4", "D")]

    service.join_or_requeue_user_by_id(state, _user("u1", "A新"))

    assert [u["user_id"] for u in state["current"]] == ["u2", "u3"]
    assert state["waiting"][-1]["user_id"] == "u1"


def test_join_or_requeue_moves_user_from_waiting_next_to_tail():
    service = QueueService()
    state = _base_state()
    state["waiting"] = [_user("u1", "A"), _user("u2", "B"), _user("u3", "C"), _user("u4", "D")]

    service.join_or_requeue_user_by_id(state, _user("u2", "B新"))

    assert [u["user_id"] for u in state["waiting"]] == ["u1", "u3", "u4", "u2"]


def test_join_or_requeue_moves_user_from_waiting_back_to_tail():
    service = QueueService()
    state = _base_state()
    state["waiting"] = [_user("u1", "A"), _user("u2", "B"), _user("u3", "C"), _user("u4", "D"), _user("u5", "E")]

    service.join_or_requeue_user_by_id(state, _user("u5", "E新"))

    assert [u["user_id"] for u in state["waiting"]] == ["u1", "u2", "u3", "u4", "u5"]
    assert state["waiting"][-1]["display_name"] == "E新"


def test_join_or_requeue_updates_declared_player_name_when_provided():
    service = QueueService()
    state = _base_state()
    state["waiting"] = [_user("u1", "A", "旧名", 7)]

    service.join_or_requeue_user_by_id(state, _user("u1", "A", "新名"))

    assert state["waiting"][-1]["declared_player_name"] == "新名"


def test_join_or_requeue_keeps_declared_player_name_when_not_provided():
    service = QueueService()
    state = _base_state()
    state["waiting"] = [_user("u1", "A", "維持名", 7)]

    service.join_or_requeue_user_by_id(state, _user("u1", "A", None))

    assert state["waiting"][-1]["declared_player_name"] == "維持名"


def test_join_or_requeue_keeps_participation_count():
    service = QueueService()
    state = _base_state()
    state["waiting"] = [_user("u1", "A", "名", 9)]

    service.join_or_requeue_user_by_id(state, _user("u1", "A", "名"))

    assert state["waiting"][-1]["participation_count"] == 9


def test_join_or_requeue_does_not_change_order_when_closed():
    service = QueueService()
    state = _base_state(is_open=False)
    state["waiting"] = [_user("u1", "A", "名", 9), _user("u2", "B", None, 0)]

    service.join_or_requeue_user_by_id(state, _user("u1", "A新", "新名"))

    assert [u["user_id"] for u in state["waiting"]] == ["u1", "u2"]
    assert state["waiting"][0]["display_name"] == "A"
    assert state["waiting"][0]["declared_player_name"] == "名"
