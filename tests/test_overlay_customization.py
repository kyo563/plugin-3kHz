from copy import deepcopy
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.schemas.overlay_settings import OverlaySettings
from app.services.application_services import ApplicationServices

@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(db_path=str(tmp_path/'state.db'), desktop=True),base_url='http://127.0.0.1') as c:
        c.headers['Authorization']='Bearer '+c.app.state.access_keys.admin
        yield c

@pytest.mark.parametrize('waiting',[0,1,2,3,4,5,6,7])
def test_summary_includes_next_excludes_now_and_placeholders(client,waiting):
    for i in range(3+waiting):
        assert client.post('/api/control/add-user',json={'display_name':f'Name{i}','user_id':f'u{i}'}).status_code==200
    public=client.get('/api/overlay-state').json()
    assert public['total_waiting_count']==waiting
    assert public['total_waiting_group_count']==(waiting+2)//3
    assert public['queue_count']==max(0,waiting-3)
    assert 'participation_counts' not in public and 'waiting' not in public
    assert all('user_id' not in u and 'participation_count' not in u for u in public['now_view']+public['next_view'])


def test_settings_update_etag_backup_restart_and_legacy_backup(client,tmp_path):
    before=client.get('/api/overlay-state')
    settings=OverlaySettings(width=320,height=450,font_size=24,open_label='募集中',closed_label='締切',now_label='参加中',next_label='次の方',queue_label='').model_dump()
    assert client.post('/api/settings/overlay',json=settings).status_code==200
    after=client.get('/api/overlay-state',headers={'If-None-Match':before.headers['etag']})
    assert after.status_code==200 and after.json()['appearance']==settings
    assert client.app.state.services.build_view_state()['current']==[]
    restarted=ApplicationServices(db_path=str(tmp_path/'state.db'),desktop=True)
    assert restarted.build_overlay_state()['appearance']==settings
    backup=client.get('/api/control/backup').json()
    assert backup['state']['overlay_settings']==settings
    legacy=deepcopy(backup); legacy['state'].pop('overlay_settings')
    for source in (legacy,backup):
        revision=client.get('/api/state').json()['revision']
        assert client.post('/api/control/restore',json={'backup':source,'expected_revision':revision}).status_code==200
    assert client.get('/api/settings/overlay').json()==settings

@pytest.mark.parametrize('change',[{'width':159},{'height':199},{'font_size':97},{'width':True},{'width':'480'},{'open_label':'a'*41},{'css':'background:red'}])
def test_invalid_settings_do_not_mutate_state(client,change):
    before=client.get('/api/state').json()
    assert client.post('/api/settings/overlay',json={**OverlaySettings().model_dump(),**change}).status_code==422
    assert client.get('/api/state').json()==before


def test_labels_are_text_and_ingest_cannot_modify(client):
    settings=OverlaySettings(now_label='<img src=x onerror=alert(1)>').model_dump()
    assert client.post('/api/settings/overlay',json=settings).status_code==200
    assert client.get('/api/overlay-state').json()['appearance']['now_label']==settings['now_label']
    ingest={'Authorization':'Bearer '+client.app.state.access_keys.ingest}
    assert client.post('/api/settings/overlay',json=settings,headers=ingest).status_code==401


def test_reset_settings_preserves_queue_and_match_data(client, tmp_path):
    client.post('/api/control/add-user', json={'display_name':'Keep', 'user_id':'keep'})
    client.post('/api/settings/overlay', json={'layout':'custom', 'custom_text':'changed', 'width':900, 'fonts':{'all':'mincho'}})
    before = client.app.state.services.persistence_service.get_state()
    response = client.post('/api/settings/overlay', json={'name_mode':'youtube'})
    expected = OverlaySettings(name_mode='youtube').model_dump()
    assert response.status_code == 200
    assert response.json() == expected
    after = client.app.state.services.persistence_service.get_state()
    for key in before:
        if key not in ('overlay_settings', 'revision'):
            assert after[key] == before[key], key
    restarted = ApplicationServices(db_path=str(tmp_path/'state.db'), desktop=True)
    assert restarted.build_overlay_state()['appearance'] == expected


def test_both_editable_presets_survive_switch_and_restart(client, tmp_path):
    settings = OverlaySettings(width=800, height=600, vertical_text='[受付]\n\n[NOW1]\n', horizontal_now_text='[NOW見出し]\n\n[NOW1]\n[NOW2]\n[NOW3]').model_dump()
    for layout in ('vertical', 'horizontal', 'vertical'):
        settings['layout'] = layout
        assert client.post('/api/settings/overlay', json=settings).json() == settings
        restarted = ApplicationServices(db_path=str(tmp_path/'state.db'), desktop=True)
        assert restarted.build_overlay_state()['appearance'] == settings
