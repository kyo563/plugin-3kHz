"""Manual URL selection remains an authenticated local OneComme binding."""
from datetime import datetime, timezone, timedelta
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.services.onecomme import OneCommeBridge
from tests.test_onecomme import event
from tests.test_onecomme_receiving import row


@pytest.mark.parametrize('url', [
    'https://www.youtube.com/watch?v=abcdefghijk&si=discard-this',
    'https://youtube.com/watch?v=abcdefghijk#fragment',
    'https://m.youtube.com/watch?v=abcdefghijk',
    'https://youtu.be/abcdefghijk?si=discard-this',
    'https://www.youtube.com/live/abcdefghijk?feature=share',
    'https://www.youtube.com/embed/abcdefghijk/',
])
def test_url_normalization_is_local_and_retains_only_video_id(url):
    assert OneCommeBridge.video_url(url) == ('abcdefghijk','https://www.youtube.com/watch?v=abcdefghijk')


@pytest.mark.parametrize('url', [
    'http://www.youtube.com/watch?v=abcdefghijk', 'https://youtube.com.evil.test/watch?v=abcdefghijk',
    'https://evil.test/watch?v=abcdefghijk', 'https://user:pass@youtube.com/watch?v=abcdefghijk',
    'https://youtube.com:443/watch?v=abcdefghijk', 'file:///etc/passwd',
    'https://youtube.com/@channel/live', 'abcdefghijk', 'https://youtu.be/short',
    'https://youtube.com/watch?v=abcdefghijk&v=lmnopqrstuv',
    'https://youtube.com/watch?v=abcdef\nghijk', 'https://youtube.com/watch?v=abcdef\u200bghijk',
])
def test_url_parser_rejects_foreign_sites_and_ambiguous_or_nonvideo_urls(url):
    with pytest.raises(ValueError):
        OneCommeBridge.video_url(url)


def test_url_waits_for_matching_onecomme_source_and_preserves_history_and_auth(tmp_path):
    db=str(tmp_path/'url.db')
    with TestClient(create_app(db_path=db,desktop=True,onecomme=True),base_url='http://127.0.0.1') as c:
        url={'url':'https://youtu.be/abcdefghijk?si=discard-this'}
        assert c.post('/api/onecomme/select-url',json=url).status_code==401
        c.headers['Authorization']='Bearer '+c.app.state.access_keys.ingest
        assert c.post('/api/onecomme/select-url',json=url).status_code==401
        c.headers['Authorization']='Bearer '+c.app.state.access_keys.admin
        result=c.post('/api/onecomme/select-url',json=url).json()
        assert result['manual_url']=='https://www.youtube.com/watch?v=abcdefghijk'
        assert not result['selected'] and not result['ready_to_receive']
        assert c.post('/api/onecomme/select-url',json={'url':'https://evil.test'}).status_code==422
        assert c.app.state.onecomme.snapshot()['manual_url']==result['manual_url']
        c.headers['Authorization']='Bearer '+c.app.state.access_keys.ingest
        c.post('/api/onecomme/heartbeat',json={'services':[row(video='lmnopqrstuv')]})
        assert not c.app.state.onecomme.snapshot()['ready_to_receive']
        c.post('/api/onecomme/heartbeat',json={'services':[row(video='abcdefghijk')]})
        assert c.app.state.onecomme.selected=='abcdefghijk'
        old={**event(frame='abcdefghijk',at=(datetime.now(timezone.utc)-timedelta(minutes=1)).isoformat()),'service_id':'restricted-row'}
        assert c.post('/api/onecomme/comment',json=old).json()['status']=='history'
        assert c.post('/api/onecomme/comment',json={**event(frame='abcdefghijk'),'service_id':'restricted-row'}).json()['status']=='accepted'
        before=c.app.state.onecomme.since
        c.post('/api/onecomme/heartbeat',json={'services':[row(video='abcdefghijk')]})
        assert c.app.state.onecomme.since==before
        c.post('/api/onecomme/heartbeat',json={'services':[row(video='lmnopqrstuv')]})
        assert c.app.state.onecomme.snapshot()['selection_reason']=='url_mismatch'
        assert not c.app.state.onecomme.snapshot()['ready_to_receive']
        assert len(c.app.state.services.build_view_state()['current'])==1
    with TestClient(create_app(db_path=db,desktop=True,onecomme=True),base_url='http://127.0.0.1') as c:
        c.headers['Authorization']='Bearer '+c.app.state.access_keys.ingest
        c.post('/api/onecomme/heartbeat',json={'services':[row(video='abcdefghijk')]})
        b=c.app.state.onecomme
        assert b.snapshot()['manual_url']=='https://www.youtube.com/watch?v=abcdefghijk'
        assert b.selected=='abcdefghijk' and len(b.services.build_view_state()['current'])==1


