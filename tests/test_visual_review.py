from fastapi.testclient import TestClient
from scripts.preview_onecomme import create_preview, KEY


def test_preview_uses_isolated_data_and_real_pages(tmp_path):
    with TestClient(create_preview(tmp_path), base_url='http://127.0.0.1') as client:
        assert client.get('/preview-status').json()['bot_posting'] is False
        assert client.post('/api/preview/scenario', json={'count':150}).status_code == 401
        client.headers['Authorization'] = 'Bearer ' + KEY
        assert len(client.get('/api/state').json()['waiting']) == 37
        assert client.post('/api/preview/scenario', json={'count':150}).status_code == 200
        assert len(client.get('/api/state').json()['waiting']) == 150
        assert client.post('/api/preview/scenario', json={'count':151}).status_code == 422
        assert 'visual-review' in client.get('/control').text
        assert 'settings-obs-panel' in client.get('/settings').text
        assert 'http://127.0.0.1:18765/' not in client.get('/settings').text
        assert client.get('/api/onecomme/template').status_code == 409
        assert client.get('/preview/missing.js').status_code == 404


def test_preview_blocks_bot_commands_but_allows_safe_stop(tmp_path):
    with TestClient(create_preview(tmp_path), base_url='http://127.0.0.1') as client:
        client.headers['Authorization'] = 'Bearer ' + KEY
        for command in ('connect','start','test','check','status'):
            assert client.post('/api/bot/connection', json={'action':command}).status_code == 409
        assert client.post('/api/bot/settings', json={}).status_code == 409
        assert client.post('/api/bot/connection', json={'action':'stop'}).status_code == 200
        assert client.app.state.bot.stopped.is_set()
