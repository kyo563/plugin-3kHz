from copy import deepcopy
import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.services.application_services import ApplicationServices


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(db_path=str(tmp_path/'queue.db'), desktop=True, onecomme=True),
                    base_url='http://127.0.0.1') as c:
        c.headers['Authorization'] = 'Bearer ' + c.app.state.access_keys.admin
        yield c


def placeholders(state):
    return [u['display_name'] for section in ('now_view', 'next_view')
            for u in state[section] if u.get('is_placeholder')]


@pytest.mark.parametrize('layout', ['vertical', 'horizontal', 'custom'])
@pytest.mark.parametrize('participants', [0, 1, 4])
def test_acceptance_toggles_only_obs_empty_slots_without_changing_participants(client, layout, participants):
    settings = client.get('/api/settings/overlay').json()
    assert client.post('/api/settings/overlay', json=dict(settings, layout=layout, show_participation_number=True)).status_code == 200
    for i in range(participants):
        assert client.post('/api/control/add-user', json={'user_id': f'user{i}', 'display_name': f'Player{i}'}).status_code == 200
    initial = client.get('/api/overlay-state')
    state = initial.json()
    assert placeholders(state) == ['参加者募集中'] * (6-participants)
    actual = [u for section in ('now_view', 'next_view') for u in state[section] if not u.get('is_placeholder')]
    before = client.get('/api/state').json()
    last_etag = initial.headers['etag']
    for is_open, expected in [(False, '-'), (True, '参加者募集中'), (False, '-')]:
        assert client.post('/api/control/toggle-open').status_code == 200
        result = client.get('/api/overlay-state', headers={'If-None-Match': last_etag})
        assert result.status_code == 200
        last_etag = result.headers['etag']
        assert client.get('/api/overlay-state', headers={'If-None-Match': last_etag}).status_code == 304
        overlay = result.json()
        assert overlay['is_open'] is is_open
        assert placeholders(overlay) == [expected] * (6-participants)
        assert [u for section in ('now_view', 'next_view') for u in overlay[section] if not u.get('is_placeholder')] == actual
        after = client.get('/api/state').json()
        for key in ('current', 'waiting', 'participation_counts', 'total_match_count', 'overlay_settings'):
            assert after[key] == before[key]
        assert overlay['total_waiting_count'] == max(0, participants-3)
    assert not any(u.get('is_placeholder') for u in after['current']+after['waiting'])


def test_custom_empty_slot_labels_persist_restart_backup_and_reset(client, tmp_path):
    client.post('/api/control/add-user', json={'user_id': 'keep', 'display_name': 'Keep'})
    settings = dict(client.get('/api/settings/overlay').json(), placeholder_open_label='参加できます',
                    placeholder_closed_label='募集停止')
    assert client.post('/api/settings/overlay', json=settings).status_code == 200
    assert set(placeholders(client.get('/api/overlay-state').json())) == {'参加できます'}
    client.post('/api/control/toggle-open')
    assert set(placeholders(client.get('/api/overlay-state').json())) == {'募集停止'}
    restarted = ApplicationServices(db_path=str(tmp_path/'queue.db'), desktop=True, onecomme=True)
    assert set(placeholders(restarted.build_overlay_state())) == {'募集停止'}
    backup = client.get('/api/control/backup')
    assert backup.status_code == 200
    assert backup.json()['state']['overlay_settings'] == settings
    revision = client.get('/api/state').json()['revision']
    assert client.post('/api/control/restore', json={'backup': backup.json(), 'expected_revision': revision}).status_code == 200
    assert client.get('/api/settings/overlay').json() == settings
    preserved = client.get('/api/state').json()
    reset = client.post('/api/settings/overlay', json={'name_mode': 'youtube'}).json()
    assert reset['placeholder_open_label'] == '参加者募集中' and reset['placeholder_closed_label'] == '-'
    assert placeholders(client.get('/api/overlay-state').json()) == ['-'] * 5
    assert client.get('/api/state').json()['current'] == preserved['current']


def test_legacy_database_and_backup_default_new_labels_without_losing_custom_settings(client, tmp_path):
    settings = dict(client.get('/api/settings/overlay').json(), now_label='対局')
    for key in ('placeholder_open_label', 'placeholder_closed_label'): settings.pop(key)
    # Simulate a pre-update database that has neither field.
    with sqlite3.connect(tmp_path/'queue.db') as db:
        db.execute("UPDATE app_state SET value=? WHERE key='overlay_settings'", (json.dumps(settings),))
    restored = ApplicationServices(db_path=str(tmp_path/'queue.db'), desktop=True, onecomme=True)
    assert restored.build_overlay_state()['appearance']['now_label'] == '対局'
    assert restored.build_overlay_state()['appearance']['placeholder_closed_label'] == '-'
    backup = deepcopy(client.get('/api/control/backup').json())
    for key in ('placeholder_open_label', 'placeholder_closed_label'): backup['state']['overlay_settings'].pop(key)
    revision = client.get('/api/state').json()['revision']
    response = client.post('/api/control/restore', json={'backup': backup, 'expected_revision': revision})
    assert response.status_code == 200
    assert response.json()['overlay_settings']['now_label'] == '対局'
    assert response.json()['overlay_settings']['placeholder_open_label'] == '参加者募集中'


@pytest.mark.parametrize('field', ['placeholder_open_label', 'placeholder_closed_label'])
@pytest.mark.parametrize('value', ['x'*41, 7, True, []])
def test_invalid_empty_slot_label_is_rejected_without_mutation(client, field, value):
    before = client.get('/api/state').json()
    assert client.post('/api/settings/overlay', json=dict(before['overlay_settings'], **{field: value})).status_code == 422
    assert client.get('/api/state').json() == before


def test_empty_labels_and_markup_are_literal_settings_and_ingest_cannot_edit_them(client):
    settings = dict(client.get('/api/settings/overlay').json(), placeholder_open_label='',
                    placeholder_closed_label='<b>募集停止</b>')
    assert client.post('/api/settings/overlay', json=settings).status_code == 200
    assert placeholders(client.get('/api/overlay-state').json()) == [''] * 6
    client.post('/api/control/toggle-open')
    assert placeholders(client.get('/api/overlay-state').json()) == ['<b>募集停止</b>'] * 6
    assert client.post('/api/settings/overlay', json=settings, headers={
        'Authorization': 'Bearer ' + client.app.state.access_keys.ingest}).status_code == 401


def test_settings_controls_are_onecomme_only_and_standalone_display_is_unchanged(client, tmp_path):
    page = client.get('/settings').text
    for key in ('placeholder_open_label', 'placeholder_closed_label'):
        assert page.count(f'name="{key}"') == 1
    assert '空き枠の文言（受付中）' in page and '空き枠の文言（受付停止中）' in page
    with TestClient(create_app(db_path=str(tmp_path/'standalone'/'q.db'), desktop=True),
                    base_url='http://127.0.0.1') as standalone:
        standalone.headers['Authorization'] = 'Bearer ' + standalone.app.state.access_keys.admin
        standalone.post('/api/control/toggle-open')
        assert placeholders(standalone.get('/api/overlay-state').json()) == ['参加者募集中'] * 6
        assert 'name="placeholder_open_label"' not in standalone.get('/settings').text
