from contextlib import asynccontextmanager
import os
from pathlib import Path

from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel, Field
from app.security import AccessKeys, LocalSecurityMiddleware
from threading import Lock
import time
from fastapi.staticfiles import StaticFiles
from starlette.responses import JSONResponse
from app.services.queue_service import ParticipationCountLimitError

from app.routes.comment_api import router as comment_api_router, development_router as comment_development_router
from app.routes.control_api import router as control_api_router, development_router as control_development_router
from app.routes.overlay_api import router as overlay_api_router
from app.routes.pages import router as pages_router
from app.routes.font_api import router as font_router
from app.routes.youtube_api import router as youtube_router
from app.services.youtube_chat import YouTubeChat
from app.services.application_services import ApplicationServices

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"


def create_app(*, db_path: str | None = None, desktop: bool | None = None,
               development: bool = False, services: ApplicationServices | None = None,
               access_keys: AccessKeys | None = None, desktop_config=None, onecomme: bool = False) -> FastAPI:
    # Resolve configuration once. Constructing/importing an app never opens SQLite.
    selected_db = str(Path(db_path or os.environ.get("WAITING_LIST_DB_PATH")
                           or "data/waiting_list.sqlite3").expanduser().resolve())
    selected_desktop = os.environ.get("WAITING_LIST_DESKTOP") == "1" if desktop is None else desktop

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        application.state.services = services if services is not None else ApplicationServices(
            db_path=selected_db, desktop=selected_desktop
        )
        application.state.youtube = YouTubeChat(application.state.services)
        if onecomme:
            from app.services.onecomme import OneCommeBridge
            application.state.onecomme = OneCommeBridge(application.state.services)
        try:
            yield
        finally:
            await application.state.youtube.stop()
            # SQLite connections close after each operation; release service/cache references.
            del application.state.services

    application = FastAPI(title="待機列整理アプリ", lifespan=lifespan)
    @application.exception_handler(ParticipationCountLimitError)
    async def count_limit_error(request: Request, exc: ParticipationCountLimitError):
        return JSONResponse({"detail": str(exc)}, status_code=409)

    application.state.access_keys = access_keys or AccessKeys()
    application.state.onecomme_mode = onecomme
    application.state.overlay_seen = None
    application.state.overlay_lock = Lock()
    application.state.started_at = time.monotonic()
    application.add_middleware(LocalSecurityMiddleware, keys=application.state.access_keys)
    application.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    application.include_router(pages_router)
    application.include_router(font_router)
    if onecomme:
        from app.routes.onecomme_api import router as onecomme_router
        application.include_router(onecomme_router)
    else:
        application.include_router(youtube_router)
    application.include_router(control_api_router)
    application.include_router(comment_api_router)
    application.include_router(overlay_api_router)
    if development:
        application.include_router(control_development_router)
        application.include_router(comment_development_router)

    @application.get("/api/capabilities")
    def capabilities():
        return {"development": development}

    @application.get("/api/obs-status")
    def obs_status(request: Request):
        appearance = application.state.services.persistence_service.get_state()["overlay_settings"]
        seen = application.state.overlay_seen
        return {"running": True, "overlay_url": str(request.base_url).rstrip("/") + "/overlay",
                "last_access_seconds": None if seen is None else round(time.monotonic() - seen, 1),
                "recommended_width": appearance["width"], "recommended_height": appearance["height"]}

    @application.post("/api/desktop/exit")
    def desktop_exit():
        callback = getattr(application.state, "request_exit", None)
        if callback is None:
            raise HTTPException(409, "デスクトップ起動時のみ終了できます")
        callback()
        return {"stopping": True}

    @application.post("/api/desktop/activate")
    def desktop_activate():
        callback = getattr(application.state, "request_activate", None)
        if callback is None:
            raise HTTPException(409, "デスクトップ画面の準備中です")
        callback()
        return {"activated": True}

    @application.post("/api/desktop/onboarding-complete")
    def complete_onboarding():
        if desktop_config is None:
            raise HTTPException(409, "デスクトップ起動時のみ利用できます")
        desktop_config.complete_onboarding()
        return {"completed": True}

    @application.get("/api/connection")
    def connection(request: Request):
        return {"receive_url": str(request.base_url).rstrip("/") + "/api/comments/receive",
                "ingest_key": application.state.access_keys.ingest,
                "control_url": str(request.base_url).rstrip("/") + "/control#key=" + application.state.access_keys.admin}

    class PortSettings(BaseModel):
        port: int = Field(ge=1024, le=65535)

    @application.get("/api/desktop-settings")
    def read_desktop_settings():
        return {"available": desktop_config is not None, "port": desktop_config.port if desktop_config else None, "onboarding_completed": desktop_config.onboarding_completed if desktop_config else True}

    @application.post("/api/desktop-settings")
    def write_desktop_settings(payload: PortSettings):
        if desktop_config is None:
            raise HTTPException(409, "デスクトップ起動時のみ設定できます")
        desktop_config.save_port(payload.port)
        return {"port": payload.port, "restart_required": True}

    return application


app = create_app()
