"""Isolated visual review using the actual OneComme pages and services. Never shipped."""
from contextlib import asynccontextmanager
from pathlib import Path
import sys
import asyncio
from typing import Literal

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi import Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from pydantic import BaseModel, Field
import uvicorn
from app.main import create_app

DIRECTORY = ROOT / 'dist' / 'management-visual-review'
PORT = 18879
# Only a disposable, loopback-only review instance uses this public test key.
KEY = 'joinqueue-isolated-visual-review-only-20261001'
NAMES = ['こはく', 'みずき', 'さくら', 'ゆず', 'しろねこ', 'そら', 'なつめ', 'あおい', 'こむぎ', 'はる', 'ルナ', 'ひなた']
HANDLES = ['kohaku', 'mizuki', 'sakura', 'yuzu', 'shironeko', 'sora', 'natsume', 'aoi', 'komugi', 'haru', 'luna', 'hinata']


def seed(app, count):
    def update(state):
        people = []
        for i in range(count + 3):
            nickname = NAMES[i % len(NAMES)] + (f' {i // len(NAMES) + 1}' if i >= len(NAMES) else '')
            people.append({'user_id':f'review-{i}', 'display_name':nickname,
                'youtube_handle':f'@{HANDLES[i % len(HANDLES)]}_{i+1}', 'youtube_nickname':nickname,
                'declared_player_name': ['こはく丸', '', 'さくらもち', 'Yuzu', 'ねこさん'][i % 5],
                'onecomme_memo':['初参加・操作説明あり', '', '前回参加あり', '聞き専です', '長いメモの省略表示を確認するためのサンプルです'][i % 5],
                'participation_count':i % 4, 'avatar_url':None})
        state.update(current=people[:3], waiting=people[3:], is_open=True, priority_mode=True,
                     total_match_count=4, participation_history=[], participation_counts={},
                     logs=['目視確認用サンプル。実際の参加者・配信には影響しません。'])
    app.state.services.persistence_service.mutate_state(update)


