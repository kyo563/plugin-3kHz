from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.dependencies import get_services

router = APIRouter()
development_router = APIRouter()


class ReorderWaitingPayload(BaseModel):
    ordered_user_ids: list[str] = Field(max_length=1000)


class UserIdPayload(BaseModel):
    user_id: str = Field(min_length=1, max_length=256)


class UpdateDeclaredPlayerNamePayload(BaseModel):
    user_id: str = Field(min_length=1, max_length=256)
    declared_player_name: str | None = Field(default=None, max_length=200)


@router.get("/api/state")
def api_state(request: Request = None):
    services = get_services(request)
    return services.build_view_state()


@router.post("/api/control/reorder-waiting")
def api_reorder_waiting(payload: ReorderWaitingPayload, request: Request = None):
    services = get_services(request)
    services.persistence_service.manual_mutate(lambda s: services.queue_service.reorder_waiting(s, payload.ordered_user_ids))
    return services.build_view_state()


@router.post("/api/control/remove-user")
def api_remove_user(payload: UserIdPayload, request: Request = None):
    services = get_services(request)
    services.persistence_service.manual_mutate(lambda s: services.queue_service.remove_user_by_id(s, payload.user_id))
    return services.build_view_state()


@router.post("/api/control/move-to-waiting-tail")
def api_move_to_waiting_tail(payload: UserIdPayload, request: Request = None):
    services = get_services(request)
    services.persistence_service.manual_mutate(lambda s: services.queue_service.move_user_to_waiting_tail(s, payload.user_id))
    return services.build_view_state()


@router.post("/api/control/update-declared-player-name")
def api_update_declared_player_name(payload: UpdateDeclaredPlayerNamePayload, request: Request = None):
    services = get_services(request)
    services.persistence_service.manual_mutate(
        lambda s: services.queue_service.update_declared_player_name(s, payload.user_id, payload.declared_player_name)
    )
    return services.build_view_state()


@router.post("/api/control/toggle-open")
def api_control_toggle_open(request: Request = None):
    services = get_services(request)
    services.toggle_open()
    return services.build_view_state()


@router.post("/api/control/toggle-priority")
def api_control_toggle_priority(request: Request = None):
    services = get_services(request)
    services.toggle_priority()
    return services.build_view_state()


@router.post("/api/control/move-next")
def api_control_move_next(request: Request = None):
    services = get_services(request)
    services.move_next()
    return services.build_view_state()


@router.post("/api/control/reset")
def api_control_reset(request: Request = None):
    services = get_services(request)
    services.reset_state()
    return services.build_view_state()


@development_router.post("/api/mock/add")
def api_add(request: Request = None):
    services = get_services(request)
    services.add_mock_user()
    return services.build_view_state()


@development_router.post("/api/mock/cancel")
def api_cancel(request: Request = None):
    services = get_services(request)
    services.cancel_mock_user()
    return services.build_view_state()


@development_router.post("/api/mock/move-next")
def api_move_next(request: Request = None):
    services = get_services(request)
    services.move_next()
    return services.build_view_state()


@development_router.post("/api/mock/toggle-open")
def api_toggle_open(request: Request = None):
    services = get_services(request)
    services.toggle_open()
    return services.build_view_state()


@development_router.post("/api/mock/toggle-priority")
def api_toggle_priority(request: Request = None):
    services = get_services(request)
    services.toggle_priority()
    return services.build_view_state()


@development_router.post("/api/mock/reset")
def api_reset(request: Request = None):
    services = get_services(request)
    services.reset_state()
    return services.build_view_state()


@router.post('/api/settings/toggle-overlay-player-name')
def api_toggle_overlay_player_name(request: Request = None):
    services = get_services(request)
    services.toggle_overlay_player_name()
    return services.build_view_state()


# Operator tools use the same authenticated boundary as other control operations.
from fastapi import HTTPException, Response
from pydantic import ValidationError
from app.schemas.backup import RestorePayload, Name, Count
from app.services.operator_service import add_participant, correct_count, export_backup

