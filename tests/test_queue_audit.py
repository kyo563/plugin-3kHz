from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
import random
import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.schemas.comment import ReceivedComment
from app.services.application_services import ApplicationServices
from app.services.participation_history import new_session
from app.services.queue_audit import QueueAudit
from app.services.queue_service import QueueService
from tests.test_onecomme_priority_number import queue, user


def events(report):
    return [json.loads(line) for line in report.splitlines() if line.startswith('{')]


@pytest.fixture
def client(tmp_path):
    app = create_app(db_path=str(tmp_path / 'audit.sqlite3'), desktop=True, onecomme=True)
    with TestClient(app, base_url='http://127.0.0.1') as client:
        client.headers['Authorization'] = 'Bearer ' + app.state.access_keys.admin
        yield client


def add(client, uid):
    response = client.post('/api/control/add-user', json={'user_id': uid, 'display_name': 'PRIVATE_NAME_' + uid})
    assert response.status_code == 200, response.text
    return response.json()


def report(client):
    response = client.get('/api/control/diagnostic-log')
    assert response.status_code == 200
    assert 'text/plain' in response.headers['content-type']
    assert 'attachment' in response.headers['content-disposition']
    assert response.headers['cache-control'] == 'no-store'
    return response.content.decode('utf-8-sig')


def test_export_allowlist_keeps_only_handles_even_in_malicious_fields(client):
    add(client, 'PRIVATE_UID')
    p = client.app.state.services.persistence_service
    def change(state):
        state['current'][0].update(youtube_handle='@公開ハンドル', youtube_nickname='PRIVATE_NICK',
                                  declared_player_name='PRIVATE_ALIAS', onecomme_memo='PRIVATE_MEMO')
        state['logs'].append('PRIVATE_TOKEN https://private.test/oauth?key=PRIVATE_KEY')
        state['overlay_settings']['custom_text'] = 'PRIVATE_TEXT[NOW1]PRIVATE_NAME'
        state['description_text'] = 'PRIVATE_DESCRIPTION'
    p.mutate_state(change)
    text = report(client)
    assert '@公開ハンドル' in text
    for private in ('PRIVATE', 'https://', 'user_id', 'youtube_nickname', 'declared_player_name', 'onecomme_memo'):
        assert private not in text
    last = events(text)[-1]
    assert last['after']['handles'] == {'P001': '@公開ハンドル'}
    assert last['after']['OBS_template_tokens']['custom_text'] == ['[NOW1]']
    assert last['after']['NOW'] == ['P001']
    # Downloading is non-mutating: no revision change, undo invalidation or audit entry.
    revision, undo = p.revision, p.undo_available()
    assert report(client) == text and p.revision == revision and p.undo_available() == undo


@pytest.mark.parametrize('value', ['@bad\nname', '@https://private.test/key', '@abc\u200bsecret', '@bad name', 'display-name', '@a?key=secret', None])
def test_invalid_handle_is_never_exported(value):
    assert QueueAudit.handle(value) is None


def test_each_operation_has_reconstructable_before_after_and_reason(client):
    for i in range(8): add(client, f'u{i}')
    state = client.get('/api/state').json()
    assert client.post('/api/control/move-current-to-waiting', json={
        'user_id': 'u0', 'target_user_id': 'u4', 'expected_revision': state['revision']}).status_code == 200
    assert client.post('/api/control/undo').status_code == 200
    assert client.post('/api/control/move-to-waiting-tail', json={'user_id':'u1'}).status_code == 200
    assert client.post('/api/control/remove-user', json={'user_id':'u2'}).status_code == 200
    records = events(report(client))
    for record in records:
        for snapshot in (record['before'], record['after']):
            assert snapshot['NEXT'] == snapshot['WAITING'][:3]
            assert snapshot['QUEUE'] == snapshot['WAITING'][3:]
            assert len(snapshot['OBS_NOW']) == len(snapshot['OBS_NEXT']) == 3
        assert record['elapsed_seconds'] >= 0
    move = next(r for r in records if r['action'] == 'manual_move')
    assert move['actor'] == 'P001'
    assert move['before']['NOW'] == ['P001','P002','P003']
    assert move['after']['NOW'] == ['P002','P003','P004']
    assert move['after']['WAITING'][0] == 'P001'
    assert move['cumulative_records_changed'] == 0
    assert {'manual_add','manual_move','manual_tail','manual_remove','undo'} <= {r['action'] for r in records}


