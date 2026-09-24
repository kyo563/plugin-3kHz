from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel, Field, model_validator
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


class Heartbeat(BaseModel):
    dropped: int = Field(default=0, ge=0)


@router.get("/api/onecomme/status")
def status(request: Request):
    return request.app.state.onecomme.snapshot()


@router.post("/api/onecomme/select")
def select(payload: Selection, request: Request):
    try:
        return request.app.state.onecomme.select(payload.frame_id)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None


@router.post("/api/onecomme/heartbeat")
def heartbeat(payload: Heartbeat, request: Request):
    request.app.state.onecomme.heartbeat(payload.dropped)
    return {"ok": True}


@router.post("/api/onecomme/comment")
def comment(payload: Event, request: Request):
    return request.app.state.onecomme.receive(payload.frame_id, payload.frame_name, payload.comment)
