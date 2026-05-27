import os
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))
os.environ["WAITING_LIST_DB_PATH"] = str(Path(__file__).resolve().parent / "tmp_routes.sqlite3")

from app import mock_state
from app.main import app
from app.routes.control_api import api_state
from app.routes.overlay_api import api_overlay_state


def setup_function():
    mock_state.reset_state()


def test_api_state_returns_control_view_state():
    data = api_state()

    assert "current" in data
    assert "waiting" in data
    assert "logs" in data


def test_api_overlay_state_returns_minimal_overlay_payload():
    data = api_overlay_state()

    assert set(data.keys()) == {"is_open", "now_view", "next_view", "queue_count", "queue_group_count"}

    assert "logs" not in data
    for section in ("now_view", "next_view"):
        for user in data[section]:
            assert "user_id" not in user
            assert "participation_count" not in user


def test_route_urls_are_unchanged():
    paths = {route.path for route in app.router.routes}

    assert "/" in paths
    assert "/control" in paths
    assert "/overlay" in paths
    assert "/settings" in paths
    assert "/api/state" in paths
    assert "/api/overlay-state" in paths
    assert "/api/mock/add" in paths
    assert "/api/mock/cancel" in paths
    assert "/api/mock/move-next" in paths
    assert "/api/mock/toggle-open" in paths
    assert "/api/mock/toggle-priority" in paths
    assert "/api/mock/reset" in paths
