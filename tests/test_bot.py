from datetime import datetime, timezone
import json
import os
import time
from pathlib import Path
import httpx
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.schemas.comment import ReceivedComment
from app.services.application_services import ApplicationServices
from app.services.onecomme import OneCommeBridge
from app.services.user_identity_service import UserIdentityService
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
            return httpx.Response(200, json=pairing_response())
        return httpx.Response(200, json={'status': 'connected', 'channelId': 'UC' + '9'*22,
                            'connectionId': '11111111-1111-4111-8111-111111111111', 'serviceEnabled': True, 'features':{'connectionTest':True}})
    now = [100.0]
    bot = AnnouncementBot(services, bridge, MemoryStore(), client=httpx.Client(transport=httpx.MockTransport(transport)), clock=lambda: now[0])
    services.bot = bridge.bot = bot
    yield bot, bridge, services, now, sent, calls
    bot.stop()

def activate(bot):
    bot.command('connect'); bot.command('status'); bot.command('start')


def pairing_response(now=None, identifier='1234abcd-1111-4111-8111-111111111111'):
    return {'authorizationUrl': BOT_ORIGIN + '/connect?id=' + identifier + '&key=' + 'k'*43,
            'confirmation': identifier[:8], 'expiresAt': int((time.time() if now is None else now)*1000) + 600000}


def replace_transport(bot, handler):
    bot.http.close()
    bot.http = httpx.Client(transport=httpx.MockTransport(handler))


@pytest.mark.parametrize('registered', [False, True])
@pytest.mark.parametrize('failure', ['timeout', 'server', 'invalid_response'])
def test_failed_pairing_start_can_retry_without_rotating_device(setup_bot, registered, failure):
    bot, bridge, services, now, sent, calls = setup_bot
    attempts = []
    def fail(request):
        attempts.append(request.url.path)
        if failure == 'timeout':
            raise httpx.ReadTimeout('PRIVATE_AUTH_URL')
        return httpx.Response(503 if failure == 'server' else 200,
                              json={'error': {'code': 'BOT_UNAVAILABLE', 'message': 'PRIVATE_AUTH_URL'}} if failure == 'server' else {})
    replace_transport(bot, fail)
    with pytest.raises(ValueError): bot.command('connect')
    device = bot.device
    assert device and bot.store.data['shared_device'] == device
    assert not bot.status()['authenticated'] and bot.status()['auth_state'] == 'unverified'
    assert 'PRIVATE_AUTH_URL' not in str(bot.status())
    def recover(request):
        attempts.append(request.url.path)
        assert request.headers['Authorization'] == 'Bearer ' + device
        if request.url.path.endswith('/status'):
            return httpx.Response(200, json={'status': 'pending', 'stage': 'new'}) if registered else httpx.Response(403, json={'error': {'code': 'UNAUTHENTICATED'}})
        return httpx.Response(200, json=pairing_response())
    replace_transport(bot, recover)
    result = bot.command('connect')
    assert result['auth_state'] == 'pending' and result['login_pending'] and not result['error']
    assert bot.device == device and bot.store.data['shared_pairing']['confirmation'] == result['confirmation']
    assert attempts == ['/v1/connections/start', '/v1/connections/status', '/v1/connections/start']
    assert not sent


def test_pending_link_and_confirmation_survive_restart_and_resume_without_reissuing(setup_bot):
    bot, bridge, services, now, sent, calls = setup_bot
    first = bot.command('connect')
    attempts = []
    def pending(request):
        attempts.append(request.url.path)
        return httpx.Response(200, json={'status': 'pending', 'stage': 'new'})
    restored = AnnouncementBot(services, bridge, bot.store, client=httpx.Client(transport=httpx.MockTransport(pending)))
    try:
        assert restored.status()['authorization_url'] == first['authorization_url']
        assert restored.status()['confirmation'] == first['confirmation']
        assert restored.command('connect')['auth_state'] == 'pending'
        assert attempts == ['/v1/connections/status']
        assert not restored.running and not sent
    finally: restored.stop()


