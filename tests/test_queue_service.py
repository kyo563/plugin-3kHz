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
        "participation_counts": {},
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


def test_reorder_waiting_reorders_by_user_id_and_keeps_rest_tail_order():
    service = QueueService()
    state = _base_state()
    state["current"] = [_user("c1", "C1")]
    state["waiting"] = [_user("u1", "A"), _user("u2", "B"), _user("u3", "C"), _user("u4", "D")]

    service.reorder_waiting(state, ["u3", "u1"])

    assert [u["user_id"] for u in state["waiting"]] == ["u3", "u1", "u2", "u4"]
    assert [u["user_id"] for u in state["current"]] == ["c1"]


def test_remove_user_by_id_removes_from_current_and_waiting_and_is_safe_when_missing():
    service = QueueService()
    state = _base_state()
    state["current"] = [_user("u1", "A")]
    state["waiting"] = [_user("u2", "B")]

    service.remove_user_by_id(state, "u1")
    assert [u["user_id"] for u in state["current"]] == []

    service.remove_user_by_id(state, "u2")
    assert [u["user_id"] for u in state["waiting"]] == []

    service.remove_user_by_id(state, "none")
    assert state["waiting"] == []


def test_move_user_to_waiting_tail_moves_from_current_or_waiting():
    service = QueueService()
    state = _base_state()
    state["current"] = [_user("u1", "A")]
    state["waiting"] = [_user("u2", "B"), _user("u3", "C")]

    service.move_user_to_waiting_tail(state, "u1")
    assert [u["user_id"] for u in state["current"]] == []
    assert [u["user_id"] for u in state["waiting"]] == ["u2", "u3", "u1"]

    service.move_user_to_waiting_tail(state, "u2")
    assert [u["user_id"] for u in state["waiting"]] == ["u3", "u1", "u2"]


def test_update_declared_player_name_updates_by_user_id_only():
    service = QueueService()
    state = _base_state()
    state["current"] = [_user("u1", "A", declared_player_name="x")]
    state["waiting"] = [_user("u2", "B", declared_player_name="same-name")]

    service.update_declared_player_name(state, "u1", "新しい申告名")
    assert state["current"][0]["declared_player_name"] == "新しい申告名"

    service.update_declared_player_name(state, "u1", "")
    assert state["current"][0]["declared_player_name"] is None

    service.update_declared_player_name(state, "u2", "a" * 40)
    assert state["waiting"][0]["declared_player_name"] == "a" * 32


def test_move_next_increments_participation_counts_for_current_only():
    service = QueueService()
    state = _base_state()
    state["current"] = [_user("u1", "A", participation_count=1), {"display_name": "参加者募集中", "is_placeholder": True}]
    state["waiting"] = [_user("u2", "B", participation_count=3)]
    state["participation_counts"] = {"u1": 2, "u2": 10}
    service.move_next(state)
    assert state["participation_counts"]["u1"] == 3
    assert state["participation_counts"]["u2"] == 10


def test_non_move_next_operations_do_not_increment_participation_counts():
    service = QueueService()
    state = _base_state()
    state["current"] = [_user("u1", "A", participation_count=1)]
    state["waiting"] = [_user("u2", "B", participation_count=1)]
    state["participation_counts"] = {"u1": 1, "u2": 1}
    service.cancel_user_by_id(state, "u2")
    service.remove_user_by_id(state, "u1")
    state["waiting"] = [_user("u3", "C")]
    service.move_user_to_waiting_tail(state, "u3")
    assert state["participation_counts"] == {"u1": 1, "u2": 1}
