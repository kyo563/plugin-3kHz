import io
import zipfile
import json
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import urlsplit, parse_qs
from fastapi.testclient import TestClient
from app.main import create_app


def test_obs_named_drag_link_uses_public_display_not_management(tmp_path):
    class Links(HTMLParser):
        href = None

        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if tag == 'a' and attrs.get('id') == 'obs-drag-source':
                assert attrs['draggable'] == 'true'
                self.href = attrs['href']

    with TestClient(create_app(db_path=str(tmp_path / 'db'), desktop=True, onecomme=True), base_url='http://127.0.0.1:18765') as c:
        page = c.get('/obs-setup')
        assert page.status_code == 200
        links = Links()
        links.feed(page.text)
        url = urlsplit(links.href)
        assert url.netloc == '127.0.0.1:18765'
        assert url.path == '/onecomme-overlay'
        assert not url.fragment
        assert parse_qs(url.query) == {'layer-name': ['待機列表示'], 'layer-width': ['1200'], 'layer-height': ['600']}
        # OBS has no management cookie or token; the page and display data must
        # work without widening access to private state or settings.
        c.cookies.clear()
        assert c.get(links.href).status_code == 200
        assert c.get('/api/overlay-state').status_code == 200
        assert c.get('/api/state').status_code == 401
        assert c.get('/static/onecomme-obs-setup.css').status_code == 200
        assert c.app.state.access_keys.admin not in links.href


def test_template_download_branding_and_shared_renderer(tmp_path):
    with TestClient(create_app(db_path=str(tmp_path/'db'), desktop=True, onecomme=True), base_url='http://127.0.0.1') as c:
        assert c.get('/api/onecomme/template').status_code == 401
        c.headers['Authorization'] = 'Bearer ' + c.app.state.access_keys.admin
        r = c.get('/api/onecomme/template')
        assert r.status_code == 200
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            assert set(z.namelist()) == {
                'taikiretsu-display/' + name
                for name in ('index.html', 'script.js', 'style.css', 'template.json', 'thumb.png')
            }
            assert json.loads(z.read('taikiretsu-display/template.json'))['name'] == '待機列整理アプリ｜OBS表示'
            assert json.loads(z.read('taikiretsu-display/template.json'))['description'] == 'コメント欄から参加者をリストアップするプラグインです。表示設定はプラグイン管理画面から。'
            thumbnail = z.read('taikiretsu-display/thumb.png')
            assert thumbnail.startswith(b'\x89PNG\r\n\x1a\n')
            assert thumbnail == (Path(__file__).resolve().parents[1] / 'static' / 'onecomme-template' / 'thumb.png').read_bytes()
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
