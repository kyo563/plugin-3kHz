from fastapi import APIRouter
from pydantic import BaseModel

from app import mock_state
from app.services.queue_service import QueueService

router = APIRouter()
_queue_service = QueueService()


class ReorderWaitingPayload(BaseModel):
    ordered_user_ids: list[str]


class UserIdPayload(BaseModel):
    user_id: str


class UpdateDeclaredPlayerNamePayload(BaseModel):
    user_id: str
    declared_player_name: str | None = None


@router.get("/api/state")
def api_state():
    return mock_state.build_view_state()


@router.post("/api/control/reorder-waiting")
def api_reorder_waiting(payload: ReorderWaitingPayload):
    mock_state._persistence_service.mutate_state(lambda s: _queue_service.reorder_waiting(s, payload.ordered_user_ids))
    return mock_state.build_view_state()


@router.post("/api/control/remove-user")
def api_remove_user(payload: UserIdPayload):
    mock_state._persistence_service.mutate_state(lambda s: _queue_service.remove_user_by_id(s, payload.user_id))
    return mock_state.build_view_state()


@router.post("/api/control/move-to-waiting-tail")
def api_move_to_waiting_tail(payload: UserIdPayload):
    mock_state._persistence_service.mutate_state(lambda s: _queue_service.move_user_to_waiting_tail(s, payload.user_id))
    return mock_state.build_view_state()


@router.post("/api/control/update-declared-player-name")
def api_update_declared_player_name(payload: UpdateDeclaredPlayerNamePayload):
    mock_state._persistence_service.mutate_state(
        lambda s: _queue_service.update_declared_player_name(s, payload.user_id, payload.declared_player_name)
    )
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