def create_preview(directory=DIRECTORY):
    directory.mkdir(parents=True, exist_ok=True)
    app = create_app(db_path=str(directory / 'review.sqlite3'), desktop=True, onecomme=True)
    app.state.access_keys.admin = KEY
    app.state.bot_simulation = False
    original = app.router.lifespan_context

    def preview_stream():
        state = app.state.setup_store.read('review_stream', 'none')
        if state == 'none':
            app.state.onecomme.heartbeat(services=[])
            app.state.onecomme.heartbeat_at = 0
            return
        frames = [{'service_id':'sample-row','service_name':'いつもの麻雀配信','id':'demoLive001','name':'第1回 麻雀参加型配信（サンプル）',
                   'enabled':True,'url':'https://www.youtube.com/watch?v=demoLive001',
                   'start_time':None,'state':'live' if state == 'live' else 'upcoming'}]
        if state in ('next','third'):
            video, title = ('demoLive002','第2回') if state == 'next' else ('demoLive003','第3回')
            frames[0].update(id=video, name=f'{title} 麻雀参加型配信（サンプル）',url='https://www.youtube.com/watch?v='+video)
        if state == 'multiple':
            frames.append({**frames[0],'service_id':'sample-row-2','id':'demoLive002','name':'別の配信（確認用サンプル）','url':'https://www.youtube.com/watch?v=demoLive002'})
        if state == 'missing':
            frames = [{**frames[0],'service_id':'different-row','id':'demoLive004','name':'別の枠の配信','url':'https://www.youtube.com/watch?v=demoLive004'}]
        app.state.onecomme.heartbeat(services=frames)

    async def stream_loop():
        while True:
            preview_stream()
            await asyncio.sleep(1.5)

    @asynccontextmanager
    async def lifespan(app):
        async with original(app):
            # Stop the actual sender before any browser is served. Do not simulate a real login.
            app.state.bot.stop()
            if not app.state.setup_store.read('review_seeded', False):
                seed(app, 37)
                app.state.setup_store.write('review_seeded', True)
                app.state.setup_store.write('setup', {'completed':True,'deferred':False,'step':4,'use_bot':False,'use_obs':True})
            task = asyncio.create_task(stream_loop())
            try:
                yield
            finally:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
    app.router.lifespan_context = lifespan

    @app.middleware('http')
    async def isolate(request: Request, call_next):
        if request.url.path == '/api/onecomme/template':
            return JSONResponse({'detail':'確認用画面ではテンプレートを配布しません。'}, status_code=409)
        if request.method != 'GET' and request.url.path.startswith('/api/bot/') and not app.state.bot_simulation:
            safe_stop = False
            if request.method == 'POST' and request.url.path == '/api/bot/connection':
                try:
                    safe_stop = (await request.json()).get('action') == 'stop'
                except (ValueError, AttributeError):
                    pass
            if not safe_stop:
                return JSONResponse({'detail':'確認用画面ではBot接続・投稿は実行しません。'}, status_code=409)
        response = await call_next(request)
        if request.url.path in ('/control','/settings') and response.status_code == 200:
            body = b''.join([part async for part in response.body_iterator]).decode('utf-8')
            # Keep copy/drag links in this disposable instance, never the real plugin.
            body = body.replace('http://127.0.0.1:18765/', f'http://127.0.0.1:{PORT}/')
            banner = (ROOT/'scripts/preview/banner.html').read_text(encoding='utf-8')
            body = body.replace('</head>', '<link rel="stylesheet" href="/preview/review.css"></head>')
            body = body.replace('<body data-onecomme="true">', '<body data-onecomme="true">'+banner)
            body = body.replace('</body>', '<script src="/preview/review.js"></script></body>')
            headers = dict(response.headers)
            headers.pop('content-length', None)
            return HTMLResponse(body, headers=headers)
        return response

    @app.get('/preview/{asset}')
    def asset(asset: str):
        if asset not in ('review.css','review.js'):
            return JSONResponse({'detail':'Not found'},status_code=404)
        return FileResponse(ROOT/'scripts/preview'/asset)

    class Scenario(BaseModel):
        count: int = Field(ge=0, le=150, strict=True)

    @app.get('/preview-status')
    def preview_status():
        return {'preview':'joinqueue-isolated-visual-review','bot_posting':False,
                'bot_simulation':app.state.bot_simulation,
                'stream':app.state.setup_store.read('review_stream','none')}

    class BotSimulationAction(BaseModel):
        action: Literal['begin','moderator','approve','cancel']

    @app.post('/api/preview/bot')
    def simulate_bot(payload: BotSimulationAction):
        from scripts.preview.bot_simulation import PreviewBot
        if payload.action == 'begin':
            app.state.bot.stop()
            bot = PreviewBot(app.state.onecomme)
            app.state.bot = app.state.services.bot = app.state.onecomme.bot = bot
            app.state.bot_simulation = True
        elif not app.state.bot_simulation:
            raise HTTPException(409, '先にシミュレーションを開始してください。')
        elif payload.action == 'moderator':
            app.state.bot.moderator = True
        elif not app.state.bot.requested:
            raise HTTPException(409, '先に「配信チャンネルを接続」を押してください。')
        elif payload.action == 'approve':
            app.state.bot.approved = True
        elif payload.action == 'cancel':
            app.state.bot.approved = False
            app.state.bot.error = '認証がキャンセルされました（シミュレーション）。接続解除後にやり直してください。'
        return {'simulation':True, 'bot_posting':False}

    class PreviewStream(BaseModel):
        state: Literal['none','upcoming','live','multiple','next','third','missing']

    @app.post('/api/preview/stream')
    def stream(payload: PreviewStream):
        app.state.setup_store.write('review_stream',payload.state)
        preview_stream()
        return {'ok':True}

    @app.post('/api/preview/scenario')
    def scenario(payload: Scenario):
        seed(app,payload.count)
        return {'ok':True}
    return app


if __name__ == '__main__':
    print(f'Visual review: http://127.0.0.1:{PORT}/control#key={KEY}',flush=True)
    uvicorn.run(create_preview(),host='127.0.0.1',port=PORT,log_level='warning',access_log=False)