def test_explicit_unresolved_source_binding_accepts_receipt_but_never_guesses_or_changes_rooms(tmp_path):
    with TestClient(create_app(db_path=str(tmp_path/'db'),desktop=True,onecomme=True),base_url='http://127.0.0.1') as c:
        c.headers['Authorization']='Bearer '+c.app.state.access_keys.ingest
        c.post('/api/onecomme/heartbeat',json={'services':[row(),row('other-row')]})
        c.headers['Authorization']='Bearer '+c.app.state.access_keys.admin
        url={'url':'https://youtube.com/live/abcdefghijk'}
        assert not c.post('/api/onecomme/select-url',json=url).json()['ready_to_receive']
        assert c.post('/api/onecomme/select-url',json={**url,'service_id':'missing'}).status_code==422
        assert c.post('/api/onecomme/select-url',json={**url,'service_id':'restricted-row'}).json()['ready_to_receive']
        c.headers['Authorization']='Bearer '+c.app.state.access_keys.ingest
        first={**event(frame='opaque-room'),'service_id':'restricted-row'}
        c.post('/api/onecomme/heartbeat',json={'services':[row(receive='opaque-room'),row('other-row',receive='opaque-room')]})
        assert c.post('/api/onecomme/comment',json=first).json()['status']=='accepted'
        assert c.post('/api/onecomme/comment',json={**first,'service_id':'other-row'}).json()['status']=='unselected'
        c.post('/api/onecomme/heartbeat',json={'services':[row(receive='room-changed')]})
        assert not c.app.state.onecomme.selected
        assert c.app.state.onecomme.snapshot()['selection_reason']=='url_mismatch'
        c.headers['Authorization']='Bearer '+c.app.state.access_keys.admin
        c.post('/api/onecomme/select',json={'frame_id':''})
        assert not c.app.state.onecomme.snapshot()['manual_url']
        c.headers['Authorization']='Bearer '+c.app.state.access_keys.ingest
        c.post('/api/onecomme/heartbeat',json={'services':[row(receive='opaque-room')]})
        assert not c.app.state.onecomme.selected


def test_url_binding_checks_resolved_conflicts_and_existing_queue_transition(tmp_path):
    with TestClient(create_app(db_path=str(tmp_path/'db'),desktop=True,onecomme=True),base_url='http://127.0.0.1') as c:
        c.headers['Authorization']='Bearer '+c.app.state.access_keys.ingest
        c.post('/api/onecomme/heartbeat',json={'services':[row(video='lmnopqrstuv')]})
        c.post('/api/onecomme/comment',json={**event(frame='lmnopqrstuv'),'service_id':'restricted-row'})
        c.headers['Authorization']='Bearer '+c.app.state.access_keys.admin
        url={'url':'https://youtu.be/abcdefghijk','service_id':'restricted-row'}
        assert c.post('/api/onecomme/select-url',json=url).status_code==422
        assert not c.app.state.onecomme.snapshot()['manual_url']
        c.headers['Authorization']='Bearer '+c.app.state.access_keys.ingest
        c.post('/api/onecomme/heartbeat',json={'services':[row(),row('new-row',video='abcdefghijk')]})
        c.headers['Authorization']='Bearer '+c.app.state.access_keys.admin
        state=c.post('/api/onecomme/select-url',json={'url':url['url']}).json()
        assert state['pending']['video_id']=='abcdefghijk' and not state['ready_to_receive']
        assert len(c.app.state.services.build_view_state()['current'])==1
        assert c.post('/api/onecomme/transition',json={'video_id':'abcdefghijk','carry':False,'revision':state['pending']['revision']}).status_code==200
        assert c.app.state.onecomme.selected=='abcdefghijk'
        assert len(c.app.state.services.build_view_state()['current'])==0


def test_url_with_duplicate_resolved_sources_requires_explicit_choice_and_stops_on_removal(tmp_path):
    with TestClient(create_app(db_path=str(tmp_path/'db'),desktop=True,onecomme=True),base_url='http://127.0.0.1') as c:
        c.headers['Authorization']='Bearer '+c.app.state.access_keys.ingest
        rows=[row(video='abcdefghijk'),row('other-row',video='abcdefghijk')]
        c.post('/api/onecomme/heartbeat',json={'services':rows})
        c.headers['Authorization']='Bearer '+c.app.state.access_keys.admin
        url={'url':'https://youtu.be/abcdefghijk'}
        assert not c.post('/api/onecomme/select-url',json=url).json()['ready_to_receive']
        assert c.post('/api/onecomme/select-url',json={**url,'service_id':'other-row'}).json()['ready_to_receive']
        c.headers['Authorization']='Bearer '+c.app.state.access_keys.ingest
        assert c.post('/api/onecomme/comment',json={**event(frame='abcdefghijk'),'service_id':'restricted-row'}).json()['status']=='unselected'
        c.post('/api/onecomme/heartbeat',json={'services':[rows[0]]})
        assert not c.app.state.onecomme.snapshot()['ready_to_receive']
        c.headers['Authorization']='Bearer '+c.app.state.access_keys.admin
        c.post('/api/onecomme/remember',json={'service_id':'restricted-row'})
        assert not c.app.state.onecomme.snapshot()['manual_url']
        assert c.app.state.onecomme.snapshot()['selection_mode']=='auto'
