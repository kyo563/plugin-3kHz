from fastapi.testclient import TestClient
from app.main import create_app
from app.services.application_services import ApplicationServices


def test_separate_stream_counts_keep_lifetime_identity_restart_and_undo(tmp_path):
    path=str(tmp_path/'counts.db')
    with TestClient(create_app(db_path=path,desktop=True),base_url='http://127.0.0.1') as c:
        c.headers['Authorization']='Bearer '+c.app.state.access_keys.admin
        def add():
            c.post('/api/control/add-user',json={'user_id':'same-user','display_name':'Account'})
        add()
        c.post('/api/control/correct-count',json={'user_id':'same-user','participation_count':5})
        c.post('/api/control/move-next')
        history=c.get('/api/control/history').json()
        assert history['sessions'][0]['users'][0]['count']==1
        assert history['cumulative_counts']['same-user']==6
        c.post('/api/control/history/start',json={'label':'second'})
        add()
        c.post('/api/control/update-declared-player-name',json={'user_id':'same-user','declared_player_name':'Alias'})
        view=c.get('/api/state').json()
        assert view['session_participation_counts'].get('same-user',0)==0
        assert view['current'][0]['participation_count']==6
        c.post('/api/control/move-next')
        view=c.get('/api/state').json()
        assert view['session_participation_counts']['same-user']==1
        assert view['participation_counts']['same-user']==7
        history=c.get('/api/control/history').json()
        assert [s['users'][0]['count'] for s in history['sessions']]==[1,1]
        assert history['cumulative_counts']['same-user']==7
        restarted=ApplicationServices(db_path=path,desktop=True).build_view_state()
        assert restarted['session_participation_counts']['same-user']==1
        assert restarted['participation_counts']['same-user']==7
        c.post('/api/control/undo')
        view=c.get('/api/state').json()
        assert view['session_participation_counts']=={}
        assert view['participation_counts']['same-user']==6
        c.post('/api/control/remove-user',json={'user_id':'same-user'})
        assert c.get('/api/state').json()['participation_counts']['same-user']==6
        backup=c.get('/api/control/backup').json()['state']
        assert backup['participation_counts']['same-user']==6
        assert len(backup['participation_history'])==2
