import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.schemas.comment import ReceivedComment
from app.services.comment_receive_service import CommentReceiveService


def _comment(external_message_id: str | None = "m-1", message: str = "参加希望", user_key: str = "user-1") -> ReceivedComment:
    return ReceivedComment(
        source="external",
        externalMessageId=external_message_id,
        receivedAt="2026-01-01T00:00:00Z",
        displayName="視聴者A",
        userKey=user_key,
        message=message,
        badges={"owner": False, "moderator": False, "member": False},
    )


def test_receive_first_comment_is_not_duplicate():
    logs: list[str] = []
    service = CommentReceiveService(log_writer=logs.append)

    result = service.receive(_comment())

    assert result.status == "accepted"
    assert result.duplicate is False


def test_receive_same_external_message_id_marks_duplicate():
    logs: list[str] = []
    service = CommentReceiveService(log_writer=logs.append)

    first = service.receive(_comment(external_message_id="dup-1"))
    second = service.receive(_comment(external_message_id="dup-1"))

    assert first.duplicate is False
    assert second.status == "accepted"
    assert second.duplicate is True


def test_receive_without_external_message_id_is_not_deduplicated():
    logs: list[str] = []
    service = CommentReceiveService(log_writer=logs.append)

    first = service.receive(_comment(external_message_id=None))
    second = service.receive(_comment(external_message_id=None))

    assert first.duplicate is False
    assert second.duplicate is False


def test_old_external_message_id_is_forgotten_after_rotation():
    logs: list[str] = []
    service = CommentReceiveService(log_writer=logs.append, max_recent_ids=2)

    service.receive(_comment(external_message_id="id-1"))
    service.receive(_comment(external_message_id="id-2"))
    service.receive(_comment(external_message_id="id-3"))

    replay = service.receive(_comment(external_message_id="id-1"))

    assert replay.duplicate is False


def test_logs_do_not_include_message_external_message_id_user_key():
    logs: list[str] = []
    service = CommentReceiveService(log_writer=logs.append)

    service.receive(_comment(external_message_id="sensitive-id", message="機密コメント本文", user_key="sensitive-user"))
    service.receive(_comment(external_message_id="sensitive-id", message="機密コメント本文", user_key="sensitive-user"))

    combined = "\n".join(logs)
    assert "機密コメント本文" not in combined
    assert "sensitive-id" not in combined
    assert "sensitive-user" not in combined
    assert "source=external" in combined
    assert "display_name=視聴者A" in combined
