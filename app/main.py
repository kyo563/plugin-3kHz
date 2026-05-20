from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app import mock_state

app = FastAPI(title="待機列整理アプリ Mock")
BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
def root():
    return RedirectResponse(url="/control", status_code=307)


@app.get("/control")
def control_page():
    return FileResponse(STATIC_DIR / "control.html")


@app.get("/overlay")
def overlay_page():
    return FileResponse(STATIC_DIR / "overlay.html")


@app.get("/settings")
def settings_page():
    return FileResponse(STATIC_DIR / "settings.html")


@app.get("/api/state")
def api_state():
    return mock_state.build_view_state()


@app.post("/api/mock/add")
def api_add():
    mock_state.add_mock_user()
    return mock_state.build_view_state()


@app.post("/api/mock/cancel")
def api_cancel():
    mock_state.cancel_mock_user()
    return mock_state.build_view_state()


@app.post("/api/mock/move-next")
def api_move_next():
    mock_state.move_next()
    return mock_state.build_view_state()


@app.post("/api/mock/toggle-open")
def api_toggle_open():
    mock_state.toggle_open()
    return mock_state.build_view_state()


@app.post("/api/mock/toggle-priority")
def api_toggle_priority():
    mock_state.toggle_priority()
    return mock_state.build_view_state()


@app.post("/api/mock/reset")
def api_reset():
    mock_state.reset_state()
    return mock_state.build_view_state()
