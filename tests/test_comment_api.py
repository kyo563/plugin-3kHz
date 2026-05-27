import os
import sqlite3
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

sys.path.append(str(Path(__file__).resolve().parents[1]))
os.environ["WAITING_LIST_DB_PATH"] = str(Path(__file__).resolve().parent / "tmp_comment_api.sqlite3")

from app import mock_state
from app.routes.comment_api import receive_external_comment, receive_manual_comment
from app.routes.control_api import api_state
from app.routes.overlay_api import api_overlay_state
from app.schemas.comment import ReceivedComment
from app.services.user_identity_service import UserIdentityService


def setup_function():
    mock_state.reset_state()


def _payload(external_message_id: str | None = None, source: str = "external") -> dict:
    if external_message_id is None:
        external_message_id = f"msg-{uuid4()}"
    return {
        "source": source,
        "externalMessageId": external_message_id,
        "receivedAt": "2026-01-01T00:00:00Z",
        "displayName": "視聴者テスト",
        "userKey": "user-raw-1",
        "message": "参加希望です",
        "badges": {"owner": False, "moderator": False, "member": True},
    }


def _build_comment(**kwargs) -> ReceivedComment:
    return ReceivedComment(**_payload(**kwargs))


def test_receive_endpoint_accepts_valid_payload():
    result = receive_external_comment(_build_comment())
    assert result.model_dump(by_alias=True) == {"status": "accepted", "duplicate": False, "command": "join", "declared_player_name": None}


def test_manual_endpoint_accepts_valid_payload_and_forces_manual_source():
    result = receive_manual_comment(_build_comment(source="external"))
    assert result.model_dump(by_alias=True) == {"status": "accepted", "duplicate": False, "command": "join", "declared_player_name": None}

    state = api_state()
    assert any("source=manual" in log for log in state["logs"])


def test_duplicate_external_message_id_returns_duplicate_true_on_second_request():
    first = receive_external_comment(_build_comment(external_message_id="dup-1"))
    second = receive_external_comment(_build_comment(external_message_id="dup-1"))

    assert first.model_dump() == {"status": "accepted", "duplicate": False, "command": "join", "declared_player_name": None}
    assert second.model_dump() == {"status": "accepted", "duplicate": True, "command": "ignore", "declared_player_name": None}


def test_invalid_payload_is_rejected_by_schema_validation():
    bad = _payload()
    bad.pop("displayName")

    with pytest.raises(ValidationError):
        ReceivedComment(**bad)


def test_receive_comment_reflects_queue_and_overlay_is_minimal():
    before = api_state()

    receive_external_comment(_build_comment(external_message_id="state-1"))

    after = api_state()
    overlay = api_overlay_state()

    before_total = len(before["current"]) + len(before["waiting"])
    after_total = len(after["current"]) + len(after["waiting"])
    assert after_total == before_total + 1
    assert set(overlay.keys()) == {"is_open", "now_view", "next_view", "queue_count", "queue_group_count"}
    assert "logs" not in overlay
    for section in ("now_view", "next_view"):
        for user in overlay[section]:
            assert "user_id" not in user
            assert "participation_count" not in user


def test_operation_logs_do_not_store_message_external_message_id_or_user_key():
    db_path = mock_state._persistence_service._db_path
    payload = _payload(external_message_id="secret-external-id")
    payload["message"] = "参加希望 名前 たなかたろう"
    payload["userKey"] = "secret-user-key"
    comment = ReceivedComment(**payload)

    receive_external_comment(comment)
    receive_external_comment(comment)

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute("SELECT message FROM operation_logs ORDER BY id").fetchall()

    logs = "\n".join(message for (message,) in rows)
    assert "たなかたろう" not in logs
    assert "secret-external-id" not in logs
    assert "secret-user-key" not in logs
    assert "コメント受信: source=external, display_name=視聴者テスト, command=join, declared_player_name=yes" in logs
    assert "重複コメントを除外: source=external, display_name=視聴者テスト" in logs


def test_receive_endpoint_returns_join_cancel_ignore_commands():
    join_payload = _payload(external_message_id="cmd-join")
    join_payload["message"] = "こんにちは参加希望"
    assert receive_external_comment(ReceivedComment(**join_payload)).model_dump() == {
        "status": "accepted",
        "duplicate": False,
        "command": "join",
        "declared_player_name": None,
    }

    cancel_payload = _payload(external_message_id="cmd-cancel")
    cancel_payload["message"] = "参加を辞退します"
    assert receive_external_comment(ReceivedComment(**cancel_payload)).model_dump() == {
        "status": "accepted",
        "duplicate": False,
        "command": "cancel",
        "declared_player_name": None,
    }

    ignore_payload = _payload(external_message_id="cmd-ignore")
    ignore_payload["message"] = "参加したいです"
    assert receive_external_comment(ReceivedComment(**ignore_payload)).model_dump() == {
        "status": "accepted",
        "duplicate": False,
        "command": "ignore",
        "declared_player_name": None,
    }


