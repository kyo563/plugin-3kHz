import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.services.application_services import ApplicationServices


def onecomme_client(path):
    return TestClient(create_app(db_path=str(path), desktop=True, onecomme=True),
                      base_url='http://127.0.0.1')


def authenticate(client):
    client.headers['Authorization'] = 'Bearer ' + client.app.state.access_keys.admin


@pytest.mark.parametrize('size', [1, 2, 3])
def test_resize_preserves_queue_order_and_persists_across_restart(tmp_path, size):
    db = tmp_path / 'queue.db'
    with onecomme_client(db) as client:
        authenticate(client)
        for name in 'ABCDEFGH':
            assert client.post('/api/control/add-user', json={'user_id': name, 'display_name': name}).is_success
        before = client.get('/api/state').json()
        overlay = client.get('/api/overlay-state')
        assert client.post('/api/settings/group-size', json={'group_size': size}).json() == {'group_size': size}
        state = client.get('/api/state').json()
        assert [u['user_id'] for u in state['current']] == list('ABCDEFGH'[:size])
        assert [u['user_id'] for u in state['waiting']] == list('ABCDEFGH'[size:])
        assert [u['user_id'] for u in state['next_view']] == list('ABCDEFGH'[size:2*size])
        assert state['total_waiting_group_count'] == (8 - size + size - 1) // size
        assert state['total_match_count'] == before['total_match_count']
        assert state['participation_counts'] == before['participation_counts']
        assert client.get('/api/control/backup').json()['state']['group_size'] == size
        if size < 3:
            updated = client.get('/api/overlay-state', headers={'If-None-Match': overlay.headers['etag']})
            assert updated.status_code == 200
            assert updated.json()['group_size'] == size
            assert len(updated.json()['now_view']) == size
        client.post('/api/control/toggle-open')
        assert client.get('/api/state').json()['final_group_slots'] == (-(8-size)) % size
    with onecomme_client(db) as client:
        authenticate(client)
        assert client.get('/api/settings/group-size').json()['group_size'] == size
        assert client.get('/api/overlay-state').json()['group_size'] == size


def test_resize_up_refills_and_undo_restores_previous_size_and_order(tmp_path):
    with onecomme_client(tmp_path / 'queue.db') as client:
        authenticate(client)
        for invalid in [0, 4, True, '2', 2.0]:
            assert client.post('/api/settings/group-size', json={'group_size': invalid}).status_code == 422
        client.post('/api/settings/group-size', json={'group_size': 1})
        for name in 'AB':
            client.post('/api/control/add-user', json={'user_id': name, 'display_name': name})
        client.post('/api/settings/group-size', json={'group_size': 3})
        state = client.get('/api/state').json()
        assert [u['user_id'] for u in state['current']] == ['A', 'B']
        assert state['waiting'] == []
        assert state['now_view'][2]['is_placeholder']
        restored = client.post('/api/control/undo').json()
        assert restored['group_size'] == 1
        assert [u['user_id'] for u in restored['current']] == ['A']
        assert [u['user_id'] for u in restored['waiting']] == ['B']
        completed = client.post('/api/control/move-next').json()
        assert [u['user_id'] for u in completed['current']] == ['B']
        assert completed['participation_counts']['A'] == 1
        assert completed['participation_counts']['B'] == 0


def test_call_timestamps_use_fixed_text_and_remain_separate_per_video(tmp_path):
    db = tmp_path / 'queue.db'
    services = ApplicationServices(db_path=str(db), desktop=True, onecomme=True)
    store = services.persistence_service
    store.switch_video('abcdefghijk')
    for event, seconds in [('three', 3861), ('one', 754), ('two', 1508), ('one', 800)]:
        store.record_call_timestamp('abcdefghijk', event, seconds)
    store.switch_video('lmnopqrstuv')
    store.record_call_timestamp('lmnopqrstuv', 'one', 65)
    with onecomme_client(db) as client:
        url = '/api/control/call-timestamps'
        assert client.get(url).status_code == 401
        authenticate(client)
        assert client.get(url).json()['text'] == '00:00:00 \t配信開始\n00:01:05 \t第1局'
        export = client.get(url, params={'video_id': 'abcdefghijk'}).json()
        assert export['text'] == '00:00:00 \t配信開始\n00:12:34 \t第1局\n00:25:08 \t第2局\n01:04:21 \t第3局'
        assert {v['video_id'] for v in export['videos']} == {'abcdefghijk', 'lmnopqrstuv'}
