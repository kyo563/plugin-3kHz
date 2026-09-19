import json
import sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from desktop.config import DesktopConfig, load_keys
from desktop.activation import activate_existing, single_instance
from desktop.runtime import InstanceLock, LocalServer


def test_onboarding_survives_port_change_and_restart(tmp_path):
    config = DesktopConfig(tmp_path)
    assert not config.onboarding_completed
    config.complete_onboarding()
    config.save_port(18089)
    reopened = DesktopConfig(tmp_path)
    assert reopened.onboarding_completed and reopened.port == 18089


def test_first_run_api_and_activation_auth(tmp_path):
    config = DesktopConfig(tmp_path)
    app = create_app(db_path=str(tmp_path/'app.db'),desktop=True,desktop_config=config)
    activated=[]
    with TestClient(app,base_url='http://127.0.0.1') as client:
        admin={'Authorization':'Bearer '+app.state.access_keys.admin}
        ingest={'Authorization':'Bearer '+app.state.access_keys.ingest}
        assert client.post('/api/desktop/activate',headers=ingest).status_code==401
        assert client.post('/api/desktop/onboarding-complete',headers=ingest).status_code==401
        assert client.post('/api/desktop/activate',headers=admin).status_code==409
        app.state.request_activate=lambda: activated.append(True)
        assert client.post('/api/desktop/activate',headers=admin).json()=={'activated':True}
        assert activated==[True]
        before=client.get('/api/state',headers=admin).json()
        assert not client.get('/api/desktop-settings',headers=admin).json()['onboarding_completed']
        assert client.post('/api/desktop/onboarding-complete',headers=admin).status_code==200
        assert client.get('/api/state',headers=admin).json()==before
        assert DesktopConfig(tmp_path).onboarding_completed


@pytest.mark.skipif(sys.platform!='win32',reason='Windows instance lock')
def test_duplicate_launch_activates_only_matching_db(tmp_path):
    db=tmp_path/'app.db'; keys=load_keys(tmp_path); calls=[]
    app=create_app(db_path=str(db),desktop=True,access_keys=keys)
    app.state.request_activate=lambda:calls.append(True)
    with LocalServer(app,0) as server:
        (tmp_path/'runtime.json').write_text(json.dumps({'port':server.port,'db':str(db)}),encoding='utf-8')
        assert not activate_existing(tmp_path,tmp_path/'other.db',attempts=1)
        with InstanceLock(db.with_suffix('.lock')):
            with single_instance(tmp_path,db) as acquired:
                assert acquired is False
        assert calls==[True]
    with single_instance(tmp_path,db) as acquired:
        assert acquired is True


def test_activation_missing_runtime_does_not_create_key(tmp_path):
    assert not activate_existing(tmp_path,tmp_path/'app.db',attempts=1)
    assert not (tmp_path/'access-keys.json').exists()
