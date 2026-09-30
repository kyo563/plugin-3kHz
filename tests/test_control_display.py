from fastapi.testclient import TestClient
from app.main import create_app
from app.schemas.control_display import ControlDisplaySettings


def test_visibility_survives_restart_without_mutating_queue_or_undo(tmp_path):
    path = str(tmp_path / 'queue.db')
    with TestClient(create_app(db_path=path, desktop=True, onecomme=True), base_url='http://127.0.0.1') as c:
        endpoint = '/api/settings/control-display'
        assert c.get(endpoint).status_code == 401
        c.headers['Authorization'] = 'Bearer ' + c.app.state.access_keys.ingest
        assert c.post(endpoint, json={}).status_code == 401
        c.headers['Authorization'] = 'Bearer ' + c.app.state.access_keys.admin
        assert c.get(endpoint).json() == ControlDisplaySettings().model_dump()
        c.post('/api/control/add-user', json={'display_name':'Test'})
        before = c.get('/api/state').json()
        overlay = c.get('/api/settings/overlay').json()
        settings = dict(avatar=False, username=True, alias=False, memo=False, count=False, order=True)
        assert c.post(endpoint, json=settings).json() == settings
        assert c.get('/api/state').json() == before
        assert c.get('/api/settings/overlay').json() == overlay
        assert c.post('/api/control/undo').status_code == 200
        assert c.get(endpoint).json() == settings
        assert c.post(endpoint, json={**settings, 'memo':'false'}).status_code == 422
        assert c.post(endpoint, json={**settings, 'extra':True}).status_code == 422
        assert c.get(endpoint).json() == settings
        assert 'control_display' not in c.get('/api/overlay-state').json()
        c.post('/api/control/reset')
        assert c.get(endpoint).json() == settings
    with TestClient(create_app(db_path=path, desktop=True, onecomme=True), base_url='http://127.0.0.1') as restarted:
        restarted.headers['Authorization'] = 'Bearer ' + restarted.app.state.access_keys.admin
        assert restarted.get(endpoint).json() == settings


def test_visibility_page_and_endpoint_are_onecomme_only(tmp_path):
    for mode in (False, True):
        with TestClient(create_app(db_path=str(tmp_path / str(mode)), desktop=True, onecomme=mode), base_url='http://127.0.0.1') as c:
            c.headers['Authorization'] = 'Bearer ' + c.app.state.access_keys.admin
            html = c.get('/control').text
            assert ('id="control-display-options"' in html) == mode
            assert ('/static/control-display.js' in html) == mode
            assert ('data-onecomme="true"' in html) == mode
            assert c.get('/api/settings/control-display').status_code == (200 if mode else 404)
            if mode:
                assert html.index('id="control-display-options"') < html.index('id="now"')
                assert html.index('/static/auth.js') < html.index('/static/control-display.js') < html.index('/static/control.js')
            assert 'control-display' not in c.get('/overlay').text
