from datetime import timedelta
from fastapi.testclient import TestClient
from app.main import create_app
from tests.test_onecomme import event


def frame(id='abcdefghijk', **kwargs):
    return dict(service_id='row-'+id,id=id,name='開始前の配信',enabled=True,
                url='https://www.youtube.com/watch?v='+id if id else '',state='upcoming',start_time=None,**kwargs)


def test_metadata_selects_before_comments_and_preserves_history_boundary(tmp_path):
    app=create_app(db_path=str(tmp_path/'db'),desktop=True,onecomme=True)
    with TestClient(app,base_url='http://127.0.0.1') as c:
        c.headers['Authorization']='Bearer '+app.state.access_keys.ingest
        assert c.post('/api/onecomme/heartbeat',json={'services':[frame()]}).status_code==200
        b=app.state.onecomme
        assert b.selected=='abcdefghijk'
        since=b.since
        assert c.post('/api/onecomme/heartbeat',json={'services':[frame()]}).status_code==200
        assert b.since==since
        assert c.post('/api/onecomme/comment',json=event(frame=b.selected,at=(since-timedelta(minutes=1)).isoformat())).json()['status']=='history'
        assert c.post('/api/onecomme/comment',json=event(1,frame=b.selected)).json()['status']=='accepted'
        assert c.post('/api/onecomme/heartbeat',json={'services':[frame('lmnopqrstuv')]}).status_code==200
        assert b.selected==''  # A different OneComme row must never take over.
        assert b.snapshot()['selection_reason']=='missing'
        assert c.post('/api/onecomme/comment',json=event(2,frame='abcdefghijk')).json()['status']=='unselected'
        assert b.frames=={'lmnopqrstuv':'開始前の配信'}
        assert len(app.state.services.persistence_service.get_state()['current'])==1


def test_auto_latest_ambiguity_stop_and_reconnect(tmp_path):
    from app.services.application_services import ApplicationServices
    from app.services.onecomme import OneCommeBridge
    from app.services.setup_preferences import SetupStore
    db=str(tmp_path/'db')
    bridge=OneCommeBridge(ApplicationServices(db_path=db,desktop=True),SetupStore(db))
    a,b=frame(),frame('lmnopqrstuv')
    bridge.heartbeat(services=[a,b]); assert bridge.selected==''
    assert bridge.snapshot()['selection_reason']=='multiple'
    a['start_time']=1700000000; b['start_time']=1800000000000
    bridge.heartbeat(services=[a,b]); assert bridge.selected==b['id']
    a['enabled']=False
    bridge.heartbeat(services=[a,b]); assert bridge.selected==b['id']
    bridge.select(''); bridge.heartbeat(services=[b]); assert bridge.selected==''
    restored=OneCommeBridge(bridge.services,SetupStore(db))
    restored.heartbeat(services=[b]); assert restored.selected==''
    restored.select('',mode='auto'); assert restored.selected==b['id']
    restored.heartbeat(services=[]); assert restored.selected==''
    restored.heartbeat(services=[{**frame(''),'service_id':b['service_id']}]); assert restored.snapshot()['selection_reason']=='resolving'
    restored.heartbeat(services=[a,{**b,'state':'ended'}]); assert restored.selected==''


def test_service_payload_is_bounded_and_does_not_relax_auth(tmp_path):
    with TestClient(create_app(db_path=str(tmp_path/'db'),desktop=True,onecomme=True),base_url='http://127.0.0.1') as c:
        assert c.post('/api/onecomme/heartbeat',json={'services':[]}).status_code==401
        c.headers['Authorization']='Bearer '+c.app.state.access_keys.ingest
        for s in ({**frame(),'enabled':'true'},{**frame(),'id':'bad'}, {**frame(),'url':'https://evil.test'}, {**frame(),'loggedName':'private'}):
            assert c.post('/api/onecomme/heartbeat',json={'services':[s]}).status_code==422
        assert c.post('/api/onecomme/heartbeat',json={'services':[frame()]*33}).status_code==422
        assert c.post('/api/onecomme/select',json={'mode':'auto'}).status_code==401
