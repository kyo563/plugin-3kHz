import pytest
from fastapi.testclient import TestClient
from app.main import create_app

@pytest.mark.parametrize('command',['参加辞退','参加を辞退','参加希望','参加希望 『変更名』'])
@pytest.mark.parametrize('seconds',[0,7,40])
def test_now_protected_but_admin_can_remove(tmp_path,command,seconds):
 with TestClient(create_app(db_path=str(tmp_path/'db'),desktop=True),base_url='http://127.0.0.1') as c:
  c.headers['Authorization']='Bearer '+c.app.state.access_keys.admin
  c.post('/api/settings/comments',json={'cooldown_seconds':seconds})
  msg=dict(source='youtube',userKey='channel-a',displayName='Alice',receivedAt='2026-09-20T00:00:00Z',externalMessageId='first',message='参加希望')
  c.post('/api/comments/receive',json=msg)
  before=c.get('/api/state').json()
  # Expire the cooldown independently: NOW protection must not depend on it.
  c.app.state.services.persistence_service.mutate_state(lambda s:s.update(user_action_locks={}))
  c.post('/api/comments/receive',json={**msg,'externalMessageId':'second','message':command})
  after=c.get('/api/state').json()
  for key in ['current','waiting','participation_counts','total_match_count']:
   assert before[key]==after[key]
  uid=after['current'][0]['user_id']
  assert c.post('/api/control/remove-user',json={'user_id':uid}).status_code==200
  assert c.get('/api/state').json()['current']==[]


def test_waiting_cancellation_and_next_match_still_work(tmp_path):
 with TestClient(create_app(db_path=str(tmp_path/'db'),desktop=True),base_url='http://127.0.0.1') as c:
  c.headers['Authorization']='Bearer '+c.app.state.access_keys.admin
  c.post('/api/settings/comments',json={'cooldown_seconds':0})
  for i in range(3):c.post('/api/control/add-user',json={'user_id':str(i),'display_name':str(i)})
  msg=dict(source='youtube',userKey='channel-a',displayName='Alice',receivedAt='2026-09-20T00:00:00Z',externalMessageId='first',message='参加希望')
  c.post('/api/comments/receive',json=msg)
  assert len(c.get('/api/state').json()['waiting'])==1
  c.post('/api/comments/receive',json={**msg,'externalMessageId':'cancel','message':'参加を辞退'})
  assert c.get('/api/state').json()['waiting']==[]
  c.post('/api/comments/receive',json={**msg,'externalMessageId':'rejoin'})
  c.post('/api/control/move-next')
  after=c.get('/api/state').json()
  assert after['current'][0]['display_name']=='Alice'
  assert after['total_match_count']==1
