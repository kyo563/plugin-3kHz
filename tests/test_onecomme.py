from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from app.main import create_app
from app.services.user_identity_service import UserIdentityService


def event(n=0, text="参加希望", frame="live", at=None):
    return {"frame_id": frame, "frame_name": "配信", "comment": {
        "source": "youtube", "userKey": "UC" + str(n).zfill(22), "displayName": "User" + str(n),
        "externalMessageId": str(n) + text, "receivedAt": at or datetime.now(timezone.utc).isoformat(),
        "message": text}}


def test_variant_isolation_auth_and_pages(tmp_path):
    for variant in (True, False):
        with TestClient(create_app(db_path=str(tmp_path / str(variant)), desktop=True, onecomme=variant), base_url="http://127.0.0.1") as c:
            assert c.get('/api/onecomme/status').status_code == 401
            c.headers['Authorization'] = 'Bearer ' + c.app.state.access_keys.ingest
            assert c.post('/api/onecomme/select', json={'frame_id': ''}).status_code == 401
            c.headers['Authorization'] = 'Bearer ' + c.app.state.access_keys.admin
            assert c.get('/api/onecomme/status').status_code == (200 if variant else 404)
            assert c.get('/api/youtube/status').status_code == (404 if variant else 200)
            assert ('id="youtube-key"' in c.get('/control').text) != variant
            assert ('id="onecomme-stream"' in c.get('/control').text) == variant


def test_selection_history_identity_now_protection_refill_and_persistence(tmp_path):
    app = create_app(db_path=str(tmp_path / 'new.db'), desktop=True, onecomme=True)
    with TestClient(app, base_url='http://127.0.0.1') as c:
        admin = {'Authorization': 'Bearer ' + app.state.access_keys.admin}
        ingest = {'Authorization': 'Bearer ' + app.state.access_keys.ingest}
        def post(e): return c.post('/api/onecomme/comment', json=e, headers=ingest)
        c.headers.update(admin)
        app.state.services.persistence_service.mutate_state(lambda s: s.update(cooldown_seconds=0))
        assert post(event()).json()['status'] == 'unselected'
        assert c.get('/api/state').json()['current'] == []
        assert c.post('/api/onecomme/select', json={'frame_id': 'missing'}).status_code == 422
        assert c.post('/api/onecomme/select', json={'frame_id': 'live'}).status_code == 200
        old = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        assert post(event(at=old)).json()['status'] == 'history'
        boundary = (app.state.onecomme.since - timedelta(milliseconds=16)).isoformat()
        assert post(event(9, text='通常コメント', at=boundary)).json()['status'] == 'ignored'
        before = (app.state.onecomme.since - timedelta(milliseconds=21)).isoformat()
        assert post(event(9, at=before)).json()['status'] == 'history'
        assert post(event(frame='other')).json()['status'] == 'unselected'
        e = event(0, '参加希望 『A&amp;B』')
        assert post(e).status_code == 200
        assert post(e).json()['duplicate']
        for n in (1, 2, 3): assert post(event(n)).status_code == 200
        state = c.get('/api/state').json()
        uid = UserIdentityService().build_comment_user_id('youtube', 'UC' + '0' * 22)
        assert state['current'][0]['user_id'] == uid
        assert state['current'][0]['declared_player_name'] == 'A&B'
        post(event(0, '参加辞退'))
        assert len(c.get('/api/state').json()['current']) == 3
        c.post('/api/control/remove-user', json={'user_id': uid})
        state = c.get('/api/state').json()
        assert len(state['current']) == 3 and state['waiting'] == []
        c.post('/api/control/move-next')
        assert len(c.get('/api/control/history').json()['sessions'][0]['users']) == 3

        assert c.post('/api/onecomme/heartbeat', json={'dropped': 2}, headers=ingest).status_code == 200
        assert c.get('/api/onecomme/status').json()['connected']
        assert c.get('/api/onecomme/status').json()['dropped'] == 2
        bad = event(); bad['comment']['userKey'] = '@same-name'
        assert post(bad).status_code == 422
        assert c.post('/api/onecomme/select', json={'frame_id': ''}).status_code == 200
        assert post(event(5)).json()['status'] == 'unselected'
    with TestClient(create_app(db_path=str(tmp_path / 'new.db'), desktop=True, onecomme=True), base_url='http://127.0.0.1') as c:
        c.headers['Authorization'] = 'Bearer ' + c.app.state.access_keys.admin
        assert c.get('/api/onecomme/status').json()['selected'] == ''
        assert len(c.get('/api/control/history').json()['sessions'][0]['users']) == 3


def test_explicit_backup_migration_keeps_counts_without_writing_old_database(tmp_path):
    old = tmp_path / 'standalone.db'
    uid = UserIdentityService().build_comment_user_id('youtube', 'UC' + '0' * 22)
    with TestClient(create_app(db_path=str(old), desktop=True), base_url='http://127.0.0.1') as c:
        c.headers['Authorization'] = 'Bearer ' + c.app.state.access_keys.admin
        c.post('/api/control/add-user', json={'user_id': uid, 'display_name': 'Account'})
        c.post('/api/control/correct-count', json={'user_id': uid, 'participation_count': 10})
        c.post('/api/control/move-next')
        backup = c.get('/api/control/backup').json()
    before = old.read_bytes()
    with TestClient(create_app(db_path=str(tmp_path / 'onecomme.db'), desktop=True, onecomme=True), base_url='http://127.0.0.1') as c:
        c.headers['Authorization'] = 'Bearer ' + c.app.state.access_keys.admin
        revision = c.get('/api/state').json()['revision']
        assert c.post('/api/control/restore', json={'backup': backup, 'expected_revision': revision}).status_code == 200
        c.post('/api/onecomme/comment', json=event())
        c.post('/api/onecomme/select', json={'frame_id': 'live'})
        c.post('/api/onecomme/comment', json=event())
        state = c.get('/api/state').json()
        assert state['current'][0]['user_id'] == uid
        assert state['current'][0]['participation_count'] == 11
        assert c.get('/api/control/history').json()['cumulative_counts'][uid] == 11
    assert old.read_bytes() == before
