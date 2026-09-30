from copy import deepcopy

import pytest
from fastapi.testclient import TestClient
from app.main import create_app


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(db_path=str(tmp_path/'appearance.db'), desktop=True, onecomme=True), base_url='http://127.0.0.1') as c:
        c.headers['Authorization'] = 'Bearer ' + c.app.state.access_keys.admin
        yield c


@pytest.mark.parametrize('change', [
    {'background_transparency':-1}, {'background_transparency':101},
    {'background_transparency':'50'}, {'background_transparency':True},
    {'background_transparency':50.5}, {'background_color':'#fff'},
    {'background_color':'red;opacity:0'}, {'auto_fit_font':'false'},
    {'font_size':11}, {'font_size':97},
])
def test_invalid_background_or_font_never_mutates_settings(client, change):
    before = client.get('/api/settings/overlay').json()
    assert client.post('/api/settings/overlay', json={**before, **change}).status_code == 422
    assert client.get('/api/settings/overlay').json() == before


def test_background_and_font_persist_backup_restore_reset_and_etag(client, tmp_path):
    initial = client.get('/api/settings/overlay').json()
    assert initial['background_transparency'] == 100
    assert initial['auto_fit_font'] is True
    client.post('/api/control/add-user', json={'user_id':'keep','display_name':'Keep'})
    queue = client.get('/api/state').json()['current']
    before = client.get('/api/overlay-state')
    settings = {**initial, 'background_color':'#12aBcD', 'background_transparency':35, 'font_size':56, 'auto_fit_font':False}
    assert client.post('/api/settings/overlay', json=settings).json() == settings
    response = client.get('/api/overlay-state', headers={'If-None-Match':before.headers['etag']})
    assert response.status_code == 200
    assert response.json()['appearance'] == settings
    backup = client.get('/api/control/backup').json()
    with TestClient(create_app(db_path=str(tmp_path/'appearance.db'), desktop=True, onecomme=True),base_url='http://127.0.0.1') as restarted:
        assert restarted.get('/api/overlay-state').json()['appearance'] == settings
    assert client.post('/api/settings/overlay', json={}).status_code == 200
    assert client.get('/api/settings/overlay').json() == initial
    assert client.get('/api/state').json()['current'] == queue
    legacy = deepcopy(backup)
    for key in ('background_color','background_transparency','auto_fit_font'):
        legacy['state']['overlay_settings'].pop(key)
    for source in (legacy, backup):
        revision = client.get('/api/state').json()['revision']
        assert client.post('/api/control/restore', json={'backup':source, 'expected_revision':revision}).status_code == 200
        restored = client.get('/api/settings/overlay').json()
        assert restored['background_transparency'] == (100 if source is legacy else 35)
    assert restored == settings
