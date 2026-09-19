from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.services.application_services import ApplicationServices

@pytest.fixture
def client(tmp_path):
    app = create_app(db_path=str(tmp_path / "state.sqlite3"), desktop=True)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        client.headers["Authorization"] = "Bearer " + app.state.access_keys.admin
        yield client

def add(client, name="参加者", user_id=None):
    return client.post("/api/control/add-user", json={"display_name":name,"user_id":user_id})

def state(client):
    return client.get("/api/state").json()

def test_add_identity_closed_and_duplicate(client):
    first = add(client).json()["current"][0]
    assert first["user_id"].startswith("manual:")
    assert add(client).status_code == 200  # names are not identities
    assert add(client, user_id=first["user_id"]).status_code == 409
    client.post("/api/control/toggle-open")
    before = state(client)
    assert add(client).status_code == 409
    assert state(client) == before
    assert add(client, name=" ").status_code == 422
    assert add(client, name="参加者募集中").status_code == 422

def test_correct_downward_persist_rejoin_and_privacy(client):
    add(client, user_id="manual:known")
    for count in [5, 0, 2]:
        response = client.post("/api/control/correct-count", json={"user_id":"manual:known", "participation_count":count})
        assert response.status_code == 200
        assert state(client)["current"][0]["participation_count"] == count
        assert state(client)["participation_counts"]["manual:known"] == count
    client.post("/api/control/remove-user", json={"user_id":"manual:known"})
    assert add(client, user_id="manual:known").json()["current"][0]["participation_count"] == 2
    overlay = client.get("/api/overlay-state").text
    assert "participation_count" not in overlay and "manual:known" not in overlay

@pytest.mark.parametrize("count", [-1, 1.5, True, "2", 2147483648])
def test_bad_counts_are_atomic(client, count):
    add(client, user_id="m")
    before = state(client)
    assert client.post("/api/control/correct-count", json={"user_id":"m","participation_count":count}).status_code == 422
    assert state(client) == before

def test_undo_next_and_remove_single_level(client):
    for i in range(7): add(client, user_id=f"m{i}")
    before = state(client)
    client.post("/api/control/move-next")
    assert state(client)["participation_counts"]["m0"] == 1
    assert client.post("/api/control/undo").status_code == 200
    after = state(client)
    assert [u["user_id"] for u in after["current"]] == [u["user_id"] for u in before["current"]]
    assert after["participation_counts"] == before["participation_counts"]
    assert client.post("/api/control/undo").status_code == 409
    client.post("/api/control/remove-user", json={"user_id":"m0"})
    assert client.post("/api/control/undo").status_code == 200
    assert state(client)["current"][0]["user_id"] == "m0"

def test_comment_invalidates_undo_and_is_preserved(client):
    add(client)
    response = client.post("/api/comments/receive", json={"source":"one", "externalMessageId":"new", "receivedAt":"2026-09-19T00:00:00Z", "displayName":"外部参加者", "userKey":"k", "message":"参加希望"})
    assert response.status_code == 200
    assert not state(client)["undo_available"]
    assert client.post("/api/control/undo").status_code == 409
    assert len(state(client)["current"]) == 2

def test_backup_restore_roundtrip_and_stale_revision(client):
    add(client, name="日本語😀", user_id="manual:saved")
    backup = client.get("/api/control/backup").json()
    assert set(backup) == {"format", "version", "state"}
    assert "user_action_locks" not in backup["state"]
    assert "access_keys" not in str(backup)
    old = state(client)["revision"]
    client.post("/api/control/reset")
    assert client.post("/api/control/restore", json={"backup":backup,"expected_revision":old}).status_code == 409
    response = client.post("/api/control/restore", json={"backup":backup,"expected_revision":state(client)["revision"]})
    assert response.status_code == 200
    assert response.json()["current"][0]["display_name"] == "日本語😀"
    assert not response.json()["undo_available"]
    assert response.json()["user_action_locks"] == {}

@pytest.mark.parametrize("kind", ["duplicate", "too_many_now", "count", "extra", "version", "placeholder", "bad_boolean"])
def test_invalid_backup_leaves_state_intact(client, kind):
    add(client, user_id="m")
    backup = client.get("/api/control/backup").json()
    user = backup["state"]["current"][0]
    if kind == "duplicate": backup["state"]["waiting"].append(deepcopy(user))
    if kind == "too_many_now": backup["state"]["current"] *= 4
    if kind == "count": user["participation_count"] = 4
    if kind == "extra": backup["state"]["db_path"] = "other-app.sqlite3"
    if kind == "version": backup["version"] = 2
    if kind == "placeholder": user["display_name"] = "参加者募集中"
    if kind == "bad_boolean": backup["state"]["is_open"] = "true"
    before = state(client)
    assert client.post("/api/control/restore", json={"backup":backup,"expected_revision":before["revision"]}).status_code == 422
    assert state(client) == before

def test_backup_auth_and_limit(client):
    ingest = {"Authorization":"Bearer " + client.app.state.access_keys.ingest}
    assert client.get("/api/control/backup", headers=ingest).status_code == 401
    assert client.post("/api/control/restore", json={}, headers=ingest).status_code == 401
    assert client.post("/api/control/restore", content=b"x"*(4*1024*1024+1), headers={"Content-Type":"application/json"}).status_code == 413

def test_restart_keeps_correction_loses_undo(tmp_path):
    from app.services.operator_service import add_participant, correct_count
    db = str(tmp_path / "state.sqlite3")
    first = ApplicationServices(db_path=db, desktop=True)
    add_participant(first, "Name", "m")
    correct_count(first, "m", 3)
    second = ApplicationServices(db_path=db, desktop=True)
    assert second.build_view_state()["current"][0]["participation_count"] == 3
    assert not second.build_view_state()["undo_available"]

def test_undo_race_only_once(client):
    add(client)
    store = client.app.state.services.persistence_service
    def attempt(_):
        try: store.undo(); return True
        except ValueError: return False
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(attempt, range(2))) == [False, True]
    assert state(client)["current"] == []
