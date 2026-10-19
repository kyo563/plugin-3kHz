"""NOW removal/movement and persistent forward-only compaction in OneComme."""
from copy import deepcopy
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from app.initial_state import initial_state
from app.main import create_app
from app.services.application_services import ApplicationServices
from app.services.queue_service import QueueService


def participant(index):
    return {"user_id": f"u{index}", "display_name": f"参加者{index}",
            "participation_count": index, "declared_player_name": f"名{index}",
            "youtube_handle": f"@user{index}", "onecomme_memo": f"memo{index}"}


def populated(total=10):
    state = initial_state(desktop=True)
    users = [participant(i) for i in range(total)]
    state.update(current=users[:3], waiting=users[3:], participation_history=[], total_match_count=0,
                 participation_counts={u['user_id']: u['participation_count'] for u in users})
    return state


def ids(state, section):
    return [u['user_id'] for u in state[section]]


@pytest.mark.parametrize('operation', ['delete', 'tail', 'drag'])
@pytest.mark.parametrize('current_index', [0, 1, 2])
@pytest.mark.parametrize('total', [4, 5, 6, 10])
@pytest.mark.parametrize('is_open', [True, False])
def test_three_operations_always_promote_original_waiting_head(operation, current_index, total, is_open):
    service = QueueService(compact_queue=True, protect_next=True)
    state = populated(total)
    state.update(is_open=is_open, priority_mode=True)
    before = deepcopy(state)
    user_id = f'u{current_index}'
    if operation == 'delete':
        service.remove_user_by_id(state, user_id)
    elif operation == 'tail':
        service.move_user_to_waiting_tail(state, user_id)
    else:
        service.move_current_to_waiting(state, user_id, 'u3')
    expected_now = [u for u in ids(before, 'current') if u != user_id] + ['u3']
    assert ids(state, 'current') == expected_now
    expected_waiting = ids(before, 'waiting')[1:]
    if operation == 'tail':
        expected_waiting.append(user_id)
    elif operation == 'drag':
        expected_waiting.insert(0, user_id)
    assert ids(state, 'waiting') == expected_waiting
    users = state['current'] + state['waiting']
    expected = before['current'] + before['waiting']
    if operation == 'delete':
        expected = [u for u in expected if u['user_id'] != user_id]
    assert sorted(users, key=lambda u: u['user_id']) == sorted(expected, key=lambda u: u['user_id'])
    for field in ('participation_counts', 'participation_history', 'total_match_count', 'is_open', 'priority_mode'):
        assert state[field] == before[field]


@pytest.mark.parametrize('target,after,expected', [
    ('u3', False, ['u0', 'u4', 'u5', 'u6']),
    ('u3', True, ['u0', 'u4', 'u5', 'u6']),
    ('u4', False, ['u0', 'u4', 'u5', 'u6']),
    ('u4', True, ['u4', 'u0', 'u5', 'u6']),
    ('u6', False, ['u4', 'u5', 'u0', 'u6']),
    ('u6', True, ['u4', 'u5', 'u6', 'u0']),
    (None, False, ['u4', 'u5', 'u6', 'u0']),
])
def test_drop_boundary_accounts_for_promoted_target(target, after, expected):
    state = populated(7)
    QueueService(compact_queue=True).move_current_to_waiting(state, 'u0', target, after)
    assert ids(state, 'current') == ['u1', 'u2', 'u3']
    assert ids(state, 'waiting') == expected


@pytest.mark.parametrize('total', [1, 2, 3])
def test_no_replacement_never_leaves_moved_person_waiting_beside_empty_now(total):
    state = populated(total)
    service = QueueService(compact_queue=True)
    service.move_user_to_waiting_tail(state, 'u0')
    assert len(state['current']) == total and state['waiting'] == []
    assert len({u['user_id'] for u in state['current']}) == total
    service.move_current_to_waiting(state, 'u0', None)
    assert len(state['current']) == total and state['waiting'] == []
    service.remove_user_by_id(state, 'u0')
    assert len(state['current']) == total - 1 and state['waiting'] == []


