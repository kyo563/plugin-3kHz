from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse, RedirectResponse

router = APIRouter()
BASE_DIR = Path(__file__).resolve().parents[2]
STATIC_DIR = BASE_DIR / "static"


@router.get("/")
def root():
    return RedirectResponse(url="/control", status_code=307)


@router.get("/control")
def control_page():
    return FileResponse(STATIC_DIR / "control.html")


@router.get("/overlay")
def overlay_page():
    return FileResponse(STATIC_DIR / "overlay.html")


@router.get("/settings")
def settings_page():
    return FileResponse(STATIC_DIR / "settings.html")
