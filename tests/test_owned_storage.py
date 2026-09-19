import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from desktop.config import DesktopConfig, load_keys
from desktop.ownership import OwnershipCatalog, safe_path
from desktop.runtime import InstanceLock

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows ownership and file locking")


def test_cleanup_exact_owned_files_and_preserve_other_apps(tmp_path):
    catalog = OwnershipCatalog(tmp_path / "catalog")
    folder = tmp_path / "日本語 空白" / "data"
    db = tmp_path / "shared" / "my.sqlite3"
    cache = catalog.register(folder, db)
    db.write_bytes(b"test-db")
    (Path(str(db) + "-wal")).write_bytes(b"wal")
    for name in ("desktop.log", "desktop.json", "access-keys.json"):
        (folder / name).write_text("owned")
    (cache / "cache.bin").write_bytes(b"cache")
    unknown = folder / "my-backup.txt"; unknown.write_bytes(b"keep")
    outside = db.parent / "other-app.sqlite3"; outside.write_bytes(b"other")
    obs = tmp_path / "obs-studio"; obs.mkdir(); (obs / "scene.json").write_bytes(b"scene")
    result = catalog.remove()
    assert result["errors"] == []
    assert not db.exists() and not cache.exists()
    assert unknown.read_bytes() == b"keep" and outside.read_bytes() == b"other"
    assert (obs / "scene.json").read_bytes() == b"scene"
    assert catalog.remove()["errors"] == []


def test_running_app_prevents_any_deletion(tmp_path):
    catalog = OwnershipCatalog(tmp_path / "catalog")
    folder = tmp_path / "data"; db = folder / "waiting_list.sqlite3"
    catalog.register(folder, db); db.write_bytes(b"keep")
    with InstanceLock(db.with_suffix(".lock")):
        with pytest.raises(RuntimeError): catalog.remove()
    assert db.read_bytes() == b"keep"
    assert catalog.remove()["errors"] == []


def test_mismatched_marker_prevents_all_deletion(tmp_path):
    catalog = OwnershipCatalog(tmp_path / "catalog")
    folder = tmp_path / "data"; db = folder / "waiting_list.sqlite3"
    catalog.register(folder, db); db.write_bytes(b"keep")
    (folder / ".waiting-list-owner").write_text("other-owner")
    with pytest.raises(ValueError): catalog.remove()
    assert db.exists()


def test_junction_in_cache_is_rejected_without_deleting_target(tmp_path):
    catalog = OwnershipCatalog(tmp_path / "catalog")
    folder = tmp_path / "data"; db = folder / "waiting_list.sqlite3"
    cache = catalog.register(folder, db); db.write_bytes(b"keep")
    outside = tmp_path / "other-app"; outside.mkdir(); (outside / "keep.txt").write_bytes(b"other")
    junction = cache / "linked"
    result = subprocess.run(["cmd", "/c", "mklink", "/J", str(junction), str(outside)], capture_output=True)
    assert result.returncode == 0
    try:
        with pytest.raises(ValueError, match="再解析"): catalog.remove()
        assert db.exists() and (outside / "keep.txt").read_bytes() == b"other"
    finally:
        os.rmdir(junction)  # Remove only the junction itself, never its target.
    assert catalog.remove()["errors"] == []


def test_locked_payload_is_reported_and_retryable(tmp_path):
    catalog = OwnershipCatalog(tmp_path / "catalog")
    folder = tmp_path / "data"; db = folder / "waiting_list.sqlite3"
    catalog.register(folder, db); db.write_bytes(b"test")
    # Windows open file handles block unlink.
    with db.open("rb"):
        result = catalog.remove()
        assert result["errors"]
        assert catalog.path.exists()
        assert (folder / ".waiting-list-owner").exists()
    assert catalog.remove()["errors"] == []


def test_existing_db_not_claimed_implicitly(tmp_path):
    db = tmp_path / "old.sqlite3"; db.write_bytes(b"other")
    catalog = OwnershipCatalog(tmp_path / "catalog")
    with pytest.raises(ValueError, match="未登録"): catalog.register(tmp_path / "data", db)
    assert db.read_bytes() == b"other"


def test_port_and_keys_persist_across_restart(tmp_path):
    config = DesktopConfig(tmp_path)
    assert config.port == 8080
    config.save_port(18081)
    assert DesktopConfig(tmp_path).port == 18081
    first = load_keys(tmp_path); second = load_keys(tmp_path)
    assert first == second and first.admin != first.ingest
    with pytest.raises(ValueError): config.save_port(0)


def test_full_removal_then_reinstall_starts_with_new_keys(tmp_path):
    catalog = OwnershipCatalog(tmp_path / "catalog")
    folder = tmp_path / "data"; db = folder / "waiting_list.sqlite3"
    catalog.register(folder, db)
    old = load_keys(folder)
    DesktopConfig(folder).save_port(18081)
    assert catalog.remove()["errors"] == []
    assert not folder.exists()
    catalog.register(folder, db)
    assert load_keys(folder) != old
    assert DesktopConfig(folder).port == 8080


def test_interrupted_marker_cleanup_can_retry(tmp_path, monkeypatch):
    catalog = OwnershipCatalog(tmp_path / "catalog")
    folder = tmp_path / "data"; db = folder / "waiting_list.sqlite3"
    cache = catalog.register(folder, db); db.write_bytes(b"test")
    marker = folder / ".waiting-list-owner"
    real_unlink = Path.unlink
    def fail_one(path, *args, **kwargs):
        if path == marker:
            raise PermissionError("simulated interruption")
        return real_unlink(path, *args, **kwargs)
    with monkeypatch.context() as context:
        context.setattr(Path, "unlink", fail_one)
        assert catalog.remove()["errors"]
    assert catalog.remove()["errors"] == []
    assert not folder.exists()


def test_unregistered_legacy_data_not_reported_as_deleted(tmp_path):
    root = tmp_path / "WaitingListApp"; root.mkdir()
    (root / "waiting_list.sqlite3").write_bytes(b"legacy")
    with pytest.raises(ValueError, match="未登録"):
        OwnershipCatalog(root).remove()
    assert (root / "waiting_list.sqlite3").exists()


def test_explicit_legacy_adoption_preserves_state(tmp_path):
    from app.initial_state import initial_state
    from app.services.sqlite_persistence_service import SQLitePersistenceService
    folder = tmp_path / "data"; db = folder / "waiting_list.sqlite3"
    state = initial_state(desktop=True); state["is_open"] = False
    service = SQLitePersistenceService(state, str(db))
    catalog = OwnershipCatalog(tmp_path / "catalog")
    catalog.register(folder, db, adopt_existing=True)
    assert service.get_state()["is_open"] is False
    assert catalog.remove()["errors"] == []


def test_prepare_uninstall_uses_authenticated_exit_only(tmp_path):
    from app.main import create_app
    from desktop.runtime import LocalServer
    from desktop.uninstall import prepare_uninstall
    folder = tmp_path / "data"; db = folder / "waiting_list.sqlite3"
    catalog = OwnershipCatalog(tmp_path / "catalog")
    catalog.register(folder, db)
    keys = load_keys(folder)
    app = create_app(db_path=str(db), desktop=True, access_keys=keys)
    called = []
    app.state.request_exit = lambda: called.append(True)
    with LocalServer(app, 0) as server:
        (folder / "runtime.json").write_text(json.dumps({"port":server.port}))
        prepare_uninstall(catalog)
        assert called == [True]
    assert catalog.remove()["errors"] == []
