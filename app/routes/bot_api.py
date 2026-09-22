from fastapi import APIRouter, Request, HTTPException
from typing import Literal
from pydantic import BaseModel, ConfigDict
from app.services.bot import BotSettings

router = APIRouter()


@router.get('/api/bot')
def status(request: Request):
    return request.app.state.bot.status()


@router.post('/api/bot/settings')
def settings(payload: BotSettings, request: Request):
    try:
        return request.app.state.bot.configure(payload)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    except Exception:
        raise HTTPException(503, '設定を保存できませんでした。') from None


class Command(BaseModel):
    model_config = ConfigDict(extra='forbid')
    action: Literal['connect', 'status', 'check', 'start', 'stop']


@router.post('/api/bot/connection')
def connection(payload: Command, request: Request):
    try:
        return request.app.state.bot.command(payload.action)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None


class Disconnect(BaseModel):
    model_config = ConfigDict(extra='forbid')
    confirmation: Literal['接続を解除']


@router.post('/api/bot/disconnect')
def disconnect(payload: Disconnect, request: Request):
    try:
        return request.app.state.bot.disconnect()
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
