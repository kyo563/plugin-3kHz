import os
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))
os.environ["WAITING_LIST_DB_PATH"] = str(Path(__file__).resolve().parent / "tmp_control_api.sqlite3")

from app import mock_state
from app.routes.control_api import (
    ReorderWaitingPayload,
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
