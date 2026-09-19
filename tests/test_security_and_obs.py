import asyncio
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json

import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.security import AccessKeys, LocalSecurityMiddleware
from app.schemas.comment import ReceivedComment
from app.services.comment_receive_service import CommentReceiveService
from app.services.application_services import ApplicationServices
from app.services.sqlite_persistence_service import SQLitePersistenceService
from app.initial_state import initial_state


@pytest.fixture
def client(tmp_path):
    app = create_app(db_path=str(tmp_path / "api.sqlite3"), desktop=True)
    with TestClient(app, base_url="http://127.0.0.1") as client:
        yield client


def admin(client):
    return {"Authorization": "Bearer " + client.app.state.access_keys.admin}


def payload(**changes):
    return dict(source="one", externalMessageId="id1", receivedAt="2026-09-19T00:00:00Z",
                displayName="視聴者", userKey="key", message="参加希望", **changes)


@pytest.mark.parametrize("path", ["/api/state", "/api/capabilities", "/api/connection", "/api/obs-status", "/api/desktop-settings", "/openapi.json"])
def test_private_reads_require_admin(client, path):
    assert client.get(path).status_code == 401
    assert client.get(path, headers=admin(client)).status_code == 200


def test_ingest_key_cannot_manage_or_read_state(client):
    headers = {"Authorization": "Bearer " + client.app.state.access_keys.ingest}
    assert client.post("/api/comments/receive", json=payload(), headers=headers).status_code == 200
    assert client.get("/api/state", headers=headers).status_code == 401
    assert client.post("/api/control/reset", headers=headers).status_code == 401
    assert client.post("/api/desktop/exit", headers=headers).status_code == 401


@pytest.mark.parametrize("headers,code", [({"Host":"evil.example"},400), ({"Host":"127.0.0.1.evil.example"},400),
    ({"Origin":"https://evil.example"},403), ({"Origin":"null"},403), ({"Sec-Fetch-Site":"cross-site"},403)])
def test_rebinding_and_cross_site_rejected_even_with_key(client, headers, code):
    assert client.post("/api/control/reset", headers={**admin(client), **headers}).status_code == code


def test_same_origin_allowed_and_key_never_in_overlay(client):
    assert client.post("/api/control/toggle-open", headers={**admin(client), "Origin":"http://127.0.0.1"}).status_code == 200
    response = client.get("/api/overlay-state")
    assert response.status_code == 200
    assert "participation_counts" not in response.text
    assert client.app.state.access_keys.admin not in response.text
    assert response.headers["referrer-policy"] == "no-referrer"


def test_body_and_field_limits(client):
    headers = {**admin(client), "Content-Type":"application/json"}
    assert client.post("/api/comments/receive", content=b"x" * 65537, headers=headers).status_code == 413
    data = payload(); data["message"] = "x" * 4097
    assert client.post("/api/comments/receive", json=data, headers=admin(client)).status_code == 422
    assert client.post("/api/control/reset", content="{}", headers={**admin(client),"Content-Type":"text/plain"}).status_code == 415
    assert client.get("/api/state", headers=admin(client)).json()["current"] == []


def test_chunked_body_cannot_bypass_limit():
    called = []
    async def downstream(scope, receive, send): called.append(True)
    keys = AccessKeys()
    app = LocalSecurityMiddleware(downstream, keys, max_body_bytes=10)
    messages = iter([{"type":"http.request", "body":b"123456", "more_body":True},
                     {"type":"http.request", "body":b"123456", "more_body":False}])
    replies = []
    async def receive(): return next(messages)
    async def send(message): replies.append(message)
    asyncio.run(app({"type":"http", "method":"POST", "path":"/api/comments/receive", "headers":[
        (b"host",b"127.0.0.1"), (b"authorization",("Bearer "+keys.ingest).encode()), (b"content-type",b"application/json")]}, receive, send))
    assert not called
    assert replies[0]["status"] == 413


