import pytest
from fastapi.testclient import TestClient

from app.main import create_app


DISPLAY = "/api/obs-counters"
SETTINGS = "/api/settings/obs-counters"


@pytest.fixture
def counter_client(tmp_path):
    app = create_app(db_path=str(tmp_path / "queue.db"), desktop=True, onecomme=True)
    with TestClient(app, base_url="http://127.0.0.1:18765") as client:
        yield client


def authenticate(client):
    client.headers["Authorization"] = "Bearer " + client.app.state.access_keys.admin


def add(client, user_id, name):
    assert client.post("/api/control/add-user", json={"user_id": user_id, "display_name": name}).is_success


def displayed_wording(client):
    data = client.get(DISPLAY).json()
    return {kind: data[kind] for kind in ("round", "unique")}


def test_two_sources_count_completed_matches_and_unique_users_and_undo(counter_client):
    client = counter_client
    assert displayed_wording(client) == {"round": "", "unique": "現在0人の方と対戦済み"}
    for kind in ("round", "unique"):
        assert "/static/obs-counter.js" in client.get(f"/onecomme-counter/{kind}").text
    assert client.get(DISPLAY).headers["cross-origin-resource-policy"] == "same-origin"
    assert client.get(DISPLAY, headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert client.get(DISPLAY, headers={"Host": "untrusted.example"}).status_code == 400
    assert client.get(SETTINGS).status_code == 401
    assert client.post(SETTINGS, json={}).status_code == 401
    authenticate(client)
    assert client.get("/api/obs-status").json()["last_access_seconds"] is not None
    assert client.post("/api/settings/group-size", json={"group_size": 2}).is_success
    add(client, "a", "same name")
    add(client, "b", "same name")
    add(client, "waiting", "not played yet")
    assert displayed_wording(client) == {"round": "現在1局目", "unique": "現在0人の方と対戦済み"}
    first = client.post("/api/control/move-next").json()
    assert first["match_undo_available"]
    assert displayed_wording(client) == {"round": "現在2局目", "unique": "現在2人の方と対戦済み"}
    # Starting a new export segment retains the current stream totals.
    assert client.post("/api/control/history/start", json={"label": "Part 2"}).is_success
    add(client, "a", "changed name")
    assert client.post("/api/control/undo-match", json={"expected_revision": first["revision"]}).status_code == 409
    second = client.post("/api/control/move-next").json()
    assert displayed_wording(client) == {"round": "", "unique": "現在3人の方と対戦済み"}
    undo = client.post("/api/control/undo-match", json={"expected_revision": second["revision"]})
    assert undo.is_success and not undo.json()["match_undo_available"]
    assert displayed_wording(client) == {"round": "現在2局目", "unique": "現在2人の方と対戦済み"}
    assert client.post("/api/control/undo-match", json={"expected_revision": second["revision"]}).status_code == 409


def test_wording_and_counts_persist_and_follow_the_active_video(counter_client):
    client = counter_client
    authenticate(client)
    store = client.app.state.services.persistence_service
    store.switch_video("abcdefghijk")
    add(client, "a", "Person A")
    client.post("/api/control/move-next")
    add(client, "b", "Person B")
    settings = client.get(SETTINGS).json()
    wording = {"round": "第{round}局", "unique": "<b>{unique}人</b>"}
    assert client.post(SETTINGS, json=wording).json() == wording
    for invalid in ("数字なし", "改行\n{round}", "a" * 80 + "{round}", "{unique}"):
        assert client.post(SETTINGS, json={**wording, "round": invalid}).status_code == 422
    backup = client.get("/api/control/backup").json()
    assert backup["state"]["obs_counter_settings"] == wording
    assert displayed_wording(client) == {"round": "第2局", "unique": "<b>1人</b>"}
    store.switch_video("lmnopqrstuv", carry=True)
    assert displayed_wording(client) == {"round": "第1局", "unique": "<b>0人</b>"}
    store.switch_video("abcdefghijk")
    assert displayed_wording(client) == {"round": "第2局", "unique": "<b>1人</b>"}
    assert client.post(SETTINGS, json=settings["defaults"]).is_success
    assert displayed_wording(client) == {"round": "現在2局目", "unique": "現在1人の方と対戦済み"}
    revision = client.get("/api/state").json()["revision"]
    assert client.post("/api/control/restore", json={"backup": backup, "expected_revision": revision}).is_success
    assert displayed_wording(client) == {"round": "第2局", "unique": "<b>1人</b>"}
    del backup["state"]["obs_counter_settings"]
    revision = client.get("/api/state").json()["revision"]
    assert client.post("/api/control/restore", json={"backup": backup, "expected_revision": revision}).is_success
    assert displayed_wording(client) == {"round": "現在2局目", "unique": "現在1人の方と対戦済み"}


def test_counter_appearance_follows_saved_queue_appearance(counter_client):
    client = counter_client
    authenticate(client)
    add(client, "a", "Participant name")
    wording = displayed_wording(client)
    saved = {
        "font_size": 52,
        "text_color": "#26e7bf",
        "background_color": "#543210",
        "background_transparency": 35,
        "auto_fit_font": False,
        "text_bold": False,
        "text_shadow": False,
        "fonts": {"all": "gothic", "obs_all": "meiryo", "summary": "mincho"},
    }
    payload = {**saved, "fonts": {**saved["fonts"], "ui_body": "sans", "now_names": "serif"}}
    assert client.post("/api/settings/overlay", json=payload).is_success
    client.headers.pop("Authorization")
    assert client.get(DISPLAY).json() == {**wording, "appearance": saved}
    assert client.get("/api/overlay-state").json()["appearance"]["fonts"]["summary"] == saved["fonts"]["summary"]
    authenticate(client)
    assert client.post("/api/settings/overlay", json={"name_mode": "youtube"}).is_success
    assert client.get(DISPLAY).json()["appearance"] == {
        "font_size": 28,
        "text_color": "#ffffff",
        "background_color": "#000000",
        "background_transparency": 100,
        "auto_fit_font": True,
        "text_bold": True,
        "text_shadow": True,
        "fonts": {"all": "default", "obs_all": None, "summary": None},
    }