def test_receive_and_manual_endpoint_return_declared_player_name():
    payload = _payload(external_message_id="name-api-1")
    payload["message"] = "参加希望 名前 たなかたろう"
    receive_result = receive_external_comment(ReceivedComment(**payload)).model_dump()
    assert receive_result["command"] == "join"
    assert receive_result["declared_player_name"] == "たなかたろう"

    manual_payload = _payload(external_message_id="name-api-2", source="external")
    manual_payload["message"] = "こんにちは参加希望 名前 たなかたろう"
    manual_result = receive_manual_comment(ReceivedComment(**manual_payload)).model_dump()
    assert manual_result["command"] == "join"
    assert manual_result["declared_player_name"] == "たなかたろう"


def test_receive_cancel_same_user_is_blocked_within_cooldown():
    join = _payload(external_message_id="join-1"); join["message"]="参加希望"
    cancel = _payload(external_message_id="cancel-1"); cancel["message"]="参加辞退"
    receive_external_comment(ReceivedComment(**join))
    before = api_state()
    receive_external_comment(ReceivedComment(**cancel))
    after = api_state()
    assert len(after["current"]) + len(after["waiting"]) == len(before["current"]) + len(before["waiting"])


def test_rejoin_within_cooldown_is_not_applied_for_receive_and_manual():
    p1 = _payload(external_message_id="rj-1", source="external")
    p1["userKey"] = "same-user"
    p1["displayName"] = "Aさん"
    p1["message"] = "参加希望"
    receive_external_comment(ReceivedComment(**p1))

    p2 = _payload(external_message_id="rj-2", source="external")
    p2["userKey"] = "same-user"
    p2["displayName"] = "Aさん改"
    p2["message"] = "参加希望"
    receive_external_comment(ReceivedComment(**p2))

    state = api_state()
    assert all(u.get("display_name") != "Aさん改" for u in (state["current"] + state["waiting"]))

    m1 = _payload(external_message_id="mrj-1", source="manual")
    m1["userKey"] = "manual-user"
    m1["displayName"] = "Mさん"
    m1["message"] = "参加希望"
    receive_manual_comment(ReceivedComment(**m1))

    m2 = _payload(external_message_id="mrj-2", source="manual")
    m2["userKey"] = "manual-user"
    m2["displayName"] = "Mさん改"
    m2["message"] = "参加希望"
    receive_manual_comment(ReceivedComment(**m2))

    state2 = api_state()
    assert all(u.get("display_name") != "Mさん改" for u in (state2["current"] + state2["waiting"]))


def test_rejoin_with_declared_player_name_during_cooldown_does_not_update_state():
    p1 = _payload(external_message_id="name-upd-1")
    p1["userKey"] = "name-user"
    p1["displayName"] = "Aさん"
    p1["message"] = "参加希望"
    receive_external_comment(ReceivedComment(**p1))

    p2 = _payload(external_message_id="name-upd-2")
    p2["userKey"] = "name-user"
    p2["displayName"] = "Aさん"
    p2["message"] = "参加希望 名前 たなかたろう"
    receive_external_comment(ReceivedComment(**p2))

    state = api_state()
    target = [u for u in (state["current"] + state["waiting"]) if u.get("display_name") == "Aさん"][-1]
    assert target["declared_player_name"] is None


def test_ignore_messages_do_not_join_for_join_excludes():
    payloads = ["参加希望者", "参加希望順"]
    before = api_state()
    before_total = len(before["current"]) + len(before["waiting"])
    for i, msg in enumerate(payloads):
        p = _payload(external_message_id=f"ig-{i}")
        p["message"] = msg
        result = receive_external_comment(ReceivedComment(**p)).model_dump()
        assert result["command"] == "ignore"
    after = api_state()
    after_total = len(after["current"]) + len(after["waiting"])
    assert after_total == before_total


def test_join_uses_saved_participation_count_and_move_next_persists_it():
    identity = UserIdentityService()
    user_id = identity.build_comment_user_id("external", "user-raw-1")
    state = mock_state._persistence_service.get_state()
    state["current"] = []
    state["waiting"] = []
    state["participation_counts"] = {user_id: 2}
    mock_state._persistence_service.set_state(state)

    receive_external_comment(_build_comment(external_message_id="pc-1"))
    joined = api_state()
    user = (joined["current"] + joined["waiting"])[0]
    assert user["participation_count"] == 2

    mock_state.move_next()
    after = mock_state._persistence_service.get_state()
    assert after["participation_counts"][user_id] == 3
