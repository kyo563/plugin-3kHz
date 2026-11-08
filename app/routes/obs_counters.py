from fastapi import APIRouter, Request
from fastapi.responses import FileResponse

from app.dependencies import get_services
from app.routes.overlay_api import mark_overlay_seen
from app.routes.pages import STATIC_DIR
from app.schemas.obs_counters import COUNTER_TOKENS, CounterKind, ObsCounterSettings


router = APIRouter()


@router.get("/onecomme-counter/{kind}")
def counter_page(kind: CounterKind):
    return FileResponse(STATIC_DIR / "obs-counter.html")


@router.get("/api/obs-counters")
def counter_display(request: Request):
    state = get_services(request).persistence_service.get_state()
    settings = ObsCounterSettings.model_validate(state.get("obs_counter_settings", {}))
    unique = len({user["user_id"] for session in state["participation_history"] for user in session["users"]})
    round_text = ""
    if any(user.get("user_id") and not user.get("is_placeholder") for user in state["current"]):
        round_text = settings.round.replace(COUNTER_TOKENS["round"], str(state["total_match_count"] + 1))
    overlay = state["overlay_settings"]
    appearance = {key: overlay[key] for key in ("font_size", "text_color", "background_color", "background_transparency",
                                                "auto_fit_font", "text_bold", "text_shadow")}
    appearance["fonts"] = {key: overlay["fonts"][key] for key in ("all", "obs_all", "summary")}
    mark_overlay_seen(request)
    return {
        "round": round_text,
        "unique": settings.unique.replace(COUNTER_TOKENS["unique"], str(unique)),
        "appearance": appearance,
    }


@router.get("/api/settings/obs-counters")
def counter_settings(request: Request):
    state = get_services(request).persistence_service.get_state()
    defaults = ObsCounterSettings().model_dump()
    return {"wording": state.get("obs_counter_settings", defaults), "defaults": defaults}


@router.post("/api/settings/obs-counters")
def save_counter_settings(payload: ObsCounterSettings, request: Request):
    wording = payload.model_dump()
    store = get_services(request).persistence_service
    with store.serialized():
        if store.get_state().get("obs_counter_settings", ObsCounterSettings().model_dump()) != wording:
            store.mutate_state(lambda state: state.update(obs_counter_settings=wording))
    return wording