class AddParticipantPayload(BaseModel):
    display_name: Name
    user_id: str | None = Field(default=None, max_length=256)

class CorrectCountPayload(UserIdPayload):
    participation_count: Count

@router.post("/api/control/add-user")
def api_add_user(payload: AddParticipantPayload, request: Request):
    services = get_services(request)
    add_participant(services, payload.display_name, payload.user_id)
    return services.build_view_state()

@router.post("/api/control/correct-count")
def api_correct_count(payload: CorrectCountPayload, request: Request):
    services = get_services(request)
    correct_count(services, payload.user_id, payload.participation_count)
    return services.build_view_state()

@router.post("/api/control/undo")
def api_undo(request: Request):
    services = get_services(request)
    try:
        services.persistence_service.undo()
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return services.build_view_state()

@router.get("/api/control/backup")
def api_backup(request: Request):
    try:
        data = export_backup(get_services(request)).model_dump_json().encode("utf-8")
    except ValidationError as exc:
        raise HTTPException(409, "現在のデータはバックアップ形式の上限外です") from exc
    if len(data) > 4 * 1024 * 1024 - 1024:
        raise HTTPException(409, "バックアップのサイズ上限（4 MiB）を超えています")
    return Response(data, media_type="application/json", headers={
        "Content-Disposition": 'attachment; filename="waiting-list-backup.json"'})

@router.post("/api/control/restore")
def api_restore(payload: RestorePayload, request: Request):
    services = get_services(request)
    state = payload.backup.state.model_dump()
    state["user_action_locks"] = {}
    state["logs"].append("バックアップを復元しました")
    with services.comment_lock:
        try:
            services.persistence_service.restore(state, payload.expected_revision)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
    return services.build_view_state()


from app.schemas.overlay_settings import OverlaySettings

@router.get("/api/settings/overlay")
def api_get_overlay_settings(request: Request):
    return get_services(request).persistence_service.get_state()["overlay_settings"]

@router.post("/api/settings/overlay")
def api_save_overlay_settings(payload: OverlaySettings, request: Request):
    services = get_services(request)
    services.persistence_service.mutate_state(lambda s: s.update(overlay_settings=payload.model_dump()))
    return payload.model_dump()


from app.schemas.description import DescriptionSettings

@router.get("/api/settings/description")
def api_get_description(request: Request):
    return {"text": get_services(request).persistence_service.get_state()["description_text"]}

@router.post("/api/settings/description")
def api_save_description(payload: DescriptionSettings, request: Request):
    get_services(request).persistence_service.mutate_state(lambda s: s.update(description_text=payload.text))
    return payload.model_dump()


class HistoryStartPayload(BaseModel):
    label: str = Field(default="", max_length=100)

@router.get("/api/control/history")
def participation_history(request: Request):
    return {"sessions": get_services(request).persistence_service.get_state().get("participation_history", [])}

@router.post("/api/control/history/start")
def start_history(payload: HistoryStartPayload, request: Request):
    from app.services.participation_history import new_session
    services = get_services(request)
    try:
        services.persistence_service.manual_mutate(lambda state: new_session(state, payload.label))
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return participation_history(request)


class CooldownSettings(BaseModel):
    cooldown_seconds: int = Field(strict=True, ge=0, le=3600)

@router.get("/api/settings/comments")
def comment_settings(request: Request):
    return {"cooldown_seconds": get_services(request).persistence_service.get_state()["cooldown_seconds"]}

@router.post("/api/settings/comments")
def save_comment_settings(payload: CooldownSettings, request: Request):
    from app.services.state_change_cooldown_service import StateChangeCooldownService
    service = StateChangeCooldownService()
    get_services(request).persistence_service.mutate_state(lambda state: service.configure(state, payload.cooldown_seconds))
    return payload.model_dump()
