from datetime import datetime, timezone
import json
import os
import time
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.schemas.comment import ReceivedComment
from app.services.application_services import ApplicationServices
from app.services.onecomme import OneCommeBridge
from app.services.bot import AnnouncementBot, BotSettings, BotStore


class MemoryStore:
    def __init__(self): self.data = {}
    def read(self, key, default=None): return self.data.get(key, default)
    def write(self, key, value): self.data[key] = value
    def forget_credentials(self): self.data.pop('credentials', None)
    def save_connection(self, credentials, account):
        self.write('credentials', credentials)
        self.write('account', account)


def comment(n, text='参加希望', message_id=None):
    return ReceivedComment(source='youtube', userKey='UC' + str(n).zfill(22), displayName='User' + str(n),
                           externalMessageId=message_id or str(n) + text, message=text,
                           receivedAt=datetime.now(timezone.utc).isoformat())


@pytest.fixture
def setup_bot(tmp_path):
    services = ApplicationServices(db_path=str(tmp_path/'queue.db'), desktop=True)
    bridge = OneCommeBridge(services)
    bridge.frames['abcdefghijk'] = 'Test'
    bridge.select('abcdefghijk'); bridge.heartbeat()
    sent = []
    def transport(request):
        if request.url.path.endswith('/token'):
            return httpx.Response(200, json={'access_token': 'access-secret', 'refresh_token': 'refresh-secret', 'expires_in': 3600})
        if request.url.path.endswith('/channels'):
            return httpx.Response(200, json={'items': [{'id': 'UC' + '9'*22, 'snippet': {'title': 'Test Bot', 'customUrl': '@testbot'}}]})
        if request.url.path.endswith('/videos'):
            return httpx.Response(200, json={'items': [{'liveStreamingDetails': {'activeLiveChatId': 'chat'}}]})
        sent.append(json.loads(request.content)['snippet']['textMessageDetails']['messageText'])
        return httpx.Response(200, json={'id': 'sent'})
    now = [100.0]
    bot = AnnouncementBot(services, bridge, MemoryStore(), client=httpx.Client(transport=httpx.MockTransport(transport)), clock=lambda: now[0])
    services.bot = bridge.bot = bot
    bot.account = {'id': 'UC' + '9'*22, 'name': 'Bot', 'handle': '@testbot'}
    bot.credentials = {'client_id': 'client.apps.googleusercontent.com', 'client_secret': 'client-secret', 'refresh_token': 'refresh-secret'}
    yield bot, bridge, services, now, sent
    bot.stop()


def test_disabled_defaults_self_exclusion_and_persistence(setup_bot):
    bot, bridge, services, now, sent = setup_bot
    own = comment(999); own.user_key = bot.account['id']
    bridge.receive('abcdefghijk', 'Test', own)
    services.receive_comment(own)
    assert services.build_view_state()['current'] == []
    bot.tick(); assert not sent
    bot.configure(BotSettings(enabled=True, interval_minutes=30, announce_now=False))
    assert bot.store.data['settings']['interval_minutes'] == 30
    assert 'credentials' not in bot.status() and 'refresh-secret' not in str(bot.status())
    bot.disconnect()
    assert bot.is_self(own)
    assert not bot.status()['authenticated']


def test_now_next_announcements_and_no_duplicate_or_stale_group(setup_bot):
    bot, bridge, services, now, sent = setup_bot
    bot.configure(BotSettings(enabled=True))
    for i in range(6): services.receive_comment(comment(i))
    bot.tick()
    assert sent == ['User0さん、User1さん、User2さん 入室お願いします']
    now[0] += 6; bot.announce(); bot.tick(); assert len(sent) == 1
    services.move_next(); bot.tick()
    assert sent[-1] == 'User3さん、User4さん、User5さん 入室お願いします'
    assert len(sent) == 2
    now[0] += 6
    services.move_next(); bot.tick(); assert len(sent) == 2


def test_position_uses_id_next_included_and_no_join_in_query(setup_bot):
    bot, bridge, services, now, sent = setup_bot
    bot.configure(BotSettings(enabled=True, announce_now=False))
    for i in range(8): services.receive_comment(comment(i))
    bot.tick()
    bridge.receive('abcdefghijk', 'Test', comment(6, '@testbot 順番は？ 参加辞退'))
    bot.tick(); assert sent[-1] == '@User6さんは4番目/第2グループです'
    assert len(services.build_view_state()['waiting']) == 5
    now[0] += 6
    bridge.receive('abcdefghijk', 'Test', comment(6, '@testbot 順番は？', 'repeat'))
    bot.tick(); assert len(sent) == 1
    bridge.receive('abcdefghijk', 'Test', comment(1, '@testbot 順番は？'))
    bot.tick(); assert 'NOW' in sent[-1]
    now[0] += 6
    bridge.receive('abcdefghijk', 'Test', comment(50, '@testbot 順番は？'))
    bot.tick(); assert '登録されていません' in sent[-1]
    assert not bot.receive(comment(60, '@testbot-other 参加希望'))


