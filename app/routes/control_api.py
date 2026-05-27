from fastapi import APIRouter

from app import mock_state

router = APIRouter()


@router.get("/api/state")
def api_state():
    return mock_state.build_view_state()


@router.post("/api/mock/add")
def api_add():
    mock_state.add_mock_user()
    return mock_state.build_view_state()


@router.post("/api/mock/cancel")
def api_cancel():
    mock_state.cancel_mock_user()
    return mock_state.build_view_state()


@router.post("/api/mock/move-next")
def api_move_next():
    mock_state.move_next()
    return mock_state.build_view_state()


@router.post("/api/mock/toggle-open")
def api_toggle_open():
    mock_state.toggle_open()
    return mock_state.build_view_state()


@router.post("/api/mock/toggle-priority")
def api_toggle_priority():
    mock_state.toggle_priority()
    return mock_state.build_view_state()


@router.post("/api/mock/reset")
def api_reset():
    mock_state.reset_state()
    return mock_state.build_view_state()


@router.post('/api/settings/toggle-overlay-player-name')
def api_toggle_overlay_player_name():
    mock_state.toggle_overlay_player_name()
    return mock_state.build_view_state()
