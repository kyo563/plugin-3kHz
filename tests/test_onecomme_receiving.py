"""Local receiving-row fallback, with no Google requests or production DB."""
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from app.main import create_app
from tests.test_onecomme import event


def row(service='restricted-row', receive='', video='', **extra):
    return {**dict(service_id=service, id=video, receive_id=receive, name='限定配信',
                enabled=True, state='unknown', start_time=None,
                url='https://www.youtube.com/watch?v='+video if video else ''), **extra}


def test_receiving_row_without_video_metadata_accepts_first_comment_and_restores(tmp_path):
    db=str(tmp_path/'receiving.db')
    with TestClient(create_app(db_path=db,desktop=True,onecomme=True),base_url='http://127.0.0.1') as c:
        c.headers['Authorization']='Bearer '+c.app.state.access_keys.ingest
        c.post('/api/onecomme/heartbeat',json={'services':[row()]})
        b=c.app.state.onecomme
        assert not b.selected and b.snapshot()['ready_to_receive']
        first=event(frame='opaque-room')
        first['service_id']='restricted-row'
        boundary=b.since
        assert c.post('/api/onecomme/heartbeat',json={'services':[row(receive='opaque-room')]}).status_code==200
        assert b.selected=='opaque-room' and b.since==boundary
        assert c.post('/api/onecomme/comment',json=first).json()['status']=='accepted'
        assert c.post('/api/onecomme/comment',json=first).json()['duplicate']
        state=b.services.build_overlay_state()
        assert state['now_view'][0]['display_name']=='User0'
        assert b.snapshot()['services'][0]['id']==''
        assert b.snapshot()['services'][0]['queue_id']=='opaque-room'
        # Receipt stays the local session key when video metadata later resolves.
        c.post('/api/onecomme/heartbeat',json={'services':[row(receive='opaque-room',video='abcdefghijk')]})
        assert b.selected=='opaque-room' and b.pending is None
    with TestClient(create_app(db_path=db,desktop=True,onecomme=True),base_url='http://127.0.0.1') as c:
        c.headers['Authorization']='Bearer '+c.app.state.access_keys.ingest
        c.post('/api/onecomme/heartbeat',json={'services':[row(receive='opaque-room')]})
        assert c.app.state.onecomme.selected=='opaque-room'
        assert len(c.app.state.services.build_view_state()['current'])==1


def test_different_source_history_stop_disconnect_and_ambiguity_stay_protected(tmp_path):
    with TestClient(create_app(db_path=str(tmp_path/'db'),desktop=True,onecomme=True),base_url='http://127.0.0.1') as c:
        c.headers['Authorization']='Bearer '+c.app.state.access_keys.ingest
        b=c.app.state.onecomme
        a,other=row(),row('other-row')
        c.post('/api/onecomme/heartbeat',json={'services':[a,other]})
        assert not b.snapshot()['ready_to_receive']
        c.post('/api/onecomme/heartbeat',json={'services':[row(receive='room-a'),other]})
        assert b.selected=='room-a' and b.pinned_service=='restricted-row'
        old=event(frame='room-a',at=(datetime.now(timezone.utc)-timedelta(minutes=1)).isoformat())
        old['service_id']='restricted-row'
        assert c.post('/api/onecomme/comment',json=old).json()['status']=='history'
        foreign={**event(frame='room-a'),'service_id':'other-row'}
        assert c.post('/api/onecomme/comment',json=foreign).json()['status']=='unselected'
        # Two OneComme rows showing the same room still have distinct sources.
        c.post('/api/onecomme/heartbeat',json={'services':[row(receive='room-a'),row('other-row',receive='room-a')]})
        assert c.post('/api/onecomme/comment',json=foreign).json()['status']=='unselected'
        unknown={**event(frame='room-a'),'service_id':'missing-row'}
        assert c.post('/api/onecomme/comment',json=unknown).json()['status']=='unselected'
        c.post('/api/onecomme/heartbeat',json={'services':[row(receive='room-a'),row('other-row',receive='room-b')]})
        assert b.selected=='room-a'
        c.headers['Authorization']='Bearer '+c.app.state.access_keys.admin
        c.post('/api/onecomme/select',json={'frame_id':''})
        assert not b.snapshot()['ready_to_receive']
        c.headers['Authorization']='Bearer '+c.app.state.access_keys.ingest
        c.post('/api/onecomme/heartbeat',json={'services':[row(receive='room-a')]})
        assert not b.selected
        c.post('/api/onecomme/heartbeat',json={'services':[]})
        assert not b.snapshot()['ready_to_receive']


