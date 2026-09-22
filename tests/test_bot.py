from datetime import datetime, timezone
import json
import os
from pathlib import Path
import httpx
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.schemas.comment import ReceivedComment
from app.services.application_services import ApplicationServices
from app.services.onecomme import OneCommeBridge
from app.services.bot import AnnouncementBot, BotSettings, BotStore, BOT_ORIGIN, BOT_ID, BotError

class MemoryStore:
    def __init__(self): self.data = {}
    def read(self, key, default=None): return self.data.get(key, default)
    def write(self, key, value): self.data[key] = value

def comment(n, text='参加希望', message_id=None):
    return ReceivedComment(source='youtube', userKey='UC' + str(n).zfill(22), displayName='User' + str(n),
                           youtubeHandle='@user' + str(n), externalMessageId=message_id or str(n) + text, message=text,
                           receivedAt=datetime.now(timezone.utc).isoformat())

@pytest.fixture
def setup_bot(tmp_path):
    services = ApplicationServices(db_path=str(tmp_path/'queue.db'), desktop=True)
    bridge = OneCommeBridge(services)
    bridge.frames['abcdefghijk'] = 'Test'
    bridge.select('abcdefghijk'); bridge.heartbeat()
    sent, calls = [], []
    def transport(request):
        assert str(request.url).startswith(BOT_ORIGIN + '/')
        assert request.headers['Authorization'].startswith('Bearer ')
        calls.append(request)
        if request.url.path.endswith('/posts'):
            sent.append(json.loads(request.content))
            return httpx.Response(200, json={'status': 'sent'})
        if request.url.path.endswith('/start'):
            return httpx.Response(200, json={'authorizationUrl': BOT_ORIGIN + '/connect?session=test', 'confirmation': '1234abcd', 'expiresAt': 2000000000000})
        return httpx.Response(200, json={'status': 'connected', 'channelId': 'UC' + '9'*22,
                            'connectionId': '11111111-1111-4111-8111-111111111111', 'serviceEnabled': True})
    now = [100.0]
    bot = AnnouncementBot(services, bridge, MemoryStore(), client=httpx.Client(transport=httpx.MockTransport(transport)), clock=lambda: now[0])
    services.bot = bridge.bot = bot
    yield bot, bridge, services, now, sent, calls
    bot.stop()

def activate(bot):
    bot.command('connect'); bot.command('status'); bot.command('start')

def test_disabled_defaults_self_exclusion_persistence_and_no_google_secrets(setup_bot):
    bot, bridge, services, now, sent, calls = setup_bot
    own = comment(999); own.user_key = BOT_ID
    bridge.receive('abcdefghijk', 'Test', own); services.receive_comment(own)
    assert services.build_view_state()['current'] == []
    bot.tick(); assert not sent and not calls
    activate(bot)
    bot.configure(BotSettings(enabled=True, interval_minutes=15, announce_now=False))
    assert bot.store.data['shared_settings']['interval_minutes'] == 15
    assert bot.store.data['shared_settings']['enabled'] is False
    assert bot.device not in str(bot.status())
    restored = AnnouncementBot(services, bridge, bot.store, client=httpx.Client(transport=httpx.MockTransport(lambda r: pytest.fail('network'))))
    assert not restored.running and restored.settings.interval_minutes == 15
    restored.stop()
    bot.disconnect()
    assert bot.is_self(own) and not bot.status()['authenticated']
    assert not sent

def test_only_next_group_notifies_once_and_never_join_leave(setup_bot):
    bot, bridge, services, now, sent, calls = setup_bot
    activate(bot)
    for i in range(7): services.receive_comment(comment(i))
    bot.tick(); assert not sent
    services.move_next(); bot.tick()
    assert len(sent) == 1 and sent[0]['templateId'] == 'called'
    assert [u['handle'] for u in sent[0]['variables']['members']] == ['@user3', '@user4', '@user5']
    assert sent[0]['variables']['group'] == 2
    now[0] += 10; bot.announce(); bot.tick(); assert len(sent) == 1
    services.move_next(); bot.tick()
    assert len(sent[-1]['variables']['members']) == 1
    assert sent[-1]['variables']['group'] == 3

