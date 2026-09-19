import json
import socket
import subprocess
import sys
from pathlib import Path
from urllib.request import urlopen

import pytest
from fastapi import FastAPI

from desktop.runtime import InstanceLock, LocalServer, configure_storage


def test_storage_uses_local_app_data_and_preserves_explicit_db(tmp_path, monkeypatch):
    monkeypatch.delenv("WAITING_LIST_DATA_DIR", raising=False)
    monkeypatch.delenv("WAITING_LIST_DB_PATH", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    folder = configure_storage()
    assert folder == tmp_path / "WaitingListApp"
    import os
    assert Path(os.environ["WAITING_LIST_DB_PATH"]) == folder / "waiting_list.sqlite3"
    custom = tmp_path / "custom.sqlite3"
    monkeypatch.setenv("WAITING_LIST_DB_PATH", str(custom))
    configure_storage()
    assert Path(os.environ["WAITING_LIST_DB_PATH"]) == custom


@pytest.mark.skipif(sys.platform != "win32", reason="Windows msvcrt instance lock")
def test_same_database_lock_rejected_and_released(tmp_path):
    path = tmp_path / "app.lock"
    with InstanceLock(path):
        with pytest.raises(RuntimeError, match="既に起動"):
            with InstanceLock(path):
                pass
    with InstanceLock(path):
        pass


def test_server_readiness_conflict_and_shutdown():
    app = FastAPI()

    @app.get("/ready")
    def ready():
        return {"ready": True}

    with LocalServer(app, 0) as server:
        with urlopen(server.url + "/ready", timeout=3) as response:
            assert json.load(response) == {"ready": True}
        with pytest.raises(RuntimeError, match="ポート"):
            LocalServer(app, server.port)
    assert not server.thread.is_alive()
    with socket.socket() as client:
        assert client.connect_ex(("127.0.0.1", server.port)) != 0


def test_desktop_empty_state_and_restart_restoration(tmp_path):
    root = Path(__file__).resolve().parents[1]
    import os
    env = {**os.environ, "WAITING_LIST_DATA_DIR": str(tmp_path)}
    env.pop("WAITING_LIST_DB_PATH", None)
    initialize = '''
from desktop.runtime import configure_storage
configure_storage()
from app import mock_state
assert mock_state.build_view_state()["current"] == []
assert mock_state.build_view_state()["waiting"] == []
mock_state.toggle_open()
'''
    restore = '''
from desktop.runtime import configure_storage
configure_storage()
from app import mock_state
assert mock_state.build_view_state()["is_open"] is False
mock_state.reset_state()
assert mock_state.build_view_state()["current"] == []
assert mock_state.build_view_state()["waiting"] == []
'''
    for script in (initialize, restore):
        result = subprocess.run([sys.executable, "-c", script], cwd=root, env=env, capture_output=True, text=True, timeout=15)
        assert result.returncode == 0, result.stderr


def test_sqlite_handles_are_closed_after_each_operation(tmp_path):
    from app.services.sqlite_persistence_service import SQLitePersistenceService
    path = tmp_path / "state.sqlite3"
    service = SQLitePersistenceService({"is_open": True, "priority_mode": True,
        "cooldown_seconds": 40, "current": [], "waiting": [], "logs": []}, str(path))
    service.mutate_state(lambda state: state.update(is_open=False))
    assert service.get_state()["is_open"] is False
    # Windows refuses this while SQLite connection handles are still open.
    path.unlink()
    assert not path.exists()