def test_overlay_etag_and_preview_dont_fake_obs_access(client):
    before = client.get("/api/state", headers=admin(client)).json()
    sample = client.get("/overlay?sample=1&preview=1")
    assert sample.status_code == 200
    preview = client.get("/api/overlay-state?preview=1")
    assert client.get("/api/obs-status", headers=admin(client)).json()["last_access_seconds"] is None
    live = client.get("/api/overlay-state")
    assert live.headers["etag"] == preview.headers["etag"]
    assert client.get("/api/overlay-state", headers={"If-None-Match":live.headers["etag"]}).status_code == 304
    assert client.get("/api/obs-status", headers=admin(client)).json()["last_access_seconds"] is not None
    assert client.get("/api/state", headers=admin(client)).json() == before
    client.post("/api/control/toggle-open", headers=admin(client))
    changed = client.get("/api/overlay-state", headers={"If-None-Match":live.headers["etag"]})
    assert changed.status_code == 200 and changed.headers["etag"] != live.headers["etag"]


def test_source_scoped_dedup_and_concurrent_receipt():
    service = CommentReceiveService(log_writer=lambda message: None)
    a = ReceivedComment(**payload())
    b = a.model_copy(update={"source":"two"})
    assert not service.receive(a).duplicate
    assert not service.receive(b).duplicate
    concurrent = a.model_copy(update={"external_message_id":"parallel"})
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(service.receive, [concurrent] * 30))
    assert sum(not result.duplicate for result in results) == 1
    assert len(service._recent_ids) == 3


def test_closed_locked_rejoin_preserves_queue_and_lock(client):
    client.post("/api/comments/receive", json=payload(), headers=admin(client))
    client.post("/api/control/toggle-open", headers=admin(client))
    before = client.get("/api/state", headers=admin(client)).json()
    data = payload(); data["externalMessageId"] = "again"
    client.post("/api/comments/receive", json=data, headers=admin(client))
    after = client.get("/api/state", headers=admin(client)).json()
    assert "NOW参加中" in after["logs"][-1]
    assert after["user_action_locks"] == before["user_action_locks"]
    assert [(u["user_id"],u["display_name"]) for u in after["current"]] == [(u["user_id"],u["display_name"]) for u in before["current"]]


def test_legacy_counts_reconcile_without_loss(tmp_path):
    services = ApplicationServices(db_path=str(tmp_path / "old.sqlite3"), desktop=True)
    state = initial_state(desktop=True)
    state.update(current=[{"user_id":"old", "display_name":"旧データ", "participation_count":7}], participation_counts={"old":2})
    services.persistence_service.set_state(state)
    assert services.build_view_state()["participation_counts"]["old"] == 7
    services.move_next()
    assert services.build_view_state()["participation_counts"]["old"] == 8
    restored = ApplicationServices(db_path=str(tmp_path / "old.sqlite3"), desktop=True)
    assert restored.build_view_state()["participation_counts"]["old"] == 8
    restored.reset_state()
    assert restored.build_view_state()["participation_counts"] == {"old": 8}


def test_port_api_saves_for_restart(tmp_path):
    from desktop.config import DesktopConfig
    app = create_app(db_path=str(tmp_path / "port.sqlite3"), desktop=True, desktop_config=DesktopConfig(tmp_path))
    with TestClient(app, base_url="http://127.0.0.1") as client:
        assert client.post("/api/desktop-settings", json={"port":18081}, headers=admin(client)).json()["restart_required"]
        assert DesktopConfig(tmp_path).port == 18081
        assert client.post("/api/desktop-settings", json={"port":0}, headers=admin(client)).status_code == 422


def test_logs_do_not_change_participant_updated_at(tmp_path):
    services = ApplicationServices(db_path=str(tmp_path / "times.sqlite3"), desktop=True)
    services.receive_comment(ReceivedComment(**payload()))
    before = services.build_view_state()["current"][0]["updated_at"]
    services.add_log("log-only")
    assert services.build_view_state()["current"][0]["updated_at"] == before
