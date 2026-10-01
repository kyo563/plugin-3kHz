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
        assert client.post('/api/preview/stream',json={'state':'upcoming'}).status_code == 200
        stream=client.get('/api/onecomme/status').json()
        assert stream['selected']=='demoLive001' and stream['selection_mode']=='auto'
        assert stream['services'][0]['state']=='upcoming'
        assert client.post('/api/preview/stream',json={'state':'multiple'}).status_code == 200
        assert client.get('/api/onecomme/status').json()['selection_reason']=='remembered'


def test_preview_blocks_bot_commands_but_allows_safe_stop(tmp_path):
    with TestClient(create_preview(tmp_path), base_url='http://127.0.0.1') as client:
        client.headers['Authorization'] = 'Bearer ' + KEY
        for command in ('connect','start','test','check','status'):
            assert client.post('/api/bot/connection', json={'action':command}).status_code == 409
        assert client.post('/api/bot/settings', json={}).status_code == 409
        assert client.post('/api/bot/connection', json={'action':'stop'}).status_code == 200
        assert client.app.state.bot.stopped.is_set()


def test_public_bot_flow_simulates_locally_without_real_credentials_or_sender(tmp_path):
    with TestClient(create_preview(tmp_path), base_url='http://127.0.0.1') as client:
        assert client.post('/api/preview/bot', json={'action':'begin'}).status_code == 401
        client.headers['Authorization'] = 'Bearer ' + KEY
        client.post('/api/preview/bot', json={'action':'begin'}).raise_for_status()
        bot = client.app.state.bot
        assert not hasattr(bot, 'http') and not hasattr(bot, 'thread')
        def command(action):
            return client.post('/api/bot/connection', json={'action':action})
        command('connect').raise_for_status()
        assert command('status').json()['authenticated'] is False
        assert client.post('/api/preview/bot', json={'action':'cancel'}).status_code == 200
        assert command('start').status_code == 422
        client.post('/api/bot/disconnect',json={'confirmation':'接続を解除'}).raise_for_status()
        command('connect').raise_for_status()
        client.post('/api/preview/bot', json={'action':'approve'}).raise_for_status()
        assert command('status').json()['authenticated'] is True
        assert command('check').status_code == 422  # moderator missing
        client.post('/api/preview/bot',json={'action':'moderator'}).raise_for_status()
        client.post('/api/preview/stream',json={'state':'upcoming'}).raise_for_status()
        assert command('check').status_code == 422  # not live yet
        client.post('/api/preview/stream',json={'state':'live'}).raise_for_status()
        assert command('check').status_code == 200
        client.post('/api/bot/settings',json={'announce_now':True,'reply_position':True,'periodic':True,'interval_minutes':15}).raise_for_status()
        assert command('start').json()['ready'] is True
        assert client.get('/preview-status').json()['bot_posting'] is False
        assert command('test').status_code == 422
        assert client.get('/api/bot').json()['authorization_url'] is None
        client.post('/api/preview/stream',json={'state':'none'}).raise_for_status()
        assert client.get('/api/bot').json()['ready'] is False
        assert not client.app.state.services.bot.running