@pytest.mark.parametrize('reason', ['expired', 'old_client', 'google_interrupted'])
def test_pending_authentication_can_reissue_after_expiry_or_lost_link(setup_bot, reason):
    bot, bridge, services, now, sent, calls = setup_bot
    bot.wall_clock = lambda: 1000
    replace_transport(bot, lambda r: httpx.Response(200, json=pairing_response(1000)))
    original = bot.command('connect')
    if reason == 'old_client': bot.store.data.pop('shared_pairing')
    attempts = []
    def recover(request):
        attempts.append(request.url.path)
        if request.url.path.endswith('/status'):
            if reason == 'expired': return httpx.Response(403, json={'error': {'code': 'UNAUTHENTICATED'}})
            return httpx.Response(200, json={'status': 'pending', 'stage': 'pending' if reason == 'google_interrupted' else 'new'})
        return httpx.Response(200, json=pairing_response(1700, '5678abcd-1111-4111-8111-111111111111'))
    restored = AnnouncementBot(services, bridge, bot.store, wall_clock=lambda: 1700,
                                client=httpx.Client(transport=httpx.MockTransport(recover)))
    try:
        assert restored.status()['authorization_url'] is None
        result = restored.command('connect')
        assert result['authorization_url'] != original['authorization_url']
        assert result['auth_state'] == 'pending' and restored.device == bot.device
        assert attempts == ['/v1/connections/status', '/v1/connections/start']
        assert not sent
    finally: restored.stop()


def test_connected_restart_or_pairing_completion_race_preserves_authentication(setup_bot):
    bot, bridge, services, now, sent, calls = setup_bot
    activate(bot)
    device = bot.device
    connected = {'status': 'connected', 'channelId': 'UC'+'9'*22,
                 'connectionId': '11111111-1111-4111-8111-111111111111', 'serviceEnabled': True}
    for race in (False, True):
        attempts = []
        def reply(request):
            attempts.append(request.url.path)
            if race and request.url.path.endswith('/status'): return httpx.Response(200, json={'status': 'pending', 'stage': 'pending'})
            return httpx.Response(200, json=connected)
        restored = AnnouncementBot(services, bridge, bot.store, client=httpx.Client(transport=httpx.MockTransport(reply)))
        try:
            result = restored.command('connect')
            assert result['authenticated'] and result['auth_state'] == 'authenticated'
            assert restored.device == device and not result['ready'] and not sent
            assert attempts == ['/v1/connections/status'] + (['/v1/connections/start'] if race else [])
            assert bot.store.data['shared_pairing'] is None
        finally: restored.stop()


def test_status_network_failure_keeps_device_valid_authentication_and_pending_links(setup_bot):
    bot, bridge, services, now, sent, calls = setup_bot
    bot.command('connect')
    for authenticated in (False, True):
        if authenticated:
            bot.connection = {'channelId': 'UC'+'9'*22, 'connectionId': '11111111-1111-4111-8111-111111111111'}
        device, connection, pairing = bot.device, bot.connection, bot.store.data['shared_pairing'].copy()
        replace_transport(bot, lambda r: (_ for _ in ()).throw(httpx.ConnectError('PRIVATE_DEVICE')))
        with pytest.raises(ValueError, match='再試行'): bot.command('connect')
        assert bot.device == device and bot.connection == connection and bot.store.data['shared_pairing'] == pairing
        assert 'PRIVATE_DEVICE' not in str(bot.status()) and not sent


def test_expired_link_hidden_and_pending_server_never_claims_bot_started(setup_bot):
    bot, bridge, services, now, sent, calls = setup_bot
    bot.wall_clock = lambda: 1000
    replace_transport(bot, lambda r: httpx.Response(200, json=pairing_response(1000)))
    bot.command('connect')
    bot.wall_clock = lambda: 1600
    assert bot.status()['auth_state'] == 'expired'
    assert bot.status()['authorization_url'] is None and bot.status()['confirmation'] is None
    replace_transport(bot, lambda r: httpx.Response(200, json={'status': 'pending', 'stage': 'pending'}))
    for action in ('check', 'start'):
        with pytest.raises(BotError, match='配信チャンネル'): bot.command(action)
        assert not bot.running and not bot.status()['authenticated'] and not sent


