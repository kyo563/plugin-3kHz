from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.schemas.overlay_settings import OverlaySettings
from app.services.queue_service import QueueService
from app.services.overlay_state_service import OverlayStateService


def user(uid, count=0):
    return {'user_id': uid, 'display_name': uid, 'participation_count': count}


def queue(tail_counts=()):
    return {'is_open': True, 'priority_mode': True, 'logs': [],
            'current': [user(f'now{i}', 9) for i in range(3)],
            'waiting': [user(f'next{i}', 9) for i in range(3)]
                       + [user(f'tail{i}', count) for i, count in enumerate(tail_counts)]}


@pytest.mark.parametrize('counts,expected', [
    ([], ['new']), ([4], ['new', 'tail0']),
    ([0, 0, 4, 2], ['tail0', 'tail1', 'new', 'tail2', 'tail3']),
    ([0, 0], ['tail0', 'tail1', 'new']),
])
def test_priority_never_changes_now_next_and_preserves_tail_order(counts, expected):
    service = QueueService(protect_next=True)
    state = queue(counts)
    now, upcoming = deepcopy(state['current']), deepcopy(state['waiting'][:3])
    service.add_user(state, user('new'))
    assert state['current'] == now
    assert state['waiting'][:3] == upcoming
    assert [u['user_id'] for u in state['waiting'][3:]] == expected


def test_equal_priority_arrivals_stay_fifo_and_new_next_is_protected():
    service = QueueService(protect_next=True)
    state = queue([4, 4, 4, 4])
    service.add_user(state, user('first'))
    service.add_user(state, user('second'))
    assert [u['user_id'] for u in state['waiting'][3:5]] == ['first', 'second']
    service.move_next(state)
    now, upcoming = deepcopy(state['current']), deepcopy(state['waiting'][:3])
    service.add_user(state, user('third'))
    assert state['current'] == now
    assert state['waiting'][:3] == upcoming
    assert state['waiting'][3]['user_id'] == 'third'


@pytest.mark.parametrize('waiting_count', [0, 1, 2])
def test_next_vacancy_is_filled_without_displacing_existing_people(waiting_count):
    service = QueueService(protect_next=True)
    state = queue()
    state['waiting'] = state['waiting'][:waiting_count]
    before = deepcopy(state['waiting'])
    service.add_user(state, user('new'))
    assert state['waiting'][:-1] == before
    assert state['waiting'][-1]['user_id'] == 'new'


def test_priority_off_and_now_vacancy_keep_normal_behavior():
    service = QueueService(protect_next=True)
    state = queue([5])
    state['priority_mode'] = False
    service.add_user(state, user('new'))
    assert state['waiting'][-1]['user_id'] == 'new'
    state['current'].pop()
    before = deepcopy(state['waiting'])
    service.add_user(state, user('vacancy'))
    assert state['current'][-1]['user_id'] == 'vacancy'
    assert state['waiting'] == before


@pytest.mark.parametrize('onecomme', [False, True])
def test_plugin_policy_is_wired_without_changing_standalone(tmp_path, onecomme):
    with TestClient(create_app(db_path=str(tmp_path/'mode.db'), desktop=True, onecomme=onecomme), base_url='http://127.0.0.1') as c:
        services = c.app.state.services
        assert services.queue_service.protect_next is onecomme
        c.headers['Authorization'] = 'Bearer ' + c.app.state.access_keys.admin
        assert ('name="show_participation_number"' in c.get('/settings').text) is onecomme
        state = services.persistence_service.get_state()
        state.update(queue([4]))
        services.persistence_service.set_state(state)
        assert c.post('/api/control/add-user', json={'user_id':'new', 'display_name':'new'}).status_code == 200
        waiting = c.get('/api/state').json()['waiting']
        assert next(i for i, u in enumerate(waiting) if u['user_id'] == 'new') == (3 if onecomme else 2)


@pytest.mark.parametrize('mode,expected', [
    ('youtube', '@handle'), ('declared', 'Player'),
    ('youtube_declared', '@handle（Player）'), ('declared_youtube', 'Player（@handle）'),
])
def test_number_uses_session_counts_and_selected_name_only(mode, expected):
    state = queue()
    state['current'] = [{**user('known', 90), 'youtube_handle':'@handle', 'declared_player_name':'Player'}]
    state['waiting'] = [user('new')]
    state['participation_history'] = [{'matches':1, 'users':[{'user_id':'known', 'count':1}]}]
    state['overlay_settings'] = OverlaySettings(name_mode=mode, show_participation_number=True).model_dump()
    view = QueueService().build_view_state(state)
    overlay = OverlayStateService().build_overlay_state(view)
    assert overlay['now_view'][0] == {'display_name':expected + ' *2回目'}
    assert overlay['now_view'][1] == {'display_name':'参加者募集中', 'is_placeholder':True}
    assert overlay['next_view'][0] == {'display_name':'new *1回目'}
    state['overlay_settings']['show_participation_number'] = False
    assert OverlayStateService().build_overlay_state(QueueService().build_view_state(state))['now_view'][0] == {'display_name':expected}


def test_number_setting_restart_backup_reset_undo_and_new_stream(tmp_path):
    db = str(tmp_path/'number.db')
    def start():
        return TestClient(create_app(db_path=db, desktop=True, onecomme=True), base_url='http://127.0.0.1')
    with start() as c:
        c.headers['Authorization'] = 'Bearer ' + c.app.state.access_keys.admin
        assert c.get('/api/settings/overlay').json()['show_participation_number'] is False
        assert c.post('/api/settings/overlay', json={'show_participation_number':'true'}).status_code == 422
        assert c.post('/api/settings/overlay', json={'show_participation_number':True, 'name_mode':'youtube'}).status_code == 200
        for uid in ['returning', 'other1', 'other2']:
            assert c.post('/api/control/add-user', json={'user_id':uid, 'display_name':uid}).status_code == 200
        c.post('/api/control/correct-count', json={'user_id':'returning', 'participation_count':25})
        assert c.get('/api/overlay-state').json()['now_view'][0]['display_name'] == 'returning *1回目'
        c.post('/api/control/move-next')
        c.post('/api/control/undo')
        assert c.get('/api/overlay-state').json()['now_view'][0]['display_name'] == 'returning *1回目'
        c.post('/api/control/move-next')
        c.post('/api/control/add-user', json={'user_id':'returning', 'display_name':'returning'})
        assert c.get('/api/overlay-state').json()['now_view'][0]['display_name'] == 'returning *2回目'
        backup = c.get('/api/control/backup').json()
        assert backup['state']['overlay_settings']['show_participation_number'] is True
    with start() as c:
        c.headers['Authorization'] = 'Bearer ' + c.app.state.access_keys.admin
        assert c.get('/api/overlay-state').json()['now_view'][0]['display_name'] == 'returning *2回目'
        assert c.post('/api/control/history/start', json={'label':'new stream'}).status_code == 200
        assert c.get('/api/overlay-state').json()['now_view'][0]['display_name'] == 'returning *1回目'
        revision = c.get('/api/state').json()['revision']
        assert c.post('/api/control/restore', json={'backup':backup, 'expected_revision':revision}).status_code == 200
        assert c.get('/api/overlay-state').json()['now_view'][0]['display_name'] == 'returning *2回目'
        before = c.get('/api/state').json()
        assert c.post('/api/settings/overlay', json={'name_mode':'youtube'}).status_code == 200
        assert c.get('/api/overlay-state').json()['now_view'][0]['display_name'] == 'returning'
        after = c.get('/api/state').json()
        assert after['current'] == before['current']
        assert after['participation_counts'] == before['participation_counts']