def test_timer_features_disable_selection_and_heartbeat(setup_bot):
    bot, bridge, services, now, sent = setup_bot
    bot.configure(BotSettings(enabled=True, announce_now=False, guide='参加希望'))
    bot.tick(); now[0] += 601; bot.tick()
    assert sent == ['参加希望']
    services.toggle_open(); now[0] += 601; bot.tick(); assert len(sent) == 1
    bot.configure(BotSettings(enabled=False)); now[0] += 601; bot.tick(); assert len(sent) == 1
    bot.configure(BotSettings(enabled=True, announce_now=False))
    bot.receive(comment(20, '@testbot')); bridge.select(''); bot.tick(); assert len(sent) == 1
    bridge.select('abcdefghijk'); bridge.heartbeat_at = 0
    now[0] += 601; bot.tick(); assert len(sent) == 1
    assert not bot.status()['ready']


def test_oauth_pkce_state_and_account_exclusion(setup_bot):
    bot, bridge, services, now, sent = setup_bot
    url = bot.begin_login({'installed': {'client_id': 'test.apps.googleusercontent.com', 'client_secret': 'secret'}})
    query = parse_qs(urlsplit(url).query)
    assert query['code_challenge_method'] == ['S256']
    redirect = query['redirect_uri'][0]
    with httpx.Client(trust_env=False) as c:
        assert c.get(redirect, params={'state': 'wrong', 'code': 'code'}).status_code == 400
        assert bot.status()['login_pending']
        assert c.get(redirect, params={'state': query['state'][0], 'code': 'code'}).status_code == 200
    assert bot.status()['account']['handle'] == '@testbot'
    assert bot.store.data['credentials']['refresh_token'] == 'refresh-secret'
    assert not bot.settings.enabled
    assert not sent


def test_no_retry_for_ambiguous_post_and_stale_queue(setup_bot):
    bot, bridge, services, now, sent = setup_bot
    bot.configure(BotSettings(enabled=True, announce_now=False))
    bot.tick()
    bot.receive(comment(1, '@testbot 順番'))
    now[0] += 61
    bot.tick(); assert not sent
    bot.receive(comment(2, '@testbot 順番'))
    bot.http.close()
    attempts = []
    def fail(request):
        attempts.append(request)
        raise httpx.ReadTimeout('uncertain')
    bot.http = httpx.Client(transport=httpx.MockTransport(fail))
    with pytest.raises(httpx.ReadTimeout): bot.tick()
    now[0] += 6; bot.tick()
    assert len(attempts) == 1


def test_disconnected_during_oauth_does_not_restore_credentials(setup_bot):
    bot, bridge, services, now, sent = setup_bot
    url = bot.begin_login({'installed': {'client_id': 'test.apps.googleusercontent.com', 'client_secret': 'secret'}})
    query = parse_qs(urlsplit(url).query)
    old_request = bot._request
    def cancel(method, url, **kwargs):
        result = old_request(method, url, **kwargs)
        if url.endswith('/channels'):
            bot.disconnect()
        return result
    bot._request = cancel
    with httpx.Client(trust_env=False) as c:
        c.get(query['redirect_uri'][0], params={'state': query['state'][0], 'code': 'code'})
    assert not bot.credentials
    assert 'credentials' not in bot.store.data


@pytest.mark.skipif(os.name != 'nt', reason='Windows DPAPI')
def test_credentials_are_encrypted_and_removed(tmp_path):
    path = tmp_path/'bot.sqlite3'
    store = BotStore(path)
    secret = {'refresh_token': 'secret-refresh-token-test'}
    store.write('credentials', secret)
    assert store.read('credentials') == secret
    assert b'secret-refresh-token-test' not in path.read_bytes()
    store.forget_credentials(); assert store.read('credentials') is None
    store.save_connection(secret, {'id': 'test'})
    assert store.read('credentials') == secret
    assert store.read('account')['id'] == 'test'


def test_token_refresh_cannot_restore_disconnected_session(setup_bot):
    bot, bridge, services, now, sent = setup_bot
    def disconnect_on_refresh(request):
        bot.disconnect()
        return httpx.Response(200, json={'access_token': 'old-token', 'expires_in': 3600})
    bot.http.close()
    bot.http = httpx.Client(transport=httpx.MockTransport(disconnect_on_refresh))
    with pytest.raises(ValueError): bot._access_token()
    assert bot.token == ''
    assert not bot.status()['authenticated']


def test_bot_api_admin_only_variant_and_validations(tmp_path):
    with TestClient(create_app(db_path=str(tmp_path/'q'), desktop=True, onecomme=True), base_url='http://127.0.0.1') as c:
        assert c.get('/api/bot').status_code == 401
        c.headers['Authorization'] = 'Bearer ' + c.app.state.access_keys.ingest
        assert c.post('/api/bot/settings', json={'enabled': True}).status_code == 401
        c.headers['Authorization'] = 'Bearer ' + c.app.state.access_keys.admin
        assert c.get('/api/bot').json()['settings']['enabled'] is False
        assert c.post('/api/bot/settings', json={'interval_minutes': 7}).status_code == 422
        assert c.post('/api/bot/login', json={'installed': {}}).status_code == 422
        assert c.get('/bot').status_code == 200
        assert '/bot' in c.get('/control').text
    with TestClient(create_app(db_path=str(tmp_path/'old'), desktop=True), base_url='http://127.0.0.1') as c:
        c.headers['Authorization'] = 'Bearer ' + c.app.state.access_keys.admin
        assert c.get('/api/bot').status_code == 404
        assert c.get('/bot').status_code == 404
