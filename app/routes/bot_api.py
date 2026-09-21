from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from app.services.bot import BotSettings

router = APIRouter()


@router.get('/api/bot')
def status(request: Request):
    return request.app.state.bot.status()


@router.post('/api/bot/settings')
def settings(payload: BotSettings, request: Request):
    return request.app.state.bot.configure(payload)


class ClientDocument(BaseModel):
    installed: dict


@router.post('/api/bot/login')
def login(payload: ClientDocument, request: Request):
    try:
        return {'url': request.app.state.bot.begin_login(payload.model_dump())}
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None


@router.post('/api/bot/disconnect')
def disconnect(request: Request):
    return request.app.state.bot.disconnect()
