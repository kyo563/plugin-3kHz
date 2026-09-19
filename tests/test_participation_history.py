from fastapi.testclient import TestClient
from app.main import create_app
from app.services.application_services import ApplicationServices


def test_history_unique_order_sessions_undo_backup_restart(tmp_path):
 path=str(tmp_path/'app.db')
 with TestClient(create_app(db_path=path,desktop=True),base_url='http://127.0.0.1') as c:
  c.headers['Authorization']='Bearer '+c.app.state.access_keys.admin
  def add(uid,name):
   assert c.post('/api/control/add-user',json={'user_id':uid,'display_name':name}).status_code==200
  def history():return c.get('/api/control/history').json()['sessions']
  assert history()==[]
  add('a','Alice');add('b','Bob')
  assert history()==[]
  c.post('/api/control/move-next')
  first=history()[0]
  assert [u['user_id'] for u in first['users']]==['a','b']
  assert first['matches']==1
  add('b','Bob renamed');add('c','Carol')
  c.post('/api/control/move-next')
  rows=history()[0]['users']
  assert [u['user_id'] for u in rows]==['a','b','c']
  assert [u['count'] for u in rows]==[1,2,1]
  assert rows[1]['display_name']=='Bob renamed'
  assert c.post('/api/control/undo').status_code==200
  assert history()[0]==first
  c.post('/api/control/move-next')
  before=c.get('/api/state').json()
  assert 'participation_history' not in before
  assert 'participation_history' not in c.get('/api/overlay-state').json()
  assert c.post('/api/control/history/start',json={'label':'Second'}).status_code==200
  after=c.get('/api/state').json()
  assert before['participation_counts']==after['participation_counts']
  assert history()[-1]['users']==[]
  add('a','Alice');c.post('/api/control/move-next')
  assert history()[-1]['users'][0]['count']==1
  assert c.app.state.services.persistence_service.get_state()['participation_counts']['a']==2
  expected=history()
  restarted=ApplicationServices(db_path=path,desktop=True)
  assert restarted.persistence_service.get_state()['participation_history']==expected
  backup=c.get('/api/control/backup').json()
  assert backup['state']['participation_history']==expected
  c.post('/api/control/reset')
  assert history()==[]
  revision=c.get('/api/state').json()['revision']
  assert c.post('/api/control/restore',json={'backup':backup,'expected_revision':revision}).status_code==200
  assert history()==expected
  del backup['state']['participation_history']
  revision=c.get('/api/state').json()['revision']
  assert c.post('/api/control/restore',json={'backup':backup,'expected_revision':revision}).status_code==200
  assert history()==[]
  c.headers['Authorization']='Bearer '+c.app.state.access_keys.ingest
  assert c.get('/api/control/history').status_code==401
  assert c.post('/api/control/history/start',json={}).status_code==401


def test_empty_now_and_cancelled_participant_not_recorded(tmp_path):
 s=ApplicationServices(db_path=str(tmp_path/'db'),desktop=True)
 s.move_next()
 assert s.persistence_service.get_state()['participation_history']==[]
 from app.services.operator_service import add_participant
 add_participant(s,'A','a')
 s.persistence_service.manual_mutate(lambda st:s.queue_service.remove_user_by_id(st,'a'))
 s.move_next()
 assert s.persistence_service.get_state()['participation_history']==[]