@pytest.mark.skipif(os.name != 'nt', reason='Windows DPAPI')
def test_pending_authorization_capability_is_dpapi_encrypted(tmp_path):
    path = tmp_path/'bot.sqlite3'
    store = BotStore(path)
    pairing = pairing_response()
    store.write('shared_pairing', pairing)
    assert store.read('shared_pairing') == pairing
    assert pairing['authorizationUrl'].encode() not in path.read_bytes()
    assert ('k'*43).encode() not in path.read_bytes()


def test_server_replaced_pairing_never_reuses_stale_locally_unexpired_url(setup_bot):
    bot, bridge, services, now, sent, calls = setup_bot
    previous = bot.command('connect')['authorization_url']
    attempts = []
    def recover(request):
        attempts.append(request.url.path)
        if request.url.path.endswith('/status'):
            return httpx.Response(200, json={'status': 'pending', 'stage': 'new',
                                          'pairingId': '5678abcd-1111-4111-8111-111111111111'})
        return httpx.Response(200, json=pairing_response(identifier='9876abcd-1111-4111-8111-111111111111'))
    replace_transport(bot, recover)
    result = bot.command('connect')
    assert result['authorization_url'] != previous and result['login_pending']
    assert attempts == ['/v1/connections/status', '/v1/connections/start'] and not sent


@pytest.mark.parametrize('damage', ['foreign_host', 'wrong_device', 'invalid_expiry'])
def test_bad_pending_record_does_not_lock_out_existing_device(setup_bot, damage):
    bot, bridge, services, now, sent, calls = setup_bot
    bot.command('connect')
    pairing = bot.store.data['shared_pairing'].copy()
    if damage == 'foreign_host': pairing['authorizationUrl'] = 'https://evil.invalid/connect'
    elif damage == 'wrong_device': pairing['deviceHash'] = 'different-device'
    else: pairing['expiresAt'] = True
    bot.store.data['shared_pairing'] = pairing
    connected = {'status': 'connected', 'channelId': 'UC'+'9'*22,
                 'connectionId': '11111111-1111-4111-8111-111111111111'}
    restored = AnnouncementBot(services, bridge, bot.store, client=httpx.Client(transport=httpx.MockTransport(
        lambda r: httpx.Response(200, json=connected))))
    try:
        assert restored.device == bot.device and not restored.storage_error
        assert restored.status()['authorization_url'] is None
        assert restored.command('connect')['authenticated']
        assert restored.device == bot.device and not restored.running and not sent
    finally: restored.stop()


@pytest.mark.skipif(os.name != 'nt', reason='Windows DPAPI')
def test_local_api_retry_and_restart_use_real_encrypted_database(tmp_path):
    database = str(tmp_path/'queue.db')
    headers = lambda app: {'Authorization': 'Bearer ' + app.state.access_keys.admin}
    def reply(request):
        if request.url.path.endswith('/status'):
            return httpx.Response(403, json={'error': {'code': 'UNAUTHENTICATED'}})
        return httpx.Response(200, json=pairing_response())
    with TestClient(create_app(db_path=database, desktop=True, onecomme=True), base_url='http://127.0.0.1') as client:
        client.headers.update(headers(client.app))
        bot = client.app.state.bot
        replace_transport(bot, lambda r: (_ for _ in ()).throw(httpx.ReadTimeout('PRIVATE')))
        failed = client.post('/api/bot/connection', json={'action': 'connect'})
        assert failed.status_code == 422 and '再試行' in failed.json()['detail']
        device = bot.device
        assert client.get('/api/bot').json()['has_connection_key']
        replace_transport(bot, reply)
        repaired = client.post('/api/bot/connection', json={'action': 'connect'}).json()
        assert repaired['auth_state'] == 'pending' and bot.device == device
    with TestClient(create_app(db_path=database, desktop=True, onecomme=True), base_url='http://127.0.0.1') as client:
        client.headers.update(headers(client.app))
        restored = client.get('/api/bot').json()
        assert restored['authorization_url'] == repaired['authorization_url']
        assert restored['confirmation'] == repaired['confirmation'] and not restored['ready']
        assert client.app.state.bot.device == device
        replace_transport(client.app.state.bot, lambda r: httpx.Response(200, json={
            'status': 'connected', 'channelId': 'UC'+'9'*22,
            'connectionId': '11111111-1111-4111-8111-111111111111'}))
        verified = client.post('/api/bot/connection', json={'action': 'status'}).json()
        assert verified['authenticated'] and verified['authorization_url'] is None
        assert not verified['ready'] and client.app.state.bot.store.read('shared_pairing') is None


