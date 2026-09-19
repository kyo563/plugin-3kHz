from datetime import datetime, timedelta, timezone
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.services.application_services import ApplicationServices
from app.services.state_change_cooldown_service import StateChangeCooldownService

@pytest.mark.parametrize('seconds',[0,7,20,40,3600])
def test_settings_persist_and_backup(tmp_path,seconds):
 path=str(tmp_path/'db')
 with TestClient(create_app(db_path=path,desktop=True),base_url='http://127.0.0.1') as c:
  c.headers['Authorization']='Bearer '+c.app.state.access_keys.admin
  assert c.get('/api/settings/comments').json()=={'cooldown_seconds':40}
  assert c.post('/api/settings/comments',json={'cooldown_seconds':seconds}).status_code==200
  assert ApplicationServices(db_path=path,desktop=True).persistence_service.get_state()['cooldown_seconds']==seconds
  backup=c.get('/api/control/backup').json()
  assert backup['state']['cooldown_seconds']==seconds
  revision=c.get('/api/state').json()['revision']
  assert c.post('/api/control/restore',json={'backup':backup,'expected_revision':revision}).status_code==200
  assert c.get('/api/settings/comments').json()['cooldown_seconds']==seconds
  c.headers['Authorization']='Bearer '+c.app.state.access_keys.ingest
  assert c.post('/api/settings/comments',json={'cooldown_seconds':10}).status_code==401

@pytest.mark.parametrize('seconds',[-1,3601,7.5,'7',True,None])
def test_invalid_setting_preserves_state(tmp_path,seconds):
 with TestClient(create_app(db_path=str(tmp_path/'db'),desktop=True),base_url='http://127.0.0.1') as c:
  c.headers['Authorization']='Bearer '+c.app.state.access_keys.admin
  before=c.get('/api/state').json()
  assert c.post('/api/settings/comments',json={'cooldown_seconds':seconds}).status_code==422
  assert c.get('/api/state').json()==before


def test_shortening_extending_and_disabling_current_locks():
 start=datetime(2026,1,1,tzinfo=timezone.utc)
 state={'cooldown_seconds':40,'user_action_locks':{}}
 StateChangeCooldownService(lambda:start).mark_changed(state,'a')
 service=StateChangeCooldownService(lambda:start+timedelta(seconds=5))
 service.configure(state,7)
 assert service.is_locked(state,'a')
 assert not StateChangeCooldownService(lambda:start+timedelta(seconds=7)).is_locked(state,'a')
 # Expired locks must not reappear when increasing the duration.
 service.configure(state,20)
 assert not service.is_locked(state,'a')
 service.mark_changed(state,'b')
 service.configure(state,40)
 assert datetime.fromisoformat(state['user_action_locks']['b'])==start+timedelta(seconds=45)
 service.configure(state,0)
 assert state['user_action_locks']=={}
