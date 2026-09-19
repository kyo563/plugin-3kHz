import pytest
from fastapi.testclient import TestClient
from app.main import create_app

@pytest.mark.parametrize('reception_open',[True,False])
def test_admin_remove_refills_next_and_queue_and_undo(tmp_path,reception_open):
 with TestClient(create_app(db_path=str(tmp_path/'db'),desktop=True),base_url='http://127.0.0.1') as c:
  c.headers['Authorization']='Bearer '+c.app.state.access_keys.admin
  for i in range(8):c.post('/api/control/add-user',json={'user_id':str(i),'display_name':str(i)})
  if not reception_open:c.post('/api/control/toggle-open')
  before=c.get('/api/state').json()
  c.post('/api/control/remove-user',json={'user_id':'1'})
  after=c.get('/api/state').json()
  assert [u['user_id'] for u in after['current']]==['0','2','3']
  assert [u['user_id'] for u in after['waiting']]==['4','5','6','7']
  assert [u['user_id'] for u in after['next_view']]==['4','5','6']
  assert after['participation_counts']==before['participation_counts']
  assert after['total_match_count']==0
  assert c.get('/api/control/history').json()['sessions']==[]
  c.post('/api/control/undo')
  restored=c.get('/api/state').json()
  for section in ('current', 'waiting'):
   without_updated = lambda users: [{k: v for k, v in user.items() if k != 'updated_at'} for user in users]
   assert without_updated(restored[section]) == without_updated(before[section])


def test_waiting_comment_cancel_promotes_queue_into_next(tmp_path):
 with TestClient(create_app(db_path=str(tmp_path/'db'),desktop=True),base_url='http://127.0.0.1') as c:
  c.headers['Authorization']='Bearer '+c.app.state.access_keys.admin
  c.post('/api/settings/comments',json={'cooldown_seconds':0})
  for i in range(3):c.post('/api/control/add-user',json={'user_id':str(i),'display_name':str(i)})
  msg=dict(source='youtube',userKey='leaver',displayName='Leaver',receivedAt='2026-09-20T00:00:00Z',externalMessageId='join',message='参加希望')
  c.post('/api/comments/receive',json=msg)
  for i in range(3,7):c.post('/api/control/add-user',json={'user_id':str(i),'display_name':str(i)})
  c.post('/api/comments/receive',json={**msg,'externalMessageId':'cancel','message':'参加辞退'})
  state=c.get('/api/state').json()
  assert [u['user_id'] for u in state['next_view']]==['3','4','5']
  assert [u['user_id'] for u in state['queue_view']]==['6']
  assert [u['user_id'] for u in state['current']]==['0','1','2']