@pytest.mark.parametrize('code, expected', [
    ('BOT_AUTH_EXPIRED', '共通BotのGoogle認証が期限切れ'),
    ('BOT_UNAVAILABLE', '共通Botの認証またはYouTube接続'),
    ('LIVE_NOT_ACTIVE', '終了済み・利用不可'),
    ('CHAT_UNAVAILABLE', 'YouTube公式APIで確認できません'),
    ('UNKNOWN_PRIVATE_CODE', '共通Botサーバーに接続できません'),
])
def test_server_bot_fault_is_distinct_from_network_and_keeps_connection(setup_bot, code, expected):
    bot, bridge, services, now, sent, calls = setup_bot
    bot.command('connect'); bot.command('status')
    device, connection = bot.device, bot.connection.copy()
    bot.http.close()
    attempts = []
    def reply(request):
        attempts.append(request)
        return httpx.Response(503, json={'error': {'code': code, 'message': 'PRIVATE_TOKEN'}})
    bot.http = httpx.Client(transport=httpx.MockTransport(reply))
    with pytest.raises(BotError, match=expected): bot.command('check')
    assert bot.device == device and bot.connection == connection
    assert not bot.running and len(attempts) == 1 and not sent
    assert 'PRIVATE_TOKEN' not in str(bot.status()) and code != bot.error


def test_optional_connection_test_works_while_stopped_and_is_throttled(setup_bot):
    bot, bridge, services, now, sent, calls = setup_bot
    bot.command('connect'); bot.command('status')
    before = services.build_view_state()
    assert sent == []
    result = bot.command('test')
    assert result['ready'] is False
    assert sent[0]['templateId'] == 'connection-test'
    assert sent[0]['variables'] == {}
    assert services.build_view_state() == before
    with pytest.raises(BotError, match='間隔'):
        bot.command('test')
    assert len(sent) == 1
    now[0] += 60
    bridge.select('')
    with pytest.raises(BotError): bot.command('test')
    assert len(sent) == 1


def test_upcoming_frame_can_check_without_posting_and_missing_frame_is_distinct(setup_bot):
    bot, bridge, services, now, sent, calls = setup_bot
    bot.command('connect'); bot.command('status')
    bridge.service_frames = [{'id': 'abcdefghijk', 'state': 'upcoming'}]
    before = services.build_view_state()
    assert bot.command('check')['authenticated']
    assert not bot.running and not sent and services.build_view_state() == before
    assert json.loads(calls[-1].content)['videoId'] == 'abcdefghijk'
    bridge.select('')
    attempts = len(calls)
    with pytest.raises(BotError, match='開始前の枠も選択できます'):
        bot.command('check')
    assert len(calls) == attempts and not sent


def test_connection_test_disabled_on_older_server_and_unknown_delivery_not_retried(setup_bot):
    bot, bridge, services, now, sent, calls = setup_bot
    activate(bot)
    bot.checked[2].pop('features')
    with pytest.raises(ValueError, match='更新待ち'): bot.command('test')
    assert not sent
    bot.checked[2]['features'] = {'connectionTest':True}
    bot.http.close()
    attempts=[]
    def timeout(request):
        attempts.append(request)
        raise httpx.ReadTimeout('PRIVATE')
    bot.http=httpx.Client(transport=httpx.MockTransport(timeout))
    with pytest.raises(BotError): bot.command('test')
    assert not bot.running and len(attempts)==1
    now[0]+=120
    bot.tick()
    assert len(attempts)==1 and 'PRIVATE' not in str(bot.status())


