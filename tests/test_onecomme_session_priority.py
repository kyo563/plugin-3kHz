from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.schemas.comment import ReceivedComment
from app.services.queue_service import QueueService
from app.services.user_identity_service import UserIdentityService
from tests.test_onecomme_priority_number import queue, user


@pytest.mark.parametrize('tail_session,new_session,tail_lifetime,new_lifetime,insert_first', [
    (2, 1, 2, 900, True), (0, 1, 900, 1, False),
    (1, 1, 900, 1, False), (3, 2, 0, 900, True),
])
def test_priority_compares_only_active_stream_counts(tail_session, new_session, tail_lifetime, new_lifetime, insert_first):
    state = queue([tail_session])
    state['waiting'][3]['participation_count'] = tail_lifetime
    if new_session:
        state['participation_history'][-1]['users'].append({
            'user_id': 'new', 'display_name': 'new', 'first_match': 1, 'count': new_session})
    history = deepcopy(state['participation_history'])
    QueueService(protect_next=True).add_user(state, user('new', new_lifetime))
    assert [u['user_id'] for u in state['waiting'][3:]] == (
        ['new', 'tail0'] if insert_first else ['tail0', 'new'])
    assert state['participation_history'] == history  # joining is not a completed match
    assert next(u for u in state['waiting'] if u['user_id'] == 'new')['participation_count'] == new_lifetime


@pytest.mark.parametrize('history', [[], None, 'archived'])
def test_no_active_stream_matches_means_fifo_even_with_lifetime_or_past_history(history):
    state = queue([9])
    if history == 'archived':
        state['participation_history'].append({**deepcopy(state['participation_history'][0]), 'id': 'new-stream', 'users': [], 'matches': 0})
    elif history is None:
        del state['participation_history']
    else:
        state['participation_history'] = history
    QueueService(protect_next=True).add_user(state, user('new'))
    assert [u['user_id'] for u in state['waiting'][3:]] == ['tail0', 'new']


def test_stream_priority_completion_restart_undo_new_history_and_backup(tmp_path):
    db = str(tmp_path/'stream-priority.db')
    def start():
        return TestClient(create_app(db_path=db, desktop=True, onecomme=True), base_url='http://127.0.0.1')
    with start() as c:
        c.headers['Authorization'] = 'Bearer ' + c.app.state.access_keys.admin
        def add(uid):
            assert c.post('/api/control/add-user', json={'user_id': uid, 'display_name': uid}).status_code == 200
        add('returning')
        assert c.post('/api/control/correct-count', json={'user_id': 'returning', 'participation_count': 100}).status_code == 200
        assert c.post('/api/control/move-next').status_code == 200
        for i in range(6):
            add(f'filler{i}')
        add('returning')
        before = c.get('/api/state').json()
        assert before['session_participation_counts']['returning'] == 1
        assert before['participation_counts']['returning'] == 101
    with start() as c:
        c.headers['Authorization'] = 'Bearer ' + c.app.state.access_keys.admin
        p = c.app.state.services.persistence_service
        p.mutate_state(lambda s: s['participation_counts'].update(new=500))
        def add():
            assert c.post('/api/control/add-user', json={'user_id': 'new', 'display_name': 'new'}).status_code == 200
        add()
        view = c.get('/api/state').json()
        assert view['current'] == before['current']
        assert view['waiting'][:3] == before['waiting'][:3]
        assert [u['user_id'] for u in view['waiting'][3:]] == ['new', 'returning']
        assert view['participation_counts']['new'] == 500
        assert c.post('/api/control/undo').status_code == 200
        backup = c.get('/api/control/backup').json()
        assert c.post('/api/control/history/start', json={'label': 'next stream'}).status_code == 200
        add()
        view = c.get('/api/state').json()
        assert view['session_participation_counts'] == {}
        assert [u['user_id'] for u in view['waiting'][3:]] == ['returning', 'new']
        assert view['participation_counts']['returning'] == 101
        assert c.post('/api/control/restore', json={'backup': backup, 'expected_revision': view['revision']}).status_code == 200
        add()
        assert [u['user_id'] for u in c.get('/api/state').json()['waiting'][3:]] == ['new', 'returning']


def test_priority_follows_saved_video_session_without_resetting_totals(tmp_path):
    with TestClient(create_app(db_path=str(tmp_path/'videos.db'), desktop=True, onecomme=True), base_url='http://127.0.0.1') as c:
        services = c.app.state.services
        p = services.persistence_service
        p.adopt_video('abcdefghijk')
        p.mutate_state(lambda s: s.update(queue([2])))
        totals = p.get_state()['participation_counts']
        p.switch_video('lmnopqrstuv', carry=True)
        state = p.get_state()
        services.queue_service.add_user(state, user('new'))
        assert [u['user_id'] for u in state['waiting'][3:]] == ['tail0', 'new']
        p.switch_video('abcdefghijk')
        state = p.get_state()
        services.queue_service.add_user(state, user('new', 99))
        assert [u['user_id'] for u in state['waiting'][3:]] == ['new', 'tail0']
        assert state['participation_counts'] == totals


def test_comment_join_rejoin_and_cancellation_never_increment_priority_counts(tmp_path):
    with TestClient(create_app(db_path=str(tmp_path/'comments.db'), desktop=True, onecomme=True), base_url='http://127.0.0.1') as c:
        services = c.app.state.services
        p = services.persistence_service
        uid = UserIdentityService().build_comment_user_id('youtube', 'same-account')
        state = p.get_state()
        state.update(queue([2]))
        state['cooldown_seconds'] = 0
        state['participation_counts'][uid] = 500
        p.set_state(state)
        def send(mid, message):
            return services.receive_comment(ReceivedComment(
                source='youtube', userKey='same-account', displayName='Viewer',
                externalMessageId=mid, receivedAt='2026-10-19T00:00:00Z', message=message))
        send('join', '参加希望')
        state = p.get_state()
        assert [u['user_id'] for u in state['waiting'][3:]] == [uid, 'tail0']
        assert services.build_view_state()['session_participation_counts'].get(uid, 0) == 0
        assert state['participation_counts'][uid] == 500
        history = deepcopy(state['participation_history'])
        send('rejoin', '参加希望')
        send('cancel', '参加辞退')
        assert all(u['user_id'] != uid for u in p.get_state()['waiting'])
        send('join-again', '参加希望')
        state = p.get_state()
        assert [u['user_id'] for u in state['waiting'][3:]] == [uid, 'tail0']
        assert state['participation_counts'][uid] == 500
        assert state['participation_history'] == history
