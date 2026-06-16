import os
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))
os.environ["WAITING_LIST_DB_PATH"] = str(Path(__file__).resolve().parent / "tmp_routes.sqlite3")

from app import mock_state
from app.main import app
from app.routes.comment_api import router as comment_api_router
from app.routes.control_api import api_state, router as control_api_router
from app.routes.overlay_api import api_overlay_state, router as overlay_api_router
from app.routes.pages import router as pages_router


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
    routers = (pages_router, control_api_router, comment_api_router, overlay_api_router)
    paths = {route.path for router in routers for route in router.routes}

    assert "/" in paths
    assert "/control" in paths
    assert "/overlay" in paths
    assert "/settings" in paths
    assert "/api/state" in paths
    assert "/api/overlay-state" in paths
    assert "/api/control/toggle-open" in paths
    assert "/api/control/toggle-priority" in paths
    assert "/api/control/move-next" in paths
    assert "/api/control/reset" in paths
    assert "/api/mock/add" in paths
    assert "/api/mock/cancel" in paths
    assert "/api/mock/move-next" in paths
    assert "/api/mock/toggle-open" in paths
    assert "/api/mock/toggle-priority" in paths
    assert "/api/mock/reset" in paths
    assert "/api/settings/toggle-overlay-player-name" in paths


def test_overlay_state_hides_internal_fields_and_formats_display_name():
    state = mock_state._persistence_service.get_state()
    state["current"] = [{"user_id": "u1", "display_name": "Aさん", "declared_player_name": "たなかたろう", "participation_count": 1}]
    state["waiting"] = []
    state["show_declared_player_name_on_overlay"] = False
    mock_state._persistence_service.set_state(state)

    off = api_overlay_state()
    assert off["now_view"][0]["display_name"] == "Aさん"
    for key in ["show_declared_player_name_on_overlay", "declared_player_name", "user_id", "participation_count", "logs", "current", "waiting", "priority_mode", "cooldown_seconds"]:
        assert key not in off

    mock_state.toggle_overlay_player_name()
    on = api_overlay_state()
    assert on["now_view"][0]["display_name"] == "Aさん（たなかたろう）"


def test_overlay_state_payload_keeps_placeholder_and_hides_internal_fields():
    data = api_overlay_state()

    assert set(data.keys()) == {"is_open", "now_view", "next_view", "queue_count", "queue_group_count"}
    for forbidden in [
        "user_id",
        "declared_player_name",
        "participation_count",
        "participation_counts",
        "logs",
        "current",
        "waiting",
        "priority_mode",
        "cooldown_seconds",
        "show_declared_player_name_on_overlay",
        "user_action_locks",
    ]:
        assert forbidden not in data

    placeholder = data["now_view"][-1]
    assert placeholder == {"display_name": mock_state.OPEN_SLOT_LABEL, "is_placeholder": True}


def test_overlay_static_files_keep_safe_display_behavior():
    root = Path(__file__).resolve().parents[1]
    overlay_html = (root / "static" / "overlay.html").read_text(encoding="utf-8")
    overlay_css = (root / "static" / "overlay.css").read_text(encoding="utf-8")
    overlay_js = (root / "static" / "overlay.js").read_text(encoding="utf-8")

    assert 'classList.add("placeholder")' in overlay_js
    assert "status-open" in overlay_js
    assert "status-closed" in overlay_js
    assert "text-overflow: ellipsis" in overlay_css
    assert ".name.placeholder" in overlay_css
    assert "min-width: 0" in overlay_css
    assert "<button" not in overlay_html.lower()
    assert "<input" not in overlay_html.lower()


def test_settings_static_files_describe_mvp_settings_without_mock_controls():
    root = Path(__file__).resolve().parents[1]
    settings_html = (root / "static" / "settings.html").read_text(encoding="utf-8")
    settings_js = (root / "static" / "settings.js").read_text(encoding="utf-8")

    assert "設定画面（モック）" not in settings_html
    assert "設定画面" in settings_html
    for text in ["参加希望", "参加辞退", "参加を辞退", "参加希望者", "参加希望順"]:
        assert text in settings_html
    assert "現行MVPでは固定" in settings_html
    assert "<input" not in settings_html.lower()
    assert "<select" not in settings_html.lower()

    assert "/api/settings/toggle-overlay-player-name" in settings_js
    assert "/api/state" in settings_js
    assert "show_declared_player_name_on_overlay" in settings_js
    for text in ["読込中", "ON", "OFF", "取得失敗"]:
        assert text in settings_js
    assert "catch" in settings_js
