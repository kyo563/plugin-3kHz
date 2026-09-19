from fastapi.testclient import TestClient
from app.main import create_app
from app.services.application_services import ApplicationServices


def test_first_name_survives_rejoin_restart_backup_and_admin_edit(tmp_path):
 path=str(tmp_path/'db')
 with TestClient(create_app(db_path=path,desktop=True),base_url='http://127.0.0.1') as c:
  c.headers['Authorization']='Bearer '+c.app.state.access_keys.admin
  c.post('/api/settings/comments',json={'cooldown_seconds':0})
  for i in range(3):c.post('/api/control/add-user',json={'user_id':str(i),'display_name':str(i)})
  msg=dict(source='youtube',userKey='listener',displayName='YouTube名',youtubeNickname='YouTube名',receivedAt='2026-09-20T00:00:00Z',message='参加希望 『First』',externalMessageId='first')
  c.post('/api/comments/receive',json=msg)
  first=c.get('/api/state').json()['waiting'][0]
  c.post('/api/comments/receive',json={**msg,'externalMessageId':'second','message':'参加希望 『Second』'})
  assert c.get('/api/state').json()['waiting'][0]['declared_player_name']=='First'
  c.post('/api/comments/receive',json={**msg,'externalMessageId':'cancel','message':'参加辞退'})
  c.post('/api/comments/receive',json={**msg,'externalMessageId':'third','message':'参加希望 『Third』'})
  assert c.get('/api/state').json()['waiting'][0]['declared_player_name']=='First'
  restarted=ApplicationServices(db_path=path,desktop=True)
  assert restarted.persistence_service.get_state()['comment_names'][first['user_id']]=='First'
  backup=c.get('/api/control/backup').json()
  assert backup['state']['comment_names'][first['user_id']]=='First'
  revision=c.get('/api/state').json()['revision']
  assert c.post('/api/control/restore',json={'backup':backup,'expected_revision':revision}).status_code==200
  c.post('/api/control/update-declared-player-name',json={'user_id':first['user_id'],'declared_player_name':'Admin'})
  c.post('/api/comments/receive',json={**msg,'externalMessageId':'fourth','message':'参加希望 『Fourth』'})
  assert c.get('/api/state').json()['waiting'][0]['declared_player_name']=='Admin'
  c.post('/api/control/move-next')
  c.post('/api/control/move-next')
  c.post('/api/comments/receive',json={**msg,'externalMessageId':'fifth','message':'参加希望'})
  assert c.get('/api/state').json()['current'][0]['declared_player_name']=='Admin'


def test_closed_join_does_not_reserve_name_and_plain_join_can_later_specify(tmp_path):
 with TestClient(create_app(db_path=str(tmp_path/'db'),desktop=True),base_url='http://127.0.0.1') as c:
  c.headers['Authorization']='Bearer '+c.app.state.access_keys.admin
  c.post('/api/settings/comments',json={'cooldown_seconds':0})
  for i in range(3):c.post('/api/control/add-user',json={'user_id':str(i),'display_name':str(i)})
  msg=dict(source='youtube',userKey='a',displayName='YouTube名',receivedAt='2026-09-20T00:00:00Z',message='参加希望 『Rejected』',externalMessageId='one')
  c.post('/api/control/toggle-open')
  c.post('/api/comments/receive',json=msg)
  assert c.app.state.services.persistence_service.get_state()['comment_names']=={}
  c.post('/api/control/toggle-open')
  c.post('/api/comments/receive',json={**msg,'externalMessageId':'two','message':'参加希望'})
  c.post('/api/comments/receive',json={**msg,'externalMessageId':'three','message':'参加希望 『First』'})
  assert c.get('/api/state').json()['waiting'][0]['declared_player_name']=='First'
