from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
import hashlib
import json
import time

from app.dependencies import get_services

router = APIRouter()


@router.get("/api/overlay-state")
def api_overlay_state(request: Request = None):
    services = get_services(request)
    state = services.build_overlay_state()
    if request is None:
        return state
    if request.query_params.get("preview") != "1":
        with request.app.state.overlay_lock:
            request.app.state.overlay_seen = time.monotonic()
    encoded = json.dumps(state, ensure_ascii=False, sort_keys=True).encode("utf-8")
    encoded += str(len(services.persistence_service.list_fonts())).encode("ascii")
    etag = '"' + hashlib.sha256(encoded).hexdigest() + '"'
    headers = {"ETag": etag, "Cache-Control": "no-cache"}
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    return JSONResponse(state, headers=headers)