def test_start_is_idempotent_preserving_timer_queue_and_generation(setup_bot):
    bot, bridge, services, now, sent, calls = setup_bot
    activate(bot)
    bot.receive(comment(3, '@JoinQueueBot 順番は？'))
    before = (bot.next_guide, bot.generation, list(bot.queue), len(calls))
    now[0] += 300
    assert bot.command('start')['ready']
    assert before == (bot.next_guide, bot.generation, list(bot.queue), len(calls))


@pytest.mark.parametrize('code', ['INVALID_MESSAGE', 'REQUEST_EXPIRED', 'DUPLICATE_CONFLICT'])
def test_bad_single_notification_does_not_stop_next_notification(setup_bot, code):
    bot, bridge, services, now, sent, calls = setup_bot
    activate(bot)
    bot.http.close()
    attempts = []
    def reply(request):
        attempts.append(json.loads(request.content))
        return httpx.Response(400, json={'error':{'code':code}}) if len(attempts) == 1 else httpx.Response(200, json={'status':'sent'})
    bot.http = httpx.Client(transport=httpx.MockTransport(reply))
    bot.receive(comment(3, '@JoinQueueBot 順番は？')); bot.tick()
    assert bot.running and len(attempts) == 1
    now[0] += 10
    bot.receive(comment(4, '@JoinQueueBot 順番は？')); bot.tick()
    assert bot.running and len(attempts) == 2
    assert attempts[0]['eventId'] != attempts[1]['eventId']


@pytest.mark.parametrize('name', ['Player: A', 'https://www.example.com', 'x'*200, '😀'*100, '\u200b\n'])
def test_bot_name_is_bounded_safe_and_never_leaks_memo(name):
    value = AnnouncementBot._name({'display_name':name, 'onecomme_memo':'PRIVATE'})
    assert value['name'].strip() and len(value['name'].encode('utf-16-le')) // 2 <= 45
    assert not any(s in value['name'].lower() for s in ('/', ':', 'www.', 'PRIVATE'.lower()))
    assert set(value) == {'name'}
    assert 'handle' not in AnnouncementBot._name({'youtube_handle':'@'+'a'*100, 'display_name':name})


@pytest.mark.parametrize('corruption', ['invalid_settings', 'invalid_json', 'database'])
def test_bot_storage_corruption_preserves_data_and_queue_availability(tmp_path, corruption):
    path = tmp_path/'bot.sqlite3'
    if corruption == 'database':
        path.write_bytes(b'not a sqlite database')
    else:
        store = BotStore(path)
        store.write('shared_settings', {'interval_minutes':10})
        if corruption == 'invalid_json':
            with store.connection() as db:
                db.execute("UPDATE bot_data SET value=? WHERE key='shared_settings'", (b'{PRIVATE',))
    original = path.read_bytes()
    with TestClient(create_app(db_path=str(tmp_path/'q.db'), desktop=True, onecomme=True), base_url='http://127.0.0.1') as c:
        c.headers['Authorization'] = 'Bearer ' + c.app.state.access_keys.admin
        assert c.get('/api/state').status_code == 200
        assert c.get('/overlay').status_code == 200
        assert c.get('/api/bot').json()['ready'] is False
        assert '保存' in c.get('/api/bot').json()['error']
        assert 'PRIVATE' not in str(c.get('/api/bot').json())
        assert c.post('/api/bot/connection', json={'action':'start'}).status_code == 422
        assert c.post('/api/bot/settings', json={}).status_code == 422
    assert path.read_bytes() == original

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
    assert sent[-1]['variables'] == {'name':'@user6','handle':'@user6','state':'waiting','position':4,'group':2}
    assert sent[-1]['recipient']['userId'] == comment(6).user_key
    now[0] += 10; bot.receive(comment(6, '@JoinQueueBot 順番は？', 'again')); bot.tick(); assert len(sent) == 1
    bot.receive(comment(1, '@JoinQueueBot 順番は？')); bot.tick(); assert sent[-1]['variables']['state'] == 'now'
    assert 'group' not in sent[-1]['variables']
    now[0] += 10; bot.receive(comment(50, '@JoinQueueBot 順番は？')); bot.tick(); assert sent[-1]['variables']['state'] == 'not-queued'
    assert not bot.receive(comment(60, '@JoinQueueBot-other'))
    assert not bot.receive(comment(60, '@@JoinQueueBot'))


