from fastapi import APIRouter, Request
from app.schemas.control_display import ControlDisplaySettings

router = APIRouter()


@router.get('/api/settings/control-display')
def get_display(request: Request):
    return request.app.state.services.persistence_service.get_control_display()


@router.post('/api/settings/control-display')
def save_display(payload: ControlDisplaySettings, request: Request):
    return request.app.state.services.persistence_service.save_control_display(payload.model_dump())
