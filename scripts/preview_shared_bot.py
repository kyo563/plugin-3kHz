"""Disposable UI fixture. No external requests, real credentials or user DBs."""
import json
from pathlib import Path
import sys
import tempfile
import time
import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.main import create_app
from app.security import AccessKeys
from desktop.runtime import LocalServer

with tempfile.TemporaryDirectory(prefix='queue-bot-ui-') as folder:
    keys = AccessKeys(admin='test-admin-' + 'a' * 43, ingest='test-ingest-' + 'b' * 43)
    app = create_app(db_path=str(Path(folder) / 'queue.db'), desktop=True, onecomme=True, access_keys=keys)
    with LocalServer(app, 18766) as server:
        bot = app.state.bot
        bot.http.close()
        def reply(request):
            if request.url.path.endswith('/posts'):
                return httpx.Response(200, json={'status': 'sent'})
            return httpx.Response(200, json={'status': 'connected', 'channelId': 'UC' + 'a' * 22,
                'connectionId': '11111111-1111-4111-8111-111111111111', 'serviceEnabled': True})
        bot.http = httpx.Client(transport=httpx.MockTransport(reply))
        bot.device = 't' * 43
        app.state.onecomme.frames['abcdefghijk'] = '架空のUI試験（実投稿なし）'
        app.state.onecomme.select('abcdefghijk')
        print(server.url + '/bot#key=' + keys.admin, flush=True)
        while True:
            app.state.onecomme.heartbeat()
            time.sleep(1)