@pytest.mark.parametrize('text, expected', [
    ('@JoinQueueBot 順番', True),
    ('@JoinQueueBot 順番は？', True),
    ('@JoinQueueBot 自分の順番を教えてください', True),
    ('私の順番は？ @joinqueuebot', True),
    ('@JoinQueueBot、順番を確認したいです', True),
    ('順番は？', False),
    ('@JoinQueueBot', True),
    ('@JoinQueueBot こんにちは', True),
    ('@otherbot 順番', False),
    ('@JoinQueueBot-other 順番', False),
    ('@@JoinQueueBot 順番', False),
])
def test_position_requires_bot_reply_but_no_question_keyword(setup_bot, text, expected):
    bot, bridge, services, now, sent, calls = setup_bot
    activate(bot)
    assert bot.receive(comment(6, text)) is expected
    bot.tick()
    assert len(sent) == int(expected)
    assert len(bot.reply_times) == int(expected)


def test_position_cooldown_is_180_seconds_per_user_and_allows_first_at_zero(setup_bot):
    bot, bridge, services, now, sent, calls = setup_bot
    now[0] = 0
    activate(bot)
    bot.receive(comment(6, '@JoinQueueBot', 'first'))
    bot.tick()
    assert len(sent) == 1
    # Another user is accepted immediately; only the existing transport gap delays posting.
    bot.receive(comment(7, '@JoinQueueBot', 'other-user'))
    assert len(bot.queue) == 1 and comment(7).user_key in bot.reply_times
    now[0] = 10
    bot.tick()
    assert len(sent) == 2 and sent[-1]['recipient']['userId'] == comment(7).user_key
    now[0] = 179.999
    bot.receive(comment(6, '@JoinQueueBot', 'too-soon'))
    bot.tick()
    assert len(sent) == 2
    now[0] = 180
    bot.receive(comment(6, '@JoinQueueBot', 'after-cooldown'))
    bot.tick()
    assert len(sent) == 3 and sent[-1]['recipient']['userId'] == comment(6).user_key
    now[0] = 400
    bot.receive(comment(6, '@JoinQueueBot', 'after-cooldown'))
    bot.tick()
    assert len(sent) == 3  # A duplicate message is never answered twice.


@pytest.mark.parametrize('matches', [0, 1, 20])
def test_position_groups_start_at_next_independent_of_match_count(setup_bot, matches):
    bot, bridge, services, now, sent, calls = setup_bot
    users = [{'user_id': UserIdentityService().build_comment_user_id('youtube', comment(i).user_key)} for i in range(10)]
    state = {'total_match_count': matches, 'current': users[:3], 'waiting': users[3:]}
    for rank in (1, 3, 4, 6, 7):
        sender = comment(rank + 2)
        result = bot._variables('position', (sender.user_key, sender.youtube_handle, sender.display_name), state)
        assert result['state'] == 'waiting' and result['position'] == rank
        assert result['group'] == (rank + 2) // 3
    sender = comment(0)
    result = bot._variables('position', (sender.user_key, sender.youtube_handle, sender.display_name), state)
    assert result['state'] == 'now' and 'group' not in result

