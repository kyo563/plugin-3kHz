"""Local font copies live inside the app-owned SQLite database, never OS fonts."""
import hashlib
import re
import struct
from urllib.parse import unquote
from fastapi import APIRouter, HTTPException, Request, Response
from app.dependencies import get_services

router = APIRouter()
MAX_FONT_BYTES = 32 * 1024 * 1024

def font_type(data):
    if len(data) < 12:
        raise ValueError('フォントファイルを確認できません')
    magic = data[:4]
    if magic in (b'\x00\x01\x00\x00', b'OTTO'):
        count = int.from_bytes(data[4:6], 'big')
        if not 1 <= count <= 256 or len(data) < 12 + count * 16:
            raise ValueError('フォントのテーブルが不正です')
        for i in range(count):
            _, _, offset, length = struct.unpack_from('>4sIII', data, 12 + 16*i)
            if offset < 12 + count*16 or offset + length > len(data):
                raise ValueError('フォントのテーブル範囲が不正です')
        return 'font/otf' if magic == b'OTTO' else 'font/ttf'
    if magic in (b'wOFF', b'wOF2'):
        minimum = 44 if magic == b'wOFF' else 48
        if len(data) < minimum or int.from_bytes(data[8:12], 'big') != len(data) or not 1 <= int.from_bytes(data[12:14], 'big') <= 256:
            raise ValueError('Webフォントのヘッダーが不正です')
        if int.from_bytes(data[16:20], 'big') > MAX_FONT_BYTES:
            raise ValueError('展開後のフォントが大きすぎます')
        return 'font/woff' if magic == b'wOFF' else 'font/woff2'
    raise ValueError('TTF・OTF・WOFF・WOFF2に対応しています（TTCは非対応）')

@router.get('/api/fonts')
def list_fonts(request: Request):
    return get_services(request).persistence_service.list_fonts()

@router.post('/api/fonts')
async def upload_font(request: Request):
    data = await request.body()
    if len(data) > MAX_FONT_BYTES:
        raise HTTPException(413, 'フォントは32 MiBまでです')
    name = unquote(request.headers.get('x-font-name', 'フォント'))
    name = name.replace('\\', '/').rsplit('/', 1)[-1][:120]
    if not name or any(ord(c) < 32 for c in name):
        raise HTTPException(422, 'ファイル名が不正です')
    try:
        mime = font_type(data)
        font_id = hashlib.sha256(data).hexdigest()
        get_services(request).persistence_service.store_font(font_id, name, mime, data)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {'id': font_id, 'name': name}

@router.get('/api/font-assets/{font_id}')
def font_asset(font_id: str, request: Request):
    if not re.fullmatch('[a-f0-9]{64}', font_id):
        raise HTTPException(404)
    row = get_services(request).persistence_service.get_font(font_id)
    if row is None:
        raise HTTPException(404, 'フォントがありません。設定画面から再登録してください')
    return Response(bytes(row['data']), media_type=row['mime'])
