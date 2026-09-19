import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.services.application_services import ApplicationServices

@pytest.fixture
def client(tmp_path):
 with TestClient(create_app(db_path=str(tmp_path/'state.db'),desktop=True),base_url='http://127.0.0.1') as c:
  c.headers['Authorization']='Bearer '+c.app.state.access_keys.admin
  yield c

def join(c, message_id='1', nickname='あおい'):
 return c.post('/api/comments/receive',json={'source':'youtube','externalMessageId':message_id,'receivedAt':'2026-09-19T00:00:00Z','displayName':nickname,'youtubeHandle':'@aoi','youtubeNickname':nickname,'userKey':'channel-stable-id','message':'参加希望'})

@pytest.mark.parametrize('mode,expected',[('youtube','@aoi'),('declared','あおい'),('youtube_declared','@aoi（あおい）'),('declared_youtube','あおい（@aoi）')])
def test_four_names_and_placeholder(client,mode,expected):
 assert join(client).status_code==200
 config=client.get('/api/settings/overlay').json(); config['name_mode']=mode
 assert client.post('/api/settings/overlay',json=config).status_code==200
 public=client.get('/api/overlay-state').json()
 assert public['now_view'][0]=={'display_name':expected}
 assert public['now_view'][1]=={'display_name':'参加者募集中','is_placeholder':True}
 assert 'channel-stable-id' not in str(public)

def test_layout_and_names_survive_restart_and_backup(client,tmp_path):
 join(client)
 config=client.get('/api/settings/overlay').json(); config.update(layout='horizontal',width=1200,height=240,name_mode='declared_youtube')
 client.post('/api/settings/overlay',json=config)
 backup=client.get('/api/control/backup').json()
 assert backup['state']['current'][0]['youtube_handle']=='@aoi'
 assert backup['state']['current'][0]['youtube_nickname']=='あおい'
 restarted=ApplicationServices(db_path=str(tmp_path/'state.db'),desktop=True)
 assert restarted.build_overlay_state()['appearance']==config
 assert restarted.build_overlay_state()['now_view'][0]['display_name']=='あおい（@aoi）'

def test_streamer_edit_survives_comments_departure_restart_and_restore(client,tmp_path):
 join(client); uid=client.get('/api/state').json()['current'][0]['user_id']
 assert client.post('/api/control/update-declared-player-name',json={'user_id':uid,'declared_player_name':'配信用名'}).status_code==200
 client.post('/api/control/remove-user',json={'user_id':uid})
 client.app.state.services.persistence_service.mutate_state(lambda s:s.update(user_action_locks={}))
 assert join(client,'2','新しいニックネーム').status_code==200
 user=(client.get('/api/state').json()['current']+client.get('/api/state').json()['waiting'])[0]
 assert user['declared_player_name']=='配信用名'
 assert user['youtube_nickname']=='新しいニックネーム'
 restarted=ApplicationServices(db_path=str(tmp_path/'state.db'),desktop=True)
 assert restarted.persistence_service.get_state()['name_overrides'][uid]=='配信用名'
 backup=client.get('/api/control/backup').json()
 assert client.post('/api/control/restore',json={'backup':backup,'expected_revision':client.get('/api/state').json()['revision']}).status_code==200
 client.post('/api/control/update-declared-player-name',json={'user_id':uid,'declared_player_name':''})
 assert uid not in client.get('/api/state').json()['name_overrides']
 config=client.get('/api/settings/overlay').json(); config['name_mode']='declared'; client.post('/api/settings/overlay',json=config)
 public=client.get('/api/overlay-state').json()
 assert any(u['display_name']=='新しいニックネーム' for u in public['now_view']+public['next_view'])

@pytest.mark.parametrize('field,value',[('layout','diagonal'),('name_mode','all'),('name_mode',True)])
def test_invalid_choice_does_not_save(client,field,value):
 config=client.get('/api/settings/overlay').json(); changed={**config,field:value}
 assert client.post('/api/settings/overlay',json=changed).status_code==422
 assert client.get('/api/settings/overlay').json()==config

def test_missing_handle_uses_available_name_and_no_duplicate(client):
 client.post('/api/control/add-user',json={'display_name':'同じ名前','user_id':'manual'})
 client.post('/api/control/update-declared-player-name',json={'user_id':'manual','declared_player_name':'同じ名前'})
 config=client.get('/api/settings/overlay').json(); config['name_mode']='youtube_declared'; client.post('/api/settings/overlay',json=config)
 assert client.get('/api/overlay-state').json()['now_view'][0]['display_name']=='同じ名前'


def test_quoted_join_name_keeps_case_and_persists(client, tmp_path):
 payload={'source':'youtube','externalMessageId':'quoted-1','receivedAt':'2026-09-19T00:00:00Z','displayName':'元の表示名','youtubeHandle':'@aoi','userKey':'quoted-user','message':'参加希望 『PlayerABC』'}
 result=client.post('/api/comments/receive',json=payload)
 assert result.status_code==200
 user=client.get('/api/state').json()['current'][0]
 assert user['declared_player_name']=='PlayerABC'
 assert user['youtube_handle']=='@aoi'
 config=client.get('/api/settings/overlay').json(); config['name_mode']='declared'
 client.post('/api/settings/overlay',json=config)
 assert client.get('/api/overlay-state').json()['now_view'][0]['display_name']=='PlayerABC'
 restarted=ApplicationServices(db_path=str(tmp_path/'state.db'),desktop=True)
 assert restarted.build_overlay_state()['now_view'][0]['display_name']=='PlayerABC'
 client.post('/api/control/update-declared-player-name',json={'user_id':user['user_id'],'declared_player_name':'配信者指定'})
 client.post('/api/control/remove-user',json={'user_id':user['user_id']})
 client.app.state.services.persistence_service.mutate_state(lambda s:s.update(user_action_locks={}))
 payload.update(externalMessageId='quoted-2',message='参加希望 『OtherName』')
 client.post('/api/comments/receive',json=payload)
 assert client.get('/api/state').json()['current'][0]['declared_player_name']=='配信者指定'
