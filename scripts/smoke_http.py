import json
import os
from pathlib import Path
import sys
import tempfile
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from desktop.runtime import LocalServer, configure_storage

with tempfile.TemporaryDirectory() as folder:
    os.environ["WAITING_LIST_DATA_DIR"] = folder
    os.environ.pop("WAITING_LIST_DB_PATH", None)
    configure_storage()
    from app.main import create_app
    app = create_app(desktop=True)

    with LocalServer(app, 0) as server:
        def participants(state, key):
            return [{k: v for k, v in user.items() if k not in {"created_at", "updated_at"}} for user in state[key]]

        def request(path, payload=None):
            data = json.dumps(payload).encode() if payload is not None else None
            req = Request(server.url + path, data=data, headers={"Content-Type": "application/json", "Authorization": "Bearer " + app.state.access_keys.admin})
            with urlopen(req, timeout=5) as response:
                return json.load(response)

        for path in ("/control", "/settings", "/overlay", "/static/overlay.js", "/static/overlay.css"):
            with urlopen(server.url + path, timeout=5) as response:
                assert response.status == 200
        for i in range(8):
            payload = dict(source="probe", externalMessageId=f"probe-{i}", receivedAt="2026-09-19T00:00:00Z",
                           displayName=f"Viewer{i}", userKey=f"user-{i}", message="参加希望")
            assert request("/api/comments/receive", payload)["command"] == "join"
        overlay = request("/api/overlay-state")
        assert overlay["queue_count"] == 2 and overlay["queue_group_count"] == 1
        assert set(overlay) == {"is_open", "now_view", "next_view", "queue_count", "queue_group_count", "total_waiting_count", "total_waiting_group_count", "appearance"}
        assert all(set(u) == {"display_name"} for s in ("now_view", "next_view") for u in overlay[s])
        assert "Viewer6" not in json.dumps(overlay) and "Viewer7" not in json.dumps(overlay)
        assert request("/api/comments/receive", payload)["duplicate"] is True
        before = request("/api/state")
        payload.update(externalMessageId="cancel-7", message="参加辞退")
        request("/api/comments/receive", payload)
        assert participants(request("/api/state"), "waiting") == participants(before, "waiting")
        request("/api/control/toggle-open", {})
        payload.update(externalMessageId="closed-9", userKey="user-9", message="参加希望")
        request("/api/comments/receive", payload)
        closed = request("/api/state")
        assert participants(closed, "current") == participants(before, "current")
        assert participants(closed, "waiting") == participants(before, "waiting")
        assert closed["logs"][-1] == "受付終了中の参加希望"
        request("/api/control/move-next", {})
        counts = request("/api/state")["participation_counts"]
        assert all(counts[u["user_id"]] == 1 for u in before["current"])
        assert all(counts[u["user_id"]] == 0 for u in before["waiting"])
    print(json.dumps({"ok": True, "real_http": True, "pages": 5, "participants": 8,
                      "queue_count": 2, "queue_group_count": 1, "duplicate_rejected": True,
                      "cooldown_blocks_cancel": True, "closed_join_unchanged": True,
                      "overlay_private_fields_absent": True, "server_stopped": not server.thread.is_alive()}))