def test_rejoin_cooldown_now_and_closed_are_distinguished(client):
    for i in range(4): add(client, f'u{i}')
    services = client.app.state.services
    def send(mid, key, message='参加希望'):
        return services.receive_comment(ReceivedComment(source='youtube', userKey=key,
            displayName='PRIVATE_COMMENTER', youtubeHandle='@viewer', externalMessageId=mid,
            receivedAt='2026-10-20T00:00:00Z', message=message))
    send('one', 'commenter')
    send('two', 'commenter')
    services.persistence_service.mutate_state(lambda s: s.update(cooldown_seconds=0))
    send('three', 'commenter')
    send('three', 'commenter')  # duplicate is its own event, not a second join
    client.post('/api/control/toggle-open')
    send('four', 'closed')
    # Closing with two waiting users now accepts exactly one final-group fill.
    send('five', 'closed-extra')
    reasons = [r['reason'] for r in events(report(client))]
    assert 'final_group_fill' in reasons
    assert 'cooldown' in reasons and 'rejoin_tail' in reasons and 'duplicate' in reasons and 'closed' in reasons
    assert 'PRIVATE_COMMENTER' not in report(client)
    assert any(r['actor_handle'] == '@viewer' for r in events(report(client)))


def test_manual_reset_preserves_queue_totals_settings_and_can_undo(client):
    for i in range(8): add(client, f'u{i}')
    client.post('/api/control/move-next')
    add(client, 'u0')
    before = client.get('/api/state').json()
    p = client.app.state.services.persistence_service
    old_history = deepcopy(p.get_state()['participation_history'])
    response = client.post('/api/control/reset-session-counts', json={
        'confirmed': True, 'expected_revision': before['revision']})
    assert response.status_code == 200
    after = response.json()
    assert after['session_participation_counts'] == {}
    for field in ('current','waiting','participation_counts','overlay_settings','total_match_count','name_overrides'):
        assert after[field] == before[field]
    assert p.get_state()['participation_history'][:-1] == old_history
    assert events(report(client))[-1]['action'] == 'history_reset'
    assert client.post('/api/control/undo').json()['session_participation_counts'] == before['session_participation_counts']


@pytest.mark.parametrize('payload,status', [({'confirmed':False,'expected_revision':1},422),
    ({'confirmed':'true','expected_revision':1},422), ({'confirmed':True,'expected_revision':-1},422),
    ({'confirmed':True,'expected_revision':0},409)])
def test_reset_rejects_unconfirmed_invalid_and_stale_without_change(client, payload, status):
    before = client.get('/api/state').json()
    assert client.post('/api/control/reset-session-counts', json=payload).status_code == status
    assert client.get('/api/state').json() == before


def test_two_reset_requests_with_same_revision_only_one_wins(client):
    p = client.app.state.services.persistence_service
    revision = p.revision
    def reset(_):
        return client.post('/api/control/reset-session-counts', json={'confirmed':True,'expected_revision':revision}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(reset, range(2))) == [200,409]


def test_new_video_resets_this_stream_only_restart_and_revisit_restore(client):
    p = client.app.state.services.persistence_service
    p.adopt_video('PRIVATE_VIDEO_A')
    for i in range(6): add(client, f'u{i}')
    client.post('/api/control/move-next')
    before = client.get('/api/state').json()
    assert before['session_participation_counts']['u0'] == 1
    p.switch_video('PRIVATE_VIDEO_B', carry=True)
    after = client.get('/api/state').json()
    assert after['session_participation_counts'] == {} and after['participation_counts'] == before['participation_counts']
    # A repeated switch/reconnection to the SAME video must not reset ongoing counts.
    client.post('/api/control/move-next')
    this_stream = client.get('/api/state').json()['session_participation_counts']
    p.switch_video('PRIVATE_VIDEO_B')
    assert client.get('/api/state').json()['session_participation_counts'] == this_stream
    reopened = ApplicationServices(db_path=p._db_path, desktop=True, onecomme=True)
    assert reopened.build_view_state()['session_participation_counts'] == this_stream
    totals = reopened.build_view_state()['participation_counts']
    p.switch_video('PRIVATE_VIDEO_A')
    restored = client.get('/api/state').json()
    assert restored['session_participation_counts'] == before['session_participation_counts']
    assert restored['participation_counts'] == totals
    text = report(client)
    assert 'PRIVATE_VIDEO' not in text and '--- 前回の配信' in text
    p.switch_video('PRIVATE_VIDEO_C')
    with p._connect() as conn:
        assert conn.execute('SELECT count(*) FROM queue_audit_streams').fetchone()[0] == 2


