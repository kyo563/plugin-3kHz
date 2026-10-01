from fastapi import APIRouter, Request
from app.services.setup_preferences import SetupPreferences

router = APIRouter()


@router.get('/api/setup')
def read_setup(request: Request):
    return request.app.state.setup_store.settings()


@router.post('/api/setup')
def save_setup(payload: SetupPreferences, request: Request):
    request.app.state.setup_store.write('setup', payload.model_dump())
    return payload
