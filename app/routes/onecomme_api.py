from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel, Field, model_validator, StrictBool, ConfigDict
from typing import Literal
import unicodedata
import io
import zipfile
from pathlib import Path
from fastapi.responses import Response
from app.schemas.comment import ReceivedComment

router = APIRouter()


@router.get('/api/onecomme/template')
def download_template():
    folder = Path(__file__).resolve().parents[2] / 'static' / 'onecomme-template'
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name in ('index.html', 'script.js', 'style.css', 'template.json', 'thumb.png'):
            archive.writestr('taikiretsu-display/' + name, (folder / name).read_bytes())
    return Response(output.getvalue(), media_type='application/zip', headers={
        'Content-Disposition': 'attachment; filename="Taikiretsu-Template.zip"'})


class Event(BaseModel):
    frame_id: str = Field(min_length=1, max_length=200)
    frame_name: str = Field(min_length=1, max_length=200)
    comment: ReceivedComment

    @model_validator(mode="after")
    def youtube_identity(self):
        if (self.comment.source != "youtube" or not self.comment.user_key.strip()
                or any(unicodedata.category(c) in ('Cc', 'Cf', 'Cs') for c in self.comment.user_key)):
            raise ValueError("わんコメが提供するYouTube利用者IDが必要です")
        if not self.comment.external_message_id:
            raise ValueError("コメントIDが必要です")
        return self


class Selection(BaseModel):
    frame_id: str = Field(default="", max_length=200)
    mode: Literal['auto','manual'] = 'manual'


class ServiceFrame(BaseModel):
    model_config = ConfigDict(extra='forbid')
    service_id: str = Field(min_length=1, max_length=200)
    id: str = Field(pattern=r'^(?:[A-Za-z0-9_-]{11})?$')
    name: str = Field(min_length=1, max_length=200)
    service_name: str = Field(default='', max_length=200)
    enabled: StrictBool
    url: str = Field(default='', max_length=100, pattern=r'^(?:https://www\.youtube\.com/watch\?v=[A-Za-z0-9_-]{11})?$')
    start_time: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    state: Literal['live','upcoming','unknown','ended'] = 'unknown'


class Heartbeat(BaseModel):
    dropped: int = Field(default=0, ge=0)
    services: list[ServiceFrame] | None = Field(default=None, max_length=32)


class RememberFrame(BaseModel):
    service_id: str = Field(min_length=1, max_length=200)


class Transition(BaseModel):
    video_id: str = Field(min_length=1, max_length=200)
    carry: StrictBool = False
    revision: int = Field(ge=0)


@router.post('/api/onecomme/remember')
def remember(payload: RememberFrame, request: Request):
    try:
        return request.app.state.onecomme.remember(payload.service_id)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None


@router.post('/api/onecomme/transition')
def transition(payload: Transition, request: Request):
    try:
        return request.app.state.onecomme.confirm_transition(payload.video_id, payload.carry, payload.revision)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None


@router.get("/api/onecomme/status")
def status(request: Request):
    return request.app.state.onecomme.snapshot()


@router.post("/api/onecomme/select")
def select(payload: Selection, request: Request):
    try:
        return request.app.state.onecomme.select(payload.frame_id, payload.mode)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None


@router.post("/api/onecomme/heartbeat")
def heartbeat(payload: Heartbeat, request: Request):
    request.app.state.onecomme.heartbeat(payload.dropped, None if payload.services is None else [s.model_dump() for s in payload.services])
    return {"ok": True}


@router.post("/api/onecomme/comment")
def comment(payload: Event, request: Request):
    return request.app.state.onecomme.receive(payload.frame_id, payload.frame_name, payload.comment)