def test_audit_is_durable_bounded_and_export_tells_about_truncation(client, monkeypatch):
    p = client.app.state.services.persistence_service
    monkeypatch.setattr(QueueAudit, 'MAX_EVENTS', 3)
    for i in range(8): add(client, f'u{i}')
    text = report(client)
    assert len(events(text)) == 3 and 'omitted=0' not in text
    restarted = ApplicationServices(db_path=p._db_path, desktop=True, onecomme=True)
    assert len(events(restarted.persistence_service.export_audit())) == 3


def test_audit_and_queue_write_rollback_together(client):
    p = client.app.state.services.persistence_service
    before = client.get('/api/state').json()
    original_report = report(client)
    with p._connect() as conn:
        conn.execute("CREATE TRIGGER fail_audit BEFORE INSERT ON queue_audit_events BEGIN SELECT RAISE(ABORT,'test'); END")
    with pytest.raises(sqlite3.IntegrityError):
        add(client, 'rollback')
    assert client.get('/api/state').json() == before
    assert report(client) == original_report


def test_logs_and_reset_require_admin_and_are_onecomme_only(client, tmp_path):
    for token in ('invalid', client.app.state.access_keys.ingest):
        assert client.get('/api/control/diagnostic-log',headers={'Authorization':'Bearer '+token}).status_code == 401
        assert client.post('/api/control/reset-session-counts',json={'confirmed':True,'expected_revision':0},
                           headers={'Authorization':'Bearer '+token}).status_code == 401
    with TestClient(create_app(db_path=str(tmp_path/'standalone'), desktop=True),base_url='http://127.0.0.1') as c:
        c.headers['Authorization'] = 'Bearer '+c.app.state.access_keys.admin
        assert c.get('/api/control/diagnostic-log').status_code == 404
        assert c.post('/api/control/reset-session-counts',json={'confirmed':True,'expected_revision':0}).status_code == 404
        assert 'id="session-count-reset"' not in c.get('/').text
    html = client.get('/').text
    assert html.count('id="session-count-reset"') == 1
    assert html.count('id="diagnostic-log-download"') == 1
    other = html.split('<summary>その他（設定・バックアップ）</summary>', 1)[1].split('<details id="description-tools"', 1)[0]
    logs = html.split('<summary>操作ログ</summary>', 1)[1].split('</details>', 1)[0]
    assert 'id="session-count-reset"' in other and 'id="diagnostic-log-download"' not in other
    assert 'id="diagnostic-log-download"' in logs and 'id="session-count-reset"' not in logs
    assert 'id="session-reset-status"' in other and 'id="diagnostic-tools-status"' in logs
    assert 'id="session-count-reset"' not in html[:html.index('id="now"')]
    for removed in ('今回の参加回数・診断ログ', '新しい配信として識別できた場合、',
                    '配信を区別できない場合や、テスト後に', 'ログはこの更新以降を記録します。'):
        assert removed not in html
    assert html.count('id="session-reset-dialog"') == 1


def test_random_lifetime_counts_never_change_priority_and_equal_zero_is_fifo():
    rng = random.Random(563)
    for _ in range(100):
        state = queue([rng.randrange(5) for _ in range(9)])
        first = deepcopy(state)
        for item in state['current'] + state['waiting']:
            item['participation_count'] = rng.randrange(1000000)
        QueueService(protect_next=True).add_user(first, user('new', 0))
        QueueService(protect_next=True).add_user(state, user('new', 999999))
        assert [u['user_id'] for u in state['waiting']] == [u['user_id'] for u in first['waiting']]
        new_session(state)
        previous = [u['user_id'] for u in state['waiting']]
        QueueService(protect_next=True).add_user(state, user('fresh', 999999))
        assert [u['user_id'] for u in state['waiting']] == previous + ['fresh']
