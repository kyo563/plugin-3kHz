import json
import random
import sqlite3
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from threading import Event
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.services.application_services import ApplicationServices
from app.services.operator_service import add_participant, correct_count, export_backup
from desktop.config import DesktopConfig, load_keys

@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(db_path=str(tmp_path/'api.db'), desktop=True), base_url="http://127.0.0.1", raise_server_exceptions=False) as c:
        c.headers['Authorization'] = 'Bearer ' + c.app.state.access_keys.admin
        yield c

@pytest.mark.parametrize('body', [b'{', b'{"user_id":"m","participation_count":NaN}', b'{"user_id":"m","participation_count":Infinity}', b'['*1100+b']'*1100, b'{"display_name":"\\ud800"}'], ids=['syntax','nan','infinity','deep','surrogate'])
def test_malformed_json_never_500_or_mutates(client, body):
    before=client.get('/api/state').json()
    path='/api/control/add-user' if b'display_name' in body else '/api/control/correct-count'
    r=client.post(path,content=body,headers={'Content-Type':'application/json'})
    assert r.status_code in {400,422}
    assert client.get('/api/state').json()==before

@pytest.mark.parametrize('data', [[], None, 42, {'admin':'a'*43,'ingest':'a'*43}, {'admin':'あ'*43,'ingest':'b'*43}])
def test_invalid_key_files_fail_clearly_without_rewrite(tmp_path, data):
    path=tmp_path/'access-keys.json'; path.write_text(json.dumps(data),encoding='utf-8')
    original=path.read_bytes()
    with pytest.raises(ValueError): load_keys(tmp_path)
    assert path.read_bytes()==original

def test_parallel_port_writes_are_serialized(tmp_path,monkeypatch):
    import desktop.config as config_module
    config=DesktopConfig(tmp_path)
    entered,release,second_started=Event(),Event(),Event()
    original=config_module.atomic_json
    def delayed(path,value):
        if value['port']==19001:
            entered.set(); assert release.wait(5)
        return original(path,value)
    monkeypatch.setattr(config_module,'atomic_json',delayed)
    def second():
        second_started.set(); config.save_port(19002)
    with ThreadPoolExecutor(2) as pool:
        first=pool.submit(config.save_port,19001); assert entered.wait(5)
        following=pool.submit(second); assert second_started.wait(5)
        try:
            assert not following.done()
            # The first write owns the whole update; later requests must wait.
            with pytest.raises(TimeoutError): following.result(timeout=.1)
        finally: release.set()
        first.result(); following.result()
    assert DesktopConfig(tmp_path).port==config.port==19002

def test_write_failure_rolls_back_and_keeps_undo(tmp_path,monkeypatch):
    services=ApplicationServices(db_path=str(tmp_path/'state.db'),desktop=True)
    add_participant(services,'Name','m')
    store=services.persistence_service
    before=store.snapshot(); original=store._connect
    @contextmanager
    def failing():
        with original() as conn:
            conn.execute("CREATE TEMP TRIGGER reject_participants BEFORE INSERT ON participants BEGIN SELECT RAISE(ABORT,'simulated disk write failure'); END")
            yield conn
    with monkeypatch.context() as patch:
        patch.setattr(store,'_connect',failing)
        with pytest.raises(sqlite3.IntegrityError): correct_count(services,'m',7)
    assert store.snapshot()==before
    store.undo()
    assert store.get_state()['current']==[]

@pytest.mark.parametrize('seed', [17,83,2026])
def test_random_operation_sequences_keep_invariants(tmp_path,seed):
    services=ApplicationServices(db_path=str(tmp_path/'random.db'),desktop=True)
    rng=random.Random(seed)
    for index in range(200):
        current=services.build_view_state(); users=current['current']+current['waiting']
        action=rng.randrange(7)
        if action==0 and current['is_open']: add_participant(services,f'名前{index}😀',f'm{index}')
        elif action==1: services.move_next()
        elif action==2: services.toggle_open()
        elif action==3: services.toggle_priority()
        elif action==4 and users: correct_count(services,rng.choice(users)['user_id'],rng.randrange(10))
        elif action==5 and users: services.persistence_service.manual_mutate(lambda s: services.queue_service.remove_user_by_id(s,users[0]['user_id']))
        elif action==6 and current['undo_available']: services.persistence_service.undo()
        state=services.build_view_state(); all_users=state['current']+state['waiting']
        assert len(state['current'])<=3
        assert len({u['user_id'] for u in all_users})==len(all_users)
        assert len(state['logs'])<=30
        assert all(u['participation_count']==state['participation_counts'][u['user_id']] for u in all_users)
        assert not any(u.get('is_placeholder') for u in all_users)
        export_backup(services)

def test_parallel_adds_and_snapshots_do_not_lose_users(tmp_path):
    services=ApplicationServices(db_path=str(tmp_path/'parallel.db'),desktop=True)
    def add(i):
        add_participant(services,f'User{i}',f'm{i}')
        view=services.build_view_state()
        assert len(view['current'])<=3
        return view['revision']
    with ThreadPoolExecutor(8) as pool: list(pool.map(add,range(100)))
    state=services.build_view_state()
    assert len(state['current'])==3 and len(state['waiting'])==97
    assert len(state['participation_counts'])==100
    backup=export_backup(services)
    services.persistence_service.restore({**backup.state.model_dump(),'user_action_locks':{}},state['revision'])
    assert len(services.build_view_state()['waiting'])==97


def test_count_ceiling_does_not_break_backup_or_partial_advance(client):
    for i in range(2):
        assert client.post('/api/control/add-user',json={'display_name':f'Name{i}','user_id':f'm{i}'}).status_code==200
    assert client.post('/api/control/correct-count',json={'user_id':'m1','participation_count':2147483647}).status_code==200
    before=client.get('/api/state').json()
    assert client.post('/api/control/move-next').status_code==409
    assert client.get('/api/state').json()==before
    assert client.get('/api/control/backup').status_code==200

@pytest.mark.parametrize('name', ['😀日本語<&>"', '名'*200])
def test_unicode_boundary_backup_roundtrip(client,name):
    assert client.post('/api/control/add-user',json={'display_name':name}).status_code==200
    backup=client.get('/api/control/backup').json()
    revision=client.get('/api/state').json()['revision']
    restored=client.post('/api/control/restore',json={'backup':backup,'expected_revision':revision})
    assert restored.status_code==200
    assert restored.json()['current'][0]['display_name']==name

@pytest.mark.parametrize('value',[None,[],42,{'port':True},{'port':65536}])
def test_invalid_port_file_preserved(tmp_path,value):
    path=tmp_path/'desktop.json'; path.write_text(json.dumps(value),encoding='utf-8')
    original=path.read_bytes()
    with pytest.raises(ValueError): DesktopConfig(tmp_path)
    assert path.read_bytes()==original
