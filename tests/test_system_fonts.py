import sys
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.services.system_fonts import enumerate_windows_fonts, font_id


def test_system_font_catalog_is_admin_only_and_plugin_only(tmp_path, monkeypatch):
    fonts = [{'id':font_id('游ゴシック'), 'name':'游ゴシック', 'japanese':True}]
    monkeypatch.setattr('app.services.system_fonts.enumerate_windows_fonts', lambda: fonts)
    for plugin in (True, False):
        with TestClient(create_app(db_path=str(tmp_path/str(plugin)), desktop=True, onecomme=plugin), base_url='http://127.0.0.1') as c:
            assert c.get('/api/fonts/system').status_code == 401
            c.headers['Authorization'] = 'Bearer ' + c.app.state.access_keys.ingest
            assert c.get('/api/fonts/system').status_code == 401
            c.headers['Authorization'] = 'Bearer ' + c.app.state.access_keys.admin
            assert c.get('/api/fonts/system', headers={'Origin':'https://example.org'}).status_code == 403
            result = c.get('/api/fonts/system')
            assert result.status_code == (200 if plugin else 404)
            if plugin:
                assert result.json() == fonts
            assert ('id="obs-font-select"' in c.get('/settings').text) is plugin


def test_obs_only_font_roundtrip_backup_legacy_and_reset(tmp_path):
    db = str(tmp_path/'fonts.db')
    with TestClient(create_app(db_path=db, desktop=True, onecomme=True), base_url='http://127.0.0.1') as c:
        c.headers['Authorization'] = 'Bearer ' + c.app.state.access_keys.admin
        initial = c.get('/api/settings/overlay').json()
        settings = deepcopy(initial)
        settings['fonts'].update(all='meiryo', ui_body='mincho', obs_all=font_id('游ゴシック'), now_names='gothic')
        assert c.post('/api/settings/overlay', json=settings).json() == settings
        backup = c.get('/api/control/backup').json()
        assert backup['state']['overlay_settings']['fonts'] == settings['fonts']
        assert c.get('/api/overlay-state').json()['appearance']['fonts'] == settings['fonts']
    with TestClient(create_app(db_path=db, desktop=True, onecomme=True), base_url='http://127.0.0.1') as c:
        c.headers['Authorization'] = 'Bearer ' + c.app.state.access_keys.admin
        assert c.get('/api/settings/overlay').json() == settings
        c.post('/api/settings/overlay', json={})
        assert c.get('/api/settings/overlay').json() == initial
        revision = c.get('/api/state').json()['revision']
        assert c.post('/api/control/restore', json={'backup':backup, 'expected_revision':revision}).status_code == 200
        assert c.get('/api/settings/overlay').json() == settings
        del settings['fonts']['obs_all']
        assert c.post('/api/settings/overlay', json=settings).json()['fonts']['obs_all'] is None


@pytest.mark.parametrize('value', ['system:', 'system:ff', 'system:00', 'system:123', font_id('a\n'), font_id(' '), font_id('x'*129), 'system:../../secret'])
def test_system_font_id_rejects_invalid_input(value):
    from pydantic import ValidationError
    from app.schemas.overlay_settings import FontSettings
    with pytest.raises(ValidationError):
        FontSettings(obs_all=value)


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows API')
def test_windows_enumeration_has_unique_families_without_paths():
    fonts = enumerate_windows_fonts()
    assert fonts
    assert len({f['id'] for f in fonts}) == len(fonts)
    assert all(set(f) == {'id', 'name', 'japanese'} and not f['name'].startswith('@') for f in fonts)
    assert all(f['id'] == font_id(f['name']) for f in fonts)
    flags = [f['japanese'] for f in fonts]
    assert flags == sorted(flags, reverse=True)