def test_waiting_operations_remain_stable_and_default_standalone_is_unchanged():
    state = populated(7)
    service = QueueService(compact_queue=True)
    service.move_user_to_waiting_tail(state, 'u4')
    assert ids(state, 'current') == ['u0', 'u1', 'u2']
    assert ids(state, 'waiting') == ['u3', 'u5', 'u6', 'u4']
    service.reorder_waiting(state, ['u6', 'u3', 'u5', 'u4'])
    assert ids(state, 'waiting') == ['u6', 'u3', 'u5', 'u4']
    legacy = populated(7)
    QueueService().move_user_to_waiting_tail(legacy, 'u0')
    assert ids(legacy, 'current') == ['u1', 'u2']
    assert ids(legacy, 'waiting') == ['u3', 'u4', 'u5', 'u6', 'u0']


@pytest.fixture
def client(tmp_path):
    app = create_app(db_path=str(tmp_path / 'queue.sqlite3'), desktop=True, onecomme=True)
    with TestClient(app, base_url='http://127.0.0.1') as client:
        client.headers['Authorization'] = 'Bearer ' + app.state.access_keys.admin
        app.state.services.persistence_service.set_state(populated(7))
        yield client


@pytest.mark.parametrize('operation', ['delete', 'tail', 'drag'])
def test_api_compaction_single_undo_and_restart(client, operation):
    store = client.app.state.services.persistence_service
    before = client.get('/api/state').json()
    paths = {'delete': 'remove-user', 'tail': 'move-to-waiting-tail', 'drag': 'move-current-to-waiting'}
    payload = {'user_id': 'u1'}
    if operation == 'drag':
        payload.update(target_user_id='u5', after=True, expected_revision=before['revision'])
    result = client.post('/api/control/' + paths[operation], json=payload)
    assert result.status_code == 200, result.text
    after = result.json()
    assert ids(after, 'current') == ['u0', 'u2', 'u3']
    assert after['undo_available']
    reopened = ApplicationServices(db_path=store._db_path, desktop=True, onecomme=True)
    saved = reopened.build_view_state()
    assert saved['current'] == after['current'] and saved['waiting'] == after['waiting']
    restored = client.post('/api/control/undo').json()
    for key in ('current', 'waiting'):
        # A restored/moved row has a new modification timestamp, not a new identity.
        assert [{k: v for k, v in u.items() if k != 'updated_at'} for u in restored[key]] == [
            {k: v for k, v in u.items() if k != 'updated_at'} for u in before[key]]
    for key in ('participation_counts', 'session_participation_counts', 'total_match_count'):
        assert restored[key] == before[key]
    assert not restored['undo_available']
    # Both control and OBS view data use the same compact real queue.
    assert len(after['now_view']) == 3
    assert all(not u.get('is_placeholder') for u in after['now_view'])


@pytest.mark.parametrize('operation', ['remove-user', 'move-to-waiting-tail', 'move-current-to-waiting'])
def test_obs_immediately_uses_compacted_queue_without_recording_a_match_or_calling_bot(client, operation):
    services = client.app.state.services
    services.bot = Mock()
    from app.services.participation_history import record_match
    services.persistence_service.mutate_state(record_match)
    before = services.persistence_service.get_state()
    overlay_before = client.get('/api/overlay-state')
    payload = {'user_id': 'u1'}
    if operation == 'move-current-to-waiting':
        payload.update(target_user_id='u5', expected_revision=services.persistence_service.revision)
    assert client.post('/api/control/' + operation, json=payload).status_code == 200
    after = services.persistence_service.get_state()
    assert after['participation_history'] == before['participation_history']
    assert after['participation_counts'] == before['participation_counts']
    assert after['total_match_count'] == before['total_match_count']
    services.bot.announce.assert_not_called()
    response = client.get('/api/overlay-state', headers={'If-None-Match': overlay_before.headers['ETag']})
    assert response.status_code == 200  # old OBS cache is invalidated
    overlay = response.json()
    assert [u['display_name'] for u in overlay['now_view']] == ['@user0', '@user2', '@user3']
    expected_next = ([f'@user{i}' for i in [4, 1, 5]] if operation == 'move-current-to-waiting'
                     else [f'@user{i}' for i in [4, 5, 6]])
    assert [u['display_name'] for u in overlay['next_view']] == expected_next


