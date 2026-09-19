from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel, Field, SecretStr

router = APIRouter()

class Connection(BaseModel):
    url: str = Field(min_length=1, max_length=2048)
    api_key: SecretStr

@router.get("/api/youtube/status")
async def status(request: Request):
    return request.app.state.youtube.snapshot()

@router.post("/api/youtube/connect")
async def connect(payload: Connection, request: Request):
    try:
        return await request.app.state.youtube.start(payload.url, payload.api_key.get_secret_value().strip())
    except ValueError:
        raise HTTPException(422, "配信URLとAPIキーの形式を確認してください") from None

@router.post("/api/youtube/disconnect")
async def disconnect(request: Request):
    return await request.app.state.youtube.stop()
