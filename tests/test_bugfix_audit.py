from contextlib import contextmanager
import sqlite3
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.initial_state import initial_state
from app.services.sqlite_persistence_service import SQLitePersistenceService

@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(db_path=str(tmp_path / "api.db"), desktop=True), base_url="http://127.0.0.1", raise_server_exceptions=False) as c:
        c.headers["Authorization"] = "Bearer " + c.app.state.access_keys.admin
        yield c

def test_non_ascii_auth_is_401_not_500(client):
    assert client.get("/api/state", headers={b"Authorization":b"Bearer \xff"}).status_code == 401

@pytest.mark.parametrize("name", ["   ", "参加者募集中"])
def test_invalid_comment_name_rejected_before_state_changes(client, name):
    before = client.get("/api/state").json()
    response = client.post("/api/comments/receive", json={"source":"test", "userKey":"one", "displayName":name, "receivedAt":"2026-09-19", "message":"参加希望"})
    assert response.status_code == 422
    assert client.get("/api/state").json() == before

def test_revision_does_not_repeat_after_restart(tmp_path):
    path = str(tmp_path / "state.db")
    first = SQLitePersistenceService(initial_state(desktop=True), path)
    before, old_revision, _ = first.snapshot()
    restarted = SQLitePersistenceService(initial_state(desktop=True), path)
    restarted.mutate_state(lambda s: s.update(is_open=False))
    with pytest.raises(ValueError):
        restarted.restore(before, old_revision)
    assert not restarted.get_state()["is_open"]

def test_finished_rows_do_not_rejoin_waiting(tmp_path):
    path = str(tmp_path / "state.db")
    store = SQLitePersistenceService(initial_state(desktop=True), path)
    with sqlite3.connect(path) as conn:
        for status in ("done", "cancelled"):
            conn.execute("INSERT INTO participants(user_id,display_name,status,position,participation_count,created_at,updated_at) VALUES(?,?,?,0,2,'now','now')", (status,status,status))
    assert store.get_state()["waiting"] == []
    store.mutate_state(lambda state: state["participation_counts"].update(done=0))
    assert store.get_state()["participation_counts"]["done"] == 0
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT count(*) FROM participants WHERE status='done'").fetchone()[0] == 1

def test_read_is_one_sqlite_snapshot(tmp_path, monkeypatch):
    path = str(tmp_path / "state.db")
    store = SQLitePersistenceService(initial_state(desktop=True), path)
    with sqlite3.connect(path) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
    original = store._connect
    fired = False
    @contextmanager
    def hooked():
        nonlocal fired
        with original() as conn:
            def trace(sql):
                nonlocal fired
                if 'FROM participants' in sql and not fired:
                    fired = True
                    with sqlite3.connect(path) as writer:
                        writer.execute("UPDATE app_state SET value='0' WHERE key='is_open'")
                        writer.execute("DELETE FROM operation_logs")
                        writer.execute("INSERT INTO operation_logs(message,created_at) VALUES('new version','now')")
            conn.set_trace_callback(trace)
            yield conn
    monkeypatch.setattr(store, '_connect', hooked)
    result = store.get_state()
    assert fired
    assert result['is_open'] is True
    assert result['logs'] != ['new version']


def test_manual_reset_cannot_split_comment_receive_and_apply(client, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from app.schemas.comment import ReceivedComment
    services = client.app.state.services
    receive = services.receive_service.receive
    logged, release, reset_started, reset_finished = Event(), Event(), Event(), Event()
    def paused(comment):
        result = receive(comment)
        logged.set()
        assert release.wait(5)
        return result
    monkeypatch.setattr(services.receive_service, "receive", paused)
    def reset():
        reset_started.set()
        services.reset_state()
        reset_finished.set()
    comment = ReceivedComment(source="test", userKey="u", displayName="Name", receivedAt="now", message="参加希望")
    with ThreadPoolExecutor(max_workers=2) as pool:
        incoming = pool.submit(services.receive_comment, comment)
        assert logged.wait(5)
        resetting = pool.submit(reset)
        assert reset_started.wait(5)
        try:
            assert not reset_finished.wait(0.1)
        finally:
            release.set()
        incoming.result(timeout=5)
        resetting.result(timeout=5)
    assert services.build_view_state()["current"] == []
