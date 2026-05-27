from fastapi import APIRouter

from app import mock_state

router = APIRouter()


@router.get("/api/overlay-state")
def api_overlay_state():
    return mock_state.build_overlay_state()
