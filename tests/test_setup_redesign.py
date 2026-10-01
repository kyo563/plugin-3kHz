from datetime import datetime, timezone, timedelta
from html.parser import HTMLParser
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.services.application_services import ApplicationServices
from app.services.setup_preferences import SetupStore
from app.services.onecomme import OneCommeBridge
from app.schemas.comment import ReceivedComment


def test_setup_persistence_authority_and_no_queue_change(tmp_path):
    db = str(tmp_path/'queue.db')
    saved = {'completed':True,'deferred':False,'step':4,'use_bot':False,'use_obs':True}
    for first in (True, False):
        with TestClient(create_app(db_path=db,desktop=True,onecomme=True),base_url='http://127.0.0.1') as c:
            assert c.get('/api/setup').status_code == 401
            c.headers['Authorization'] = 'Bearer ' + c.app.state.access_keys.ingest
            assert c.post('/api/setup', json=saved).status_code == 401
            c.headers['Authorization'] = 'Bearer ' + c.app.state.access_keys.admin
            if first:
                assert not c.get('/api/setup').json()['completed']
                before = c.get('/api/state').json()
                assert c.post('/api/setup',json=saved).json() == saved
                assert c.get('/api/state').json() == before
                assert c.post('/api/setup',json={**saved,'step':5}).status_code == 422
                assert c.post('/api/setup',json={**saved,'completed':'true'}).status_code == 422
            assert c.get('/api/setup').json() == saved


def test_redesigned_pages_have_unique_ids_and_legacy_redirects(tmp_path):
    class Ids(HTMLParser):
        def __init__(self): super().__init__(); self.ids=[]
        def handle_starttag(self, tag, attrs):
            values=dict(attrs)
            if 'id' in values: self.ids.append(values['id'])
    with TestClient(create_app(db_path=str(tmp_path/'db'),desktop=True,onecomme=True),base_url='http://127.0.0.1') as c:
        page = c.get('/settings').text
        parsed=Ids(); parsed.feed(page)
        assert len(parsed.ids) == len(set(parsed.ids))
        for key in ('settings-general-panel','settings-obs-panel','settings-bot-panel','setup-wizard','onecomme-stream','copy-control','obs-check','bot-test-dialog'):
            assert key in parsed.ids
        assert 'waiting-expand' in c.get('/control').text
        assert c.get('/obs-setup',follow_redirects=False).headers['location'] == '/settings?tab=obs'
        assert c.get('/bot',follow_redirects=False).headers['location'] == '/settings?tab=bot'


def test_selected_stream_restores_but_old_comments_do_not(tmp_path):
    path = str(tmp_path/'db')
    services = ApplicationServices(db_path=path,desktop=True)
    prefs = SetupStore(path)
    bridge = OneCommeBridge(services,prefs)
    bridge.frames['member-live']='Members'
    bridge.select('member-live')
    restored=OneCommeBridge(services,SetupStore(path))
    assert restored.selected == 'member-live'
    def comment(n, at):
        return ReceivedComment(source='youtube',userKey=str(n),displayName='Member',externalMessageId=str(n),message='参加希望',receivedAt=at,badges={'member':True})
    old=(datetime.now(timezone.utc)-timedelta(minutes=1)).isoformat()
    assert restored.receive('member-live','Members',comment(1,old))['status']=='history'
    assert restored.receive('other','Other',comment(2,datetime.now(timezone.utc).isoformat()))['status']=='unselected'
    assert restored.receive('member-live','Members',comment(3,datetime.now(timezone.utc).isoformat()))['status']=='accepted'
    assert len(services.build_view_state()['current']) == 1
    assert restored.snapshot()['results']['history'] == 1
    restored.select('')
    assert OneCommeBridge(services,prefs).selected == ''


@pytest.mark.parametrize('count',[20,21,128,129,150])
def test_display_limits_never_truncate_internal_queue(tmp_path,count):
    services=ApplicationServices(db_path=str(tmp_path/'db'),desktop=True)
    waiting=[{'user_id':f'u{i}','display_name':f'User{i}','participation_count':0} for i in range(count)]
    services.persistence_service.mutate_state(lambda s:s.update(waiting=waiting))
    assert len(services.build_view_state()['waiting']) == count
    state=services.persistence_service.get_state()
    services.queue_service.reorder_waiting(state,[u['user_id'] for u in waiting[:128]][::-1]+[u['user_id'] for u in waiting[128:]])
    assert len(state['waiting']) == count
    if count>128: assert state['waiting'][128]['user_id']=='u128'
    called = set()
    while state['waiting']:
        services.queue_service.move_next(state)
        called.update(u['user_id'] for u in state['current'])
    assert called == {f'u{i}' for i in range(count)}
