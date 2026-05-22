import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app import mock_state


def setup_function():
    mock_state.reset_state()


def test_now_view_and_next_view_are_padded_to_group_size():
    view = mock_state.build_view_state()

    assert len(view["now_view"]) == mock_state.GROUP_SIZE
    assert len(view["next_view"]) == mock_state.GROUP_SIZE
    assert view["now_view"][-1]["display_name"] == mock_state.OPEN_SLOT_LABEL


def test_queue_count_excludes_next_users():
    view = mock_state.build_view_state()

    assert view["queue_count"] == 1
    assert view["queue_group_count"] == 1
    assert len(view["queue_view"]) == 1


def test_add_mock_user_does_not_change_state_when_closed():
    before = mock_state.build_view_state()
    mock_state.toggle_open()
    mock_state.add_mock_user()
    after = mock_state.build_view_state()

    assert len(after["current"]) == len(before["current"])
    assert len(after["waiting"]) == len(before["waiting"])


def test_priority_mode_demotes_higher_participation_user_only():
    mock_state.state["current"] = [
        {"user_id": "c1", "display_name": "C1", "participation_count": 0},
        {"user_id": "c2", "display_name": "C2", "participation_count": 0},
        {"user_id": "c3", "display_name": "C3", "participation_count": 0},
    ]
    mock_state.state["waiting"] = [
        {"user_id": "w1", "display_name": "W1", "participation_count": 0},
        {"user_id": "w2", "display_name": "W2", "participation_count": 0},
        {"user_id": "w3", "display_name": "W3", "participation_count": 2},
        {"user_id": "w4", "display_name": "W4", "participation_count": 0},
    ]

    mock_state.add_mock_user()

    waiting_ids = [u["user_id"] for u in mock_state.state["waiting"]]
    assert waiting_ids[:4] == ["w1", "w2", "test1", "w3"]


def test_overlay_state_hides_sensitive_fields():
    overlay = mock_state.build_overlay_state()

    forbidden_top_level_keys = {
        "logs",
        "current",
        "waiting",
        "priority_mode",
        "cooldown_seconds",
        "total_waiting_count",
        "total_waiting_group_count",
        "queue_view",
    }
    for key in forbidden_top_level_keys:
        assert key not in overlay

    for section in ("now_view", "next_view"):
        for user in overlay[section]:
            assert set(user.keys()) <= {"display_name", "is_placeholder"}
            assert "user_id" not in user
            assert "participation_count" not in user