def test_receiving_frame_change_requires_existing_queue_transition_and_never_resets_data(tmp_path):
    with TestClient(create_app(db_path=str(tmp_path/'db'),desktop=True,onecomme=True),base_url='http://127.0.0.1') as c:
        c.headers['Authorization']='Bearer '+c.app.state.access_keys.ingest
        c.post('/api/onecomme/heartbeat',json={'services':[row(receive='room-a')]})
        assert c.post('/api/onecomme/comment',json={**event(frame='room-a'),'service_id':'restricted-row'}).json()['status']=='accepted'
        c.post('/api/onecomme/heartbeat',json={'services':[row(receive='room-b')]})
        b=c.app.state.onecomme
        assert b.pending['video_id']=='room-b' and not b.snapshot()['ready_to_receive']
        assert len(b.services.build_view_state()['current'])==1
        assert c.post('/api/onecomme/comment',json={**event(2,frame='room-b'),'service_id':'restricted-row'}).json()['status']=='unselected'


def test_receive_identity_validation_and_manual_unresolved_row_selection(tmp_path):
    with TestClient(create_app(db_path=str(tmp_path/'db'),desktop=True,onecomme=True),base_url='http://127.0.0.1') as c:
        c.headers['Authorization']='Bearer '+c.app.state.access_keys.ingest
        for invalid in (' ', 'room\n', 'room\u200b', 'x'*201):
            assert c.post('/api/onecomme/heartbeat',json={'services':[row(receive=invalid)]}).status_code==422
        c.post('/api/onecomme/heartbeat',json={'services':[row(),row('other-row')]})
        c.headers['Authorization']='Bearer '+c.app.state.access_keys.admin
        assert c.post('/api/onecomme/remember',json={'service_id':'restricted-row'}).status_code==200
        assert c.app.state.onecomme.snapshot()['ready_to_receive']
        c.headers['Authorization']='Bearer '+c.app.state.access_keys.ingest
        c.post('/api/onecomme/heartbeat',json={'services':[row(enabled=False)]})
        assert not c.app.state.onecomme.snapshot()['ready_to_receive']


def test_actual_comment_source_wins_over_provisional_metadata_but_manual_source_is_protected(tmp_path):
    with TestClient(create_app(db_path=str(tmp_path/'db'),desktop=True,onecomme=True),base_url='http://127.0.0.1') as c:
        c.headers['Authorization']='Bearer '+c.app.state.access_keys.ingest
        metadata=row('metadata-row',video='abcdefghijk')
        c.post('/api/onecomme/heartbeat',json={'services':[metadata]})
        assert c.app.state.onecomme.pinned_service=='metadata-row'
        actual=row('actual-row',receive='real-room')
        c.post('/api/onecomme/heartbeat',json={'services':[metadata,actual]})
        b=c.app.state.onecomme
        assert b.pinned_service=='actual-row' and b.selected=='real-room'
        assert c.post('/api/onecomme/comment',json={**event(frame='real-room'),'service_id':'actual-row'}).json()['status']=='accepted'
        c.headers['Authorization']='Bearer '+c.app.state.access_keys.admin
        c.post('/api/onecomme/remember',json={'service_id':'actual-row'})
        c.headers['Authorization']='Bearer '+c.app.state.access_keys.ingest
        c.post('/api/onecomme/heartbeat',json={'services':[row('different-row',receive='different-room')]})
        assert b.pinned_service=='actual-row' and not b.selected


def test_missing_automatic_row_follows_actual_receipt_without_resetting_saved_queue(tmp_path):
    with TestClient(create_app(db_path=str(tmp_path/'db'),desktop=True,onecomme=True),base_url='http://127.0.0.1') as c:
        c.headers['Authorization']='Bearer '+c.app.state.access_keys.ingest
        c.post('/api/onecomme/heartbeat',json={'services':[row(receive='old-room')]})
        c.post('/api/onecomme/comment',json={**event(frame='old-room'),'service_id':'restricted-row'})
        c.post('/api/onecomme/heartbeat',json={'services':[row('replacement-row',receive='new-room')]})
        b=c.app.state.onecomme
        assert b.pinned_service=='replacement-row' and b.pending['video_id']=='new-room'
        assert len(b.services.build_view_state()['current'])==1
