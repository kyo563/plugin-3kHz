from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.schemas.comment import ReceivedComment
from app.services.application_services import ApplicationServices
from app.services.reception_schedule import ReceptionSchedule, ScheduleSettings
from app.services.user_identity_service import UserIdentityService


def user(key, count=0):
    return {'user_id': key, 'display_name': key, 'participation_count': count}


def seed(services, waiting, *, opened=False):
    def populate(state):
        state.update(is_open=opened, priority_mode=True, cooldown_seconds=0,
                     current=[user(f'now{i}') for i in range(3)],
                     waiting=[user(f'wait{i}', 10) for i in range(waiting)],
                     participation_counts={f'wait{i}': 10 for i in range(waiting)})
    services.persistence_service.mutate_state(populate)


def send(services, key, mid=None, message='参加希望'):
    return services.receive_comment(ReceivedComment(
        source='youtube', userKey=key, displayName=key, externalMessageId=mid or key,
        receivedAt='2026-10-29T00:00:00Z', message=message))


@pytest.mark.parametrize('count', [0, 1, 2, 3, 4, 5, 6, 7, 8, 9])
def test_only_last_waiting_group_is_completed_and_full_queue_stays_closed(tmp_path, count):
    services = ApplicationServices(db_path=str(tmp_path/'queue.db'), desktop=True, onecomme=True)
    seed(services, count)
    before = services.persistence_service.get_state()
    slots = 3-count % 3 if count % 3 else 0
    for i in range(4):
        send(services, f'new{i}', message=f'参加希望『Name{i}』')
        state = services.persistence_service.get_state()
        assert state['is_open'] is False
        assert state['current'] == before['current']
        assert state['waiting'][:count] == before['waiting']
        assert len(state['waiting']) == count + min(i+1, slots)
        assert services.build_overlay_state()['final_group_slots'] == max(0, slots-i-1)
    state = services.persistence_service.get_state()
    for i in range(slots, 4):
        uid = UserIdentityService().build_comment_user_id('youtube', f'new{i}')
        assert uid not in state['comment_names']
        assert uid not in state['user_action_locks']


def test_existing_users_are_unchanged_and_cancel_reopens_one_slot(tmp_path):
    services = ApplicationServices(db_path=str(tmp_path/'queue.db'), desktop=True, onecomme=True)
    seed(services, 1)
    send(services, 'viewer', 'first', '参加希望『Original』')
    before = services.persistence_service.get_state()
    send(services, 'viewer', 'repeat', '参加希望『Changed』')
    after = services.persistence_service.get_state()
    for key in ('current', 'waiting', 'comment_names', 'user_action_locks', 'participation_counts'):
        assert after[key] == before[key]
    send(services, 'last')
    assert services.build_view_state()['final_group_slots'] == 0
    send(services, 'viewer', 'cancel', '参加辞退')
    assert services.build_view_state()['final_group_slots'] == 1
    send(services, 'replacement')
    assert services.build_view_state()['final_group_slots'] == 0
    assert services.persistence_service.get_state()['waiting'][-1]['display_name'] == 'replacement'


def test_concurrent_arrivals_do_not_create_another_group(tmp_path):
    services = ApplicationServices(db_path=str(tmp_path/'queue.db'), desktop=True, onecomme=True)
    seed(services, 4)
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda n: send(services, f'viewer{n}'), range(20)))
    state = services.persistence_service.get_state()
    assert len(state['waiting']) == 6
    assert state['is_open'] is False


def test_restart_and_undo_recalculate_capacity_and_standalone_stays_closed(tmp_path):
    path = str(tmp_path/'queue.db')
    services = ApplicationServices(db_path=path, desktop=True, onecomme=True)
    seed(services, 3)
    services.persistence_service.manual_mutate(
        lambda s: services.queue_service.remove_user_by_id(s, 'wait0'))
    assert services.build_view_state()['final_group_slots'] == 1
    services.persistence_service.undo()
    assert services.build_view_state()['final_group_slots'] == 0
    seed(services, 2)
    restarted = ApplicationServices(db_path=path, desktop=True, onecomme=True)
    assert restarted.build_overlay_state()['final_group_slots'] == 1
    standalone = ApplicationServices(db_path=str(tmp_path/'standalone.db'), desktop=True)
    seed(standalone, 2)
    send(standalone, 'blocked')
    assert len(standalone.persistence_service.get_state()['waiting']) == 2
    assert 'final_group_slots' not in standalone.build_overlay_state()


def test_scheduled_close_keeps_final_group_open_without_repeating_notification(tmp_path):
    services = ApplicationServices(db_path=str(tmp_path/'queue.db'), desktop=True, onecomme=True)
    seed(services, 4, opened=True)
    notices = []
    class Bot:
        def announce_closed(self):
            notices.append('closed')
    now = datetime(2026, 10, 29, 22, 0)
    schedule = ReceptionSchedule(services, Bot(), clock=lambda: now)
    schedule.configure(ScheduleSettings(enabled=True, time='22:01'))
    now += timedelta(minutes=1)
    schedule.tick()
    assert services.build_view_state()['final_group_slots'] == 2
    send(services, 'new1')
    send(services, 'new2')
    schedule.tick()
    assert notices == ['closed']
    assert services.build_view_state()['final_group_slots'] == 0
    services.move_next()
    assert services.build_view_state()['final_group_slots'] == 0
    assert len(services.persistence_service.get_state()['waiting']) == 3


def test_fill_respects_cooldown_and_api_reports_capacity_without_exposing_ids(tmp_path):
    with TestClient(create_app(db_path=str(tmp_path/'queue.db'), desktop=True, onecomme=True),
                    base_url='http://127.0.0.1') as client:
        client.headers['Authorization'] = 'Bearer '+client.app.state.access_keys.admin
        services = client.app.state.services
        seed(services, 1)
        uid = UserIdentityService().build_comment_user_id('youtube', 'locked')
        def lock(state):
            state['cooldown_seconds'] = 40
            services.apply_service._cooldown_service.mark_changed(state, uid)
        services.persistence_service.mutate_state(lock)
        send(services, 'locked')
        assert len(services.persistence_service.get_state()['waiting']) == 1
        overlay = client.get('/api/overlay-state')
        assert overlay.json()['final_group_slots'] == 2
        assert 'user_id' not in overlay.text
        send(services, 'allowed')
        updated = client.get('/api/overlay-state', headers={'If-None-Match': overlay.headers['etag']})
        assert updated.status_code == 200
        assert updated.json()['final_group_slots'] == 1
        assert client.get('/api/state').json()['final_group_slots'] == 1