@pytest.mark.parametrize('mask', range(8))
def test_three_switches_all_combinations(setup_bot, mask):
    bot, bridge, services, now, sent, calls = setup_bot
    activate(bot)
    bot.configure(BotSettings(enabled=True, announce_now=bool(mask & 1), reply_position=bool(mask & 2), periodic=bool(mask & 4), interval_minutes=15, initial_delay_minutes=15))
    for i in range(6): services.receive_comment(comment(i))
    services.move_next(); bot.tick()
    now[0] += 10; bot.receive(comment(4, '@JoinQueueBot 順番は？')); bot.tick()
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
    bot.configure(BotSettings(enabled=True, periodic=True, interval_minutes=15, initial_delay_minutes=15))
    bot.tick(); now[0] += 899; bot.tick(); assert len(sent) == 1
    now[0] += 1; bot.tick(); assert len(sent) == 2
    now[0] += 5400; bot.tick(); assert len(sent) == 2
    bridge.heartbeat_at = 0; bot.tick(); assert not bot.running
    now[0] += 900; bot.tick(); assert len(sent) == 2

@pytest.mark.parametrize('delay', [15, 30, 45, 60])
def test_initial_delay_is_saved_and_independent_of_repeat_interval(setup_bot, delay):
    bot, bridge, services, now, sent, calls = setup_bot
    bot.configure(BotSettings(initial_delay_minutes=delay, interval_minutes=15))
    assert bot.store.data['shared_settings']['initial_delay_minutes'] == delay
    restored = AnnouncementBot(services, bridge, bot.store,
        client=httpx.Client(transport=httpx.MockTransport(lambda r: pytest.fail('network'))))
    assert restored.settings.initial_delay_minutes == delay and not restored.running
    restored.stop()
    activate(bot)
    now[0] += delay * 60 - 1
    bot.tick(); assert not sent
    now[0] += 1
    bot.tick(); assert len(sent) == 1
    now[0] += 899
    bot.tick(); assert len(sent) == 1
    now[0] += 1
    bot.tick(); assert len(sent) == 2


def test_initial_delay_edit_restarts_from_save_but_unrelated_save_preserves_deadline(setup_bot):
    bot, bridge, services, now, sent, calls = setup_bot
    activate(bot)
    deadline = bot.next_guide
    now[0] += 120
    bot.configure(BotSettings(enabled=True, interval_minutes=15, reply_position=False))
    assert bot.next_guide == deadline
    bot.configure(BotSettings(enabled=True, initial_delay_minutes=45, interval_minutes=15))
    assert bot.next_guide == now[0] + 2700
    now[0] += 100
    deadline = bot.next_guide
    bot.configure(bot.settings)
    assert bot.next_guide == deadline
    bot.command('stop')
    assert bot.next_guide is None
    bot.command('start')
    assert bot.next_guide == now[0] + 2700


@pytest.mark.parametrize('delay', [0, 10, 90, True, '30', 30.0])
def test_invalid_initial_delay_is_rejected(delay):
    with pytest.raises(ValueError):
        BotSettings(initial_delay_minutes=delay)


def test_no_replay_after_switch_off_and_no_old_google_auth_read(setup_bot):
    bot, bridge, services, now, sent, calls = setup_bot
    bot.store.data['credentials'] = {'refresh_token':'old-secret'}
    bot.store.data['settings'] = {'enabled':True, 'interval_minutes':10, 'guide':'old'}
    restored = AnnouncementBot(services, bridge, bot.store, client=httpx.Client(transport=httpx.MockTransport(lambda r: pytest.fail('network'))))
    assert not restored.running and restored.device is None and restored.settings.interval_minutes == 30
    assert 'old-secret' not in str(restored.status()); restored.stop()
    activate(bot); bot.receive(comment(6, '@JoinQueueBot 順番は？'))
    bot.configure(BotSettings(enabled=True, reply_position=False))
    bot.configure(BotSettings(enabled=True)); now[0] += 10; bot.tick(); assert not sent
    assert bot.store.data['credentials']['refresh_token'] == 'old-secret'

