import os
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))
os.environ["WAITING_LIST_DB_PATH"] = str(Path(__file__).resolve().parent / "tmp_control_api.sqlite3")

from app import mock_state
from app.routes.control_api import (
    ReorderWaitingPayload,
    api_add,
    api_cancel,
    api_control_move_next,
    api_control_reset,
    api_control_toggle_open,
    api_control_toggle_priority,
    api_move_next,
    api_reset,
    api_toggle_open,
    api_toggle_priority,
    UpdateDeclaredPlayerNamePayload,
    UserIdPayload,
    api_move_to_waiting_tail,
    api_remove_user,
    api_reorder_waiting,
    api_update_declared_player_name,
)
from app.routes.overlay_api import api_overlay_state


def setup_function():
    mock_state.reset_state()



def test_control_operation_endpoints_return_state():
    for operation in (
        api_control_toggle_open,
        api_control_toggle_priority,
        api_control_move_next,
        api_control_reset,
    ):
        mock_state.reset_state()
        state = operation()
        assert "current" in state and "waiting" in state


def test_control_move_next_increments_current_participation_counts():
    before = mock_state._persistence_service.get_state()
    current_ids = [u["user_id"] for u in before["current"]]

    api_control_move_next()

    after = mock_state._persistence_service.get_state()
    for user_id in current_ids:
        assert after["participation_counts"][user_id] == 1


def test_control_reset_clears_participation_counts():
    api_control_move_next()
    assert mock_state._persistence_service.get_state()["participation_counts"]

    state = api_control_reset()

    assert state["participation_counts"] == {}


def test_mock_operation_endpoints_still_return_state():
    for operation in (api_toggle_open, api_toggle_priority, api_move_next, api_add, api_cancel, api_reset):
        mock_state.reset_state()
        state = operation()
        assert "current" in state and "waiting" in state

def test_control_manual_operations_return_state():
    s1 = api_reorder_waiting(ReorderWaitingPayload(ordered_user_ids=["u4", "u3"]))
    assert "current" in s1 and "waiting" in s1

    s2 = api_remove_user(UserIdPayload(user_id="u3"))
    assert "current" in s2 and "waiting" in s2

    s3 = api_move_to_waiting_tail(UserIdPayload(user_id="u2"))
    assert "current" in s3 and "waiting" in s3

    s4 = api_update_declared_player_name(
        UpdateDeclaredPlayerNamePayload(user_id="u1", declared_player_name="たなか")
    )
    assert "current" in s4 and "waiting" in s4


def test_manual_operations_with_missing_user_id_do_not_raise_500_like_errors():
    s1 = api_remove_user(UserIdPayload(user_id="missing"))
    s2 = api_move_to_waiting_tail(UserIdPayload(user_id="missing"))
    s3 = api_update_declared_player_name(UpdateDeclaredPlayerNamePayload(user_id="missing", declared_player_name="abc"))
    assert "waiting" in s1 and "waiting" in s2 and "waiting" in s3


def test_overlay_state_stays_minimal_after_manual_operations():
    api_update_declared_player_name(UpdateDeclaredPlayerNamePayload(user_id="u1", declared_player_name="たなか"))
    overlay = api_overlay_state()

    assert set(overlay.keys()) == {"is_open", "now_view", "next_view", "queue_count", "queue_group_count"}
    assert "logs" not in overlay
    for section in ("now_view", "next_view"):
        for user in overlay[section]:
            assert "user_id" not in user
            assert "declared_player_name" not in user
            assert "participation_count" not in user
