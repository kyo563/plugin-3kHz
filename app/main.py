from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.routes.control_api import router as control_api_router
from app.routes.overlay_api import router as overlay_api_router
from app.routes.pages import router as pages_router

app = FastAPI(title="待機列整理アプリ Mock")
BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

app.include_router(pages_router)
app.include_router(control_api_router)
app.include_router(overlay_api_router)