def test_sender_identity_waiting_rank_now_unknown_and_cooldown(setup_bot):
    bot, bridge, services, now, sent, calls = setup_bot
    activate(bot)
    for i in range(8): services.receive_comment(comment(i))
    bridge.receive('abcdefghijk', 'Test', comment(6, '@JoinQueueBot @user7 順番？'))
    bot.tick()
    assert sent[-1]['variables'] == {'name':'@user6','handle':'@user6','state':'waiting','position':4,'group':3}
    assert sent[-1]['recipient']['userId'] == comment(6).user_key
    now[0] += 10; bot.receive(comment(6, '@JoinQueueBot', 'again')); bot.tick(); assert len(sent) == 1
    bot.receive(comment(1, '@JoinQueueBot')); bot.tick(); assert sent[-1]['variables']['state'] == 'now'
    now[0] += 10; bot.receive(comment(50, '@JoinQueueBot')); bot.tick(); assert sent[-1]['variables']['state'] == 'not-queued'
    assert not bot.receive(comment(60, '@JoinQueueBot-other'))
    assert not bot.receive(comment(60, '@@JoinQueueBot'))

@pytest.mark.parametrize('mask', range(8))
def test_three_switches_all_combinations(setup_bot, mask):
    bot, bridge, services, now, sent, calls = setup_bot
    activate(bot)
    bot.configure(BotSettings(enabled=True, announce_now=bool(mask & 1), reply_position=bool(mask & 2), periodic=bool(mask & 4), interval_minutes=15))
    for i in range(6): services.receive_comment(comment(i))
    services.move_next(); bot.tick()
    now[0] += 10; bot.receive(comment(4, '@JoinQueueBot')); bot.tick()
    now[0] = 100 + 15*60; bot.tick()
    assert [s['templateId'] for s in sent] == [k for i,k in enumerate(('called','position','announcement')) if mask & (1 << i)]

def test_timer_counts_interval_off_on_sleep_stop_and_disconnect(setup_bot):
    bot, bridge, services, now, sent, calls = setup_bot
    activate(bot)
    for i in range(7): services.receive_comment(comment(i))
    bot.tick(); assert not sent
    now[0] += 1800; bot.tick()
    assert sent[-1]['variables'] == {'waitingCount':4,'groupCount':2,'groupSize':3}
    bot.configure(BotSettings(enabled=True, periodic=False, interval_minutes=15))
    now[0] += 1800; bot.tick(); assert len(sent) == 1 and bot.running
    bot.configure(BotSettings(enabled=True, periodic=True, interval_minutes=15))
    bot.tick(); now[0] += 899; bot.tick(); assert len(sent) == 1
    now[0] += 1; bot.tick(); assert len(sent) == 2
    now[0] += 5400; bot.tick(); assert len(sent) == 2
    bridge.heartbeat_at = 0; bot.tick(); assert not bot.running
    now[0] += 900; bot.tick(); assert len(sent) == 2

def test_no_replay_after_switch_off_and_no_old_google_auth_read(setup_bot):
    bot, bridge, services, now, sent, calls = setup_bot
    bot.store.data['credentials'] = {'refresh_token':'old-secret'}
    bot.store.data['settings'] = {'enabled':True, 'interval_minutes':10, 'guide':'old'}
    restored = AnnouncementBot(services, bridge, bot.store, client=httpx.Client(transport=httpx.MockTransport(lambda r: pytest.fail('network'))))
    assert not restored.running and restored.device is None and restored.settings.interval_minutes == 30
    assert 'old-secret' not in str(restored.status()); restored.stop()
    activate(bot); bot.receive(comment(6, '@JoinQueueBot'))
    bot.configure(BotSettings(enabled=True, reply_position=False))
    bot.configure(BotSettings(enabled=True)); now[0] += 10; bot.tick(); assert not sent
    assert bot.store.data['credentials']['refresh_token'] == 'old-secret'

