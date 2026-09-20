from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, RedirectResponse, HTMLResponse

router = APIRouter()
BASE_DIR = Path(__file__).resolve().parents[2]
STATIC_DIR = BASE_DIR / "static"


@router.get("/")
def root():
    return RedirectResponse(url="/control", status_code=307)


@router.get("/control")
def control_page(request: Request):
    if request.app.state.onecomme_mode:
        html = (STATIC_DIR / "control.html").read_text(encoding="utf-8")
        start = html.index('        <details id="youtube-panel"')
        end = html.index('        <div class="actions">', start)
        html = html[:start] + (STATIC_DIR / "onecomme-panel.html").read_text(encoding="utf-8") + html[end:]
        html = html.replace('/static/youtube.js', '/static/onecomme.js')
        html = html.replace('<h1>待機列管理</h1>', '<h1>待機列管理・わんコメ版（試作）</h1>')
        return HTMLResponse(html)
    return FileResponse(STATIC_DIR / "control.html")


@router.get("/overlay")
def overlay_page():
    return FileResponse(STATIC_DIR / "overlay.html")


@router.get("/settings")
def settings_page():
    return FileResponse(STATIC_DIR / "settings.html")


@router.get("/obs-setup")
def obs_setup_page():
    return FileResponse(STATIC_DIR / "obs-setup.html")
