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
    assert result.model_dump(by_alias=True) == {"status": "accepted", "duplicate": False, "command": "join"}


def test_manual_endpoint_accepts_valid_payload_and_forces_manual_source():
    result = receive_manual_comment(_build_comment(source="external"))
    assert result.model_dump(by_alias=True) == {"status": "accepted", "duplicate": False, "command": "join"}

    state = api_state()
    assert any("source=manual" in log for log in state["logs"])


def test_duplicate_external_message_id_returns_duplicate_true_on_second_request():
    first = receive_external_comment(_build_comment(external_message_id="dup-1"))
    second = receive_external_comment(_build_comment(external_message_id="dup-1"))

    assert first.model_dump() == {"status": "accepted", "duplicate": False, "command": "join"}
    assert second.model_dump() == {"status": "accepted", "duplicate": True, "command": "ignore"}


def test_invalid_payload_is_rejected_by_schema_validation():
    bad = _payload()
    bad.pop("displayName")

    with pytest.raises(ValidationError):
        ReceivedComment(**bad)


def test_receive_comment_does_not_change_current_or_waiting_and_overlay_is_minimal():
    before = api_state()

    receive_external_comment(_build_comment(external_message_id="state-1"))

    after = api_state()
    overlay = api_overlay_state()

    assert len(after["current"]) == len(before["current"])
    assert len(after["waiting"]) == len(before["waiting"])
    assert set(overlay.keys()) == {"is_open", "now_view", "next_view", "queue_count", "queue_group_count"}
    assert "logs" not in overlay
    for section in ("now_view", "next_view"):
        for user in overlay[section]:
            assert "user_id" not in user
            assert "participation_count" not in user


def test_operation_logs_do_not_store_message_external_message_id_or_user_key():
    db_path = mock_state._persistence_service._db_path
    payload = _payload(external_message_id="secret-external-id")
    payload["message"] = "秘密の本文"
    payload["userKey"] = "secret-user-key"
    comment = ReceivedComment(**payload)

    receive_external_comment(comment)
    receive_external_comment(comment)

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute("SELECT message FROM operation_logs ORDER BY id").fetchall()

    logs = "\n".join(message for (message,) in rows)
    assert "秘密の本文" not in logs
    assert "secret-external-id" not in logs
    assert "secret-user-key" not in logs
    assert "コメント受信: source=external, display_name=視聴者テスト, command=ignore" in logs
    assert "重複コメントを除外: source=external, display_name=視聴者テスト" in logs


def test_receive_endpoint_returns_join_cancel_ignore_commands():
    join_payload = _payload(external_message_id="cmd-join")
    join_payload["message"] = "こんにちは参加希望"
    assert receive_external_comment(ReceivedComment(**join_payload)).model_dump() == {
        "status": "accepted",
        "duplicate": False,
        "command": "join",
    }

    cancel_payload = _payload(external_message_id="cmd-cancel")
    cancel_payload["message"] = "参加を辞退します"
    assert receive_external_comment(ReceivedComment(**cancel_payload)).model_dump() == {
        "status": "accepted",
        "duplicate": False,
        "command": "cancel",
    }

    ignore_payload = _payload(external_message_id="cmd-ignore")
    ignore_payload["message"] = "参加したいです"
    assert receive_external_comment(ReceivedComment(**ignore_payload)).model_dump() == {
        "status": "accepted",
        "duplicate": False,
        "command": "ignore",
    }