def test_ambiguous_post_stops_and_never_retries(setup_bot):
    bot, bridge, services, now, sent, calls = setup_bot
    activate(bot); bot.receive(comment(6, '@JoinQueueBot 順番は？'))
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
        assert c.post('/api/bot/erase', json={}).status_code == 422
        assert c.post('/api/bot/connection', json={'action':'erase'}).status_code == 422
        assert c.post('/api/bot/connection', json={'action':'stop','url':'https://evil.invalid'}).status_code == 422
        html = c.get('/bot').text
        assert '<h1>設定画面</h1>' in html and 'id="bot-client"' not in html
        assert c.get('/bot', follow_redirects=False).headers['location'] == '/settings?tab=bot'
        assert 'role="tablist"' in html and 'aria-controls="settings-bot-panel"' in html
        assert '<h3>通知選択</h3>' in html and html.count('id="bot-form"') == 1
        assert html.count('id="overlay-layout-form"') == 1
        for removed in ('通知を選ぶ', 'Botを使わなくても', 'チェックの変更は保存後', '利用者ごとのBotアカウント', '人数・待機順はNOWを除きます'):
            assert removed not in html
        control = c.get('/control').text
        assert '<a href="/settings?tab=bot">Bot設定</a>' in control
        assert 'Botのお知らせ設定' not in control
    with TestClient(create_app(db_path=str(tmp_path/'old'), desktop=True), base_url='http://127.0.0.1') as c:
        c.headers['Authorization'] = 'Bearer ' + c.app.state.access_keys.admin
        assert c.get('/api/bot').status_code == 404 and c.get('/bot').status_code == 404
        assert 'settings-bot-panel' not in c.get('/settings').text


def test_server_erasure_preserves_local_queue_settings_and_requires_server_acknowledgement(setup_bot):
    bot, bridge, services, now, sent, calls = setup_bot
    activate(bot)
    services.receive_comment(comment(1))
    before = services.build_view_state()
    settings = bot.settings.model_dump(); settings['enabled'] = False
    with pytest.raises(ValueError, match='認証結果'): bot.command('erase')
    token = bot.device
    bot.deletion_available = True
    bot.http.close()
    attempted = []
    def erase(request):
        attempted.append(request)
        assert request.url.path == '/v1/connections/erase'
        assert json.loads(request.content) == {'confirmation': 'UC' + '9'*22}
        return httpx.Response(200, json={'status':'deleted', 'securityRetentionHours':25})
    bot.http = httpx.Client(transport=httpx.MockTransport(erase))
    result = bot.command('erase')
    assert not result['ready'] and not result['authenticated'] and not result['has_connection_key']
    assert bot.settings.model_dump() == settings
    assert bot.store.data['shared_device'] is None
    assert services.build_view_state() == before
    assert len(attempted) == 1 and not sent
    assert token not in str(result)


def test_erasure_timeout_and_pending_post_preserve_device_for_safe_retry(setup_bot):
    bot, bridge, services, now, sent, calls = setup_bot
    activate(bot); bot.deletion_available = True; token = bot.device
    bot.send_lock.acquire()
    try:
        with pytest.raises(ValueError, match='投稿処理中'): bot.command('erase')
    finally:
        bot.send_lock.release()
    assert bot.device == token and not bot.running
    bot.http.close()
    bot.http = httpx.Client(transport=httpx.MockTransport(lambda r: (_ for _ in ()).throw(httpx.ReadTimeout('PRIVATE'))))
    with pytest.raises(BotError): bot.command('erase')
    assert bot.device == token and bot.store.data['shared_device'] == token
    assert 'PRIVATE' not in str(bot.status()) and token not in str(bot.status())


def test_creator_authorization_error_preserves_key_for_disconnect_retry(setup_bot):
    bot, bridge, services, now, sent, calls = setup_bot
    activate(bot); token = bot.device; before = services.build_view_state()
    bot.http.close()
    bot.http = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(503,
        json={'error': {'code': 'CHANNEL_AUTH_UNAVAILABLE', 'message': 'private provider payload'}})))
    with pytest.raises(BotError) as result:
        bot.command('disconnect')
    assert result.value.code == 'CHANNEL_AUTH_UNAVAILABLE'
    assert 'private provider' not in str(result.value)
    assert bot.device == token and bot.store.data['shared_device'] == token
    assert not bot.running and services.build_view_state() == before