def test_archived_video_with_old_gap_is_compacted_on_restore(client):
    store = client.app.state.services.persistence_service
    store.adopt_video('old-video')
    store.switch_video('new-video')
    old = populated(6)
    old['waiting'].append(old['current'].pop(0))
    # Store an old archived session exactly as previous versions could produce it.
    import json
    with store._connect() as conn:
        conn.execute('UPDATE onecomme_sessions SET value=? WHERE video_id=?',
                     (json.dumps({key: old[key] for key in store.SESSION_FIELDS}), 'old-video'))
    store.switch_video('old-video')
    restored = store.get_state()
    assert ids(restored, 'current') == ['u1', 'u2', 'u3']
    assert ids(restored, 'waiting') == ['u4', 'u5', 'u0']


@pytest.mark.parametrize('user,target', [('missing', 'u4'), ('u4', 'u5'), ('u0', 'missing'), ('u0', 'u0')])
def test_invalid_move_is_atomic(client, user, target):
    before = client.get('/api/state').json()
    result = client.post('/api/control/move-current-to-waiting', json={
        'user_id': user, 'target_user_id': target, 'expected_revision': before['revision']})
    assert result.status_code == 409
    assert client.get('/api/state').json() == before


def test_stale_drag_and_unauthorized_requests_are_rejected(client):
    before = client.get('/api/state').json()
    payload = {'user_id': 'u0', 'target_user_id': 'u4', 'expected_revision': before['revision'] - 1}
    assert client.post('/api/control/move-current-to-waiting', json=payload).status_code == 409
    assert client.post('/api/control/move-current-to-waiting', json=payload,
                       headers={'Authorization': 'Bearer invalid'}).status_code == 401
    assert client.get('/api/state').json() == before


def test_existing_and_restored_holes_are_compacted_without_incrementing_counts(tmp_path):
    db = str(tmp_path / 'old.sqlite3')
    # Simulate the old implementation leaving a NOW vacancy in persisted data.
    legacy = ApplicationServices(db_path=db, desktop=True)
    old = populated(7)
    old['waiting'].append(old['current'].pop(1))
    legacy.persistence_service.set_state(old)
    updated = ApplicationServices(db_path=db, desktop=True, onecomme=True)
    state = updated.persistence_service.get_state()
    assert ids(state, 'current') == ['u0', 'u2', 'u3']
    assert ids(state, 'waiting') == ['u4', 'u5', 'u6', 'u1']
    assert state['participation_counts'] == old['participation_counts']
    store = updated.persistence_service
    # Restore (including archived video restoration via set_state) enforces the same invariant.
    store.restore(old, store.revision)
    assert ids(store.get_state(), 'current') == ['u0', 'u2', 'u3']
    assert ids(store.get_state(), 'waiting') == ['u4', 'u5', 'u6', 'u1']


def test_move_routes_and_guidance_are_onecomme_only(tmp_path, client):
    assert 'NOWの参加者も待機列へドラッグ' in client.get('/').text
    app = create_app(db_path=str(tmp_path / 'standalone.sqlite3'), desktop=True)
    with TestClient(app, base_url='http://127.0.0.1') as standalone:
        standalone.headers['Authorization'] = 'Bearer ' + app.state.access_keys.admin
        assert 'NOWの参加者も待機列へドラッグ' not in standalone.get('/').text
        assert standalone.post('/api/control/move-current-to-waiting', json={
            'user_id': 'u0', 'expected_revision': 0}).status_code == 404