def test_ambiguous_post_stops_and_never_retries(setup_bot):
    bot, bridge, services, now, sent, calls = setup_bot
    activate(bot); bot.receive(comment(6, '@JoinQueueBot'))
    attempts = []
    def fail(request):
        attempts.append(request); raise httpx.ReadTimeout('PRIVATE')
    bot.http.close(); bot.http = httpx.Client(transport=httpx.MockTransport(fail))
    bot.tick(); now[0] += 60; bot.tick()
    assert len(attempts) == 1 and not bot.running and 'PRIVATE' not in bot.error

def test_disconnect_failure_retains_key_and_redacts_provider_response(setup_bot):
    bot, bridge, services, now, sent, calls = setup_bot
    activate(bot); token = bot.device
    bot.http.close()
    bot.http = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500, json={'error':{'message':token}})))
    with pytest.raises(BotError): bot.disconnect()
    assert bot.device == token and bot.store.data['shared_device'] == token
    assert not bot.running and token not in str(bot.status())

def test_start_response_cannot_undo_concurrent_stop(setup_bot):
    bot, bridge, services, now, sent, calls = setup_bot
    bot.command('connect')
    def stop_during_check(request):
        bot.pause()
        return httpx.Response(200,json={'status':'connected','channelId':'UC'+'9'*22,'connectionId':'11111111-1111-4111-8111-111111111111','serviceEnabled':True})
    bot.http.close(); bot.http = httpx.Client(transport=httpx.MockTransport(stop_during_check))
    with pytest.raises(BotError): bot.command('start')
    assert not bot.running

@pytest.mark.skipif(os.name != 'nt', reason='Windows DPAPI')
def test_device_key_is_encrypted_without_touching_legacy_records(tmp_path):
    path = tmp_path/'bot.sqlite3'; store = BotStore(path)
    store.write('credentials', {'refresh_token':'legacy-test'})
    store.write('shared_device', 'device-test')
    assert store.read('shared_device') == 'device-test'
    assert b'device-test' not in path.read_bytes()
    store.write('shared_device', None)
    assert store.read('shared_device') is None
    assert store.read('credentials') == {'refresh_token':'legacy-test'}

def test_api_local_auth_legacy_endpoint_removed_and_disconnect_confirmation(tmp_path):
    with TestClient(create_app(db_path=str(tmp_path/'q'), desktop=True, onecomme=True), base_url='http://127.0.0.1') as c:
        assert c.get('/api/bot').status_code == 401
        c.headers['Authorization'] = 'Bearer ' + c.app.state.access_keys.ingest
        assert c.post('/api/bot/connection', json={'action':'connect'}).status_code == 401
        c.headers['Authorization'] = 'Bearer ' + c.app.state.access_keys.admin
        assert c.post('/api/bot/settings', json={'interval_minutes':10}).status_code == 422
        assert c.post('/api/bot/settings', json={'enabled':True}).status_code == 422
        assert c.post('/api/bot/settings', json={'periodic':'false'}).status_code == 422
        assert c.post('/api/bot/login', json={'installed':{}}).status_code == 404
        assert c.post('/api/bot/disconnect', json={}).status_code == 422
        assert c.post('/api/bot/connection', json={'action':'stop','url':'https://evil.invalid'}).status_code == 422
        html = c.get('/bot').text
        assert '0.1.2' in html and 'id="bot-client"' not in html
    with TestClient(create_app(db_path=str(tmp_path/'old'), desktop=True), base_url='http://127.0.0.1') as c:
        c.headers['Authorization'] = 'Bearer ' + c.app.state.access_keys.admin
        assert c.get('/api/bot').status_code == 404 and c.get('/bot').status_code == 404
