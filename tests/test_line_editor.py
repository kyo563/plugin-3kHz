from fastapi.testclient import TestClient
from app.main import create_app
from app.services.application_services import ApplicationServices

def test_line_editor_persists_exact_text_through_restart_and_restore(tmp_path):
 path=str(tmp_path/'state.db')
 with TestClient(create_app(db_path=path,desktop=True),base_url='http://127.0.0.1') as c:
  c.headers['Authorization']='Bearer '+c.app.state.access_keys.admin
  before=c.get('/api/settings/overlay').json()
  content='[受付]\n\n配信の参加者\n[NOW1]\n[NOW2]\n\n\n[NEXT1]  [NEXT2]\n[待機人数]\n'
  changed={**before,'layout':'custom','custom_text':content}
  assert c.post('/api/settings/overlay',json=changed).status_code==200
  restarted=ApplicationServices(db_path=path,desktop=True)
  assert restarted.build_overlay_state()['appearance']['custom_text']==content
  backup=c.get('/api/control/backup').json()
  assert c.post('/api/settings/overlay',json=before).status_code==200
  revision=c.get('/api/state').json()['revision']
  assert c.post('/api/control/restore',json={'backup':backup,'expected_revision':revision}).status_code==200
  assert c.get('/api/settings/overlay').json()==changed
  c.post('/api/control/add-user',json={'user_id':'test','display_name':'新しい参加者'})
  public=c.get('/api/overlay-state').json()
  assert public['appearance']['custom_text']==content
  assert public['now_view'][0]['display_name']=='新しい参加者'
  invalid={**changed,'custom_text':'a'*4001}
  assert c.post('/api/settings/overlay',json=invalid).status_code==422
  assert c.get('/api/settings/overlay').json()==changed

def test_old_settings_keep_vertical_default():
 from app.schemas.overlay_settings import OverlaySettings
 old=OverlaySettings.model_validate({'width':480,'height':600})
 assert old.layout=='vertical' and '[NOW1]' in old.custom_text
