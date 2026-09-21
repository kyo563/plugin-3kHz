import io
import zipfile
import json
from fastapi.testclient import TestClient
from app.main import create_app


def test_template_download_branding_and_shared_renderer(tmp_path):
    with TestClient(create_app(db_path=str(tmp_path/'db'), desktop=True, onecomme=True), base_url='http://127.0.0.1') as c:
        assert c.get('/api/onecomme/template').status_code == 401
        c.headers['Authorization'] = 'Bearer ' + c.app.state.access_keys.admin
        r = c.get('/api/onecomme/template')
        assert r.status_code == 200
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            assert len(z.namelist()) == 4
            assert json.loads(z.read('taikiretsu-display/template.json'))['name'] == '待機列整理アプリ'
            assert b'/onecomme-overlay' in z.read('taikiretsu-display/index.html')
            assert c.app.state.access_keys.admin.encode() not in b''.join(z.read(n) for n in z.namelist())
        for page in ('control', 'settings', 'obs-setup'):
            text = c.get('/' + page).text
            assert '待機列整理アプリ' in text
            assert '参加型整列プラグイン' not in text
        assert 'data-onecomme="true"' in c.get('/settings').text
        assert '現行MVP' not in c.get('/settings').text
        assert '/static/overlay.js' in c.get('/onecomme-overlay').text
        for layout, width, height in [('vertical', 480, 600), ('horizontal', 1200, 240)]:
            settings = c.get('/api/settings/overlay').json()
            settings.update(layout=layout, width=width, height=height, text_color='#ff9900', vertical_text='[NOW1]\n\n自由編集')
            assert c.post('/api/settings/overlay', json=settings).status_code == 200
            assert c.get('/api/overlay-state').json()['appearance'] == settings


def test_only_readonly_display_allows_cross_site_iframe(tmp_path):
    frame = {'Sec-Fetch-Site': 'cross-site', 'Sec-Fetch-Mode': 'navigate', 'Sec-Fetch-Dest': 'iframe'}
    with TestClient(create_app(db_path=str(tmp_path/'db'), desktop=True, onecomme=True), base_url='http://127.0.0.1') as c:
        r = c.get('/onecomme-overlay', headers=frame)
        assert r.status_code == 200
        assert 'frame-ancestors' not in r.headers['content-security-policy']
        for path in ('/control', '/settings', '/api/state', '/api/onecomme/template', '/api/overlay-state'):
            assert c.get(path, headers=frame).status_code == 403
        assert "frame-ancestors 'self'" in c.get('/control').headers['content-security-policy']
        assert c.get('/onecomme-overlay', headers={**frame, 'Origin': 'null'}).status_code == 403
    with TestClient(create_app(db_path=str(tmp_path/'old'), desktop=True), base_url='http://127.0.0.1') as c:
        assert c.get('/onecomme-overlay').status_code == 404
        assert c.get('/onecomme-overlay', headers=frame).status_code == 403
        assert 'data-onecomme' not in c.get('/settings').text
