import os
from pathlib import Path
import subprocess
import sys

from fastapi.testclient import TestClient as BaseTestClient

def TestClient(app):
    return BaseTestClient(app, base_url="http://127.0.0.1", headers={"Authorization": "Bearer " + app.state.access_keys.admin})

from app.main import create_app
from app.services.application_services import ApplicationServices


def comment():
    return dict(source="factory-test", externalMessageId="same-message", receivedAt="2026-09-19T00:00:00Z",
                displayName="参加者", userKey="same-user", message="参加希望")


def test_import_and_factory_do_not_create_database(tmp_path):
    db = tmp_path / "never-created" / "state.sqlite3"
    script = "from app.main import app, create_app; from app import mock_state; create_app()"
    result = subprocess.run([sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, "WAITING_LIST_DB_PATH": str(db)}, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    assert not db.parent.exists()


def test_two_apps_isolate_database_and_duplicate_cache(tmp_path):
    a = create_app(db_path=str(tmp_path / "a.sqlite3"), desktop=True)
    b = create_app(db_path=str(tmp_path / "b.sqlite3"), desktop=True)
    with TestClient(a) as first, TestClient(b) as second:
        assert first.post("/api/comments/receive", json=comment()).json()["duplicate"] is False
        assert second.get("/api/state").json()["current"] == []
        assert second.post("/api/comments/receive", json=comment()).json()["duplicate"] is False
        assert first.post("/api/comments/receive", json=comment()).json()["duplicate"] is True
        first.post("/api/control/toggle-open")
        assert second.get("/api/state").json()["is_open"] is True
    assert not hasattr(a.state, "services")
    assert not hasattr(b.state, "services")


def test_restart_restores_state_and_releases_database(tmp_path):
    db = tmp_path / "state.sqlite3"
    for attempt in range(2):
        with TestClient(create_app(db_path=str(db), desktop=True)) as client:
            if attempt == 0:
                client.post("/api/comments/receive", json=comment())
                client.post("/api/control/toggle-open")
            else:
                state = client.get("/api/state").json()
                assert state["is_open"] is False
                assert state["current"][0]["display_name"] == "参加者"
                assert state["user_action_locks"]
    db.unlink()  # Windows rejects this if a SQLite handle is still open.


def test_development_endpoints_disabled_by_default(tmp_path):
    with TestClient(create_app(db_path=str(tmp_path / "prod.sqlite3"), desktop=True)) as client:
        paths = ["/api/mock/" + name for name in ("add", "cancel", "move-next", "toggle-open", "toggle-priority", "reset")]
        paths.append("/api/comments/manual")
        for path in paths:
            assert client.post(path, json=comment()).status_code == 404
        assert not set(paths).intersection(client.get("/openapi.json").json()["paths"])
        assert client.get("/api/capabilities").json() == {"development": False}
        assert client.get("/api/state").json()["current"] == []
        assert client.post("/api/control/toggle-open").status_code == 200


def test_development_is_explicit_and_per_app(tmp_path):
    app = create_app(db_path=str(tmp_path / "dev.sqlite3"), desktop=True, development=True)
    with TestClient(app) as client:
        assert client.get("/api/capabilities").json() == {"development": True}
        assert client.post("/api/mock/add").json()["current"][0]["user_id"] == "test1"
        assert client.post("/api/comments/manual", json=comment()).status_code == 200
        assert client.post("/api/mock/reset").json()["current"] == []


def test_injected_services_do_not_create_default_database(tmp_path):
    unused = tmp_path / "unused.sqlite3"
    services = ApplicationServices(db_path=str(tmp_path / "injected.sqlite3"), desktop=True)
    with TestClient(create_app(db_path=str(unused), services=services)) as client:
        client.post("/api/control/toggle-open")
        assert services.build_view_state()["is_open"] is False
    assert not unused.exists()


def test_configuration_is_captured_before_environment_changes(tmp_path, monkeypatch):
    selected = tmp_path / "selected.sqlite3"
    other = tmp_path / "other.sqlite3"
    monkeypatch.setenv("WAITING_LIST_DB_PATH", str(selected))
    app = create_app(desktop=True)
    monkeypatch.setenv("WAITING_LIST_DB_PATH", str(other))
    with TestClient(app) as client:
        assert client.get("/api/state").json()["current"] == []
    assert selected.exists()
    assert not other.exists()
