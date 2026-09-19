import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.services.application_services import ApplicationServices

@pytest.fixture
def client(tmp_path):
 with TestClient(create_app(db_path=str(tmp_path/'state.db'),desktop=True),base_url='http://127.0.0.1') as c:
  c.headers['Authorization']='Bearer '+c.app.state.access_keys.admin
  yield c

def total(c): return c.get('/api/state').json()['total_match_count']

def test_counts_rounds_not_people_and_empty_rounds_do_not_count(client,tmp_path):
 assert total(client)==0
 assert client.post('/api/control/move-next').status_code==200
 assert total(client)==0
 for i in range(4): client.post('/api/control/add-user',json={'display_name':f'User{i}','user_id':f'u{i}'})
 assert client.post('/api/control/move-next').status_code==200
 assert total(client)==1
 assert 'total_match_count' not in client.get('/api/overlay-state').json()
 restarted=ApplicationServices(db_path=str(tmp_path/'state.db'),desktop=True)
 assert restarted.build_view_state()['total_match_count']==1
 client.post('/api/control/move-next'); assert total(client)==2
 client.post('/api/control/move-next'); assert total(client)==2

def test_undo_backup_restore_and_reset(client):
 client.post('/api/control/add-user',json={'display_name':'User','user_id':'u'})
 client.post('/api/control/move-next'); assert total(client)==1
 client.post('/api/control/undo'); assert total(client)==0
 client.post('/api/control/move-next'); backup=client.get('/api/control/backup').json()
 assert backup['state']['total_match_count']==1
 client.post('/api/control/reset'); assert total(client)==0
 revision=client.get('/api/state').json()['revision']
 assert client.post('/api/control/restore',json={'backup':backup,'expected_revision':revision}).status_code==200
 assert total(client)==1
 backup['state'].pop('total_match_count')
 revision=client.get('/api/state').json()['revision']
 assert client.post('/api/control/restore',json={'backup':backup,'expected_revision':revision}).status_code==200
 assert total(client)==0

def test_failed_advance_does_not_increment(client):
 client.post('/api/control/add-user',json={'display_name':'User','user_id':'u'})
 client.post('/api/control/correct-count',json={'user_id':'u','participation_count':2147483647})
 assert client.post('/api/control/move-next').status_code==409
 assert total(client)==0
 client.app.state.services.persistence_service.mutate_state(lambda s:s.update(total_match_count=2147483647))
 before=client.get('/api/state').json()
 assert client.post('/api/control/move-next').status_code==409
 assert client.get('/api/state').json()==before
