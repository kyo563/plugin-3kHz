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
    assert result.command == "join"
    assert result.declared_player_name is None


def test_receive_same_external_message_id_marks_duplicate():
    logs: list[str] = []
    service = CommentReceiveService(log_writer=logs.append)

    first = service.receive(_comment(external_message_id="dup-1"))
    second = service.receive(_comment(external_message_id="dup-1"))

    assert first.duplicate is False
    assert second.status == "accepted"
    assert second.duplicate is True
    assert second.command == "ignore"
    assert second.declared_player_name is None


def test_receive_without_external_message_id_is_not_deduplicated():
    logs: list[str] = []
    service = CommentReceiveService(log_writer=logs.append)

    first = service.receive(_comment(external_message_id=None))
    second = service.receive(_comment(external_message_id=None))

    assert first.duplicate is False
    assert second.duplicate is False
    assert second.command == "join"
    assert second.declared_player_name is None


def test_old_external_message_id_is_forgotten_after_rotation():
    logs: list[str] = []
    service = CommentReceiveService(log_writer=logs.append, max_recent_ids=2)

    service.receive(_comment(external_message_id="id-1"))
    service.receive(_comment(external_message_id="id-2"))
    service.receive(_comment(external_message_id="id-3"))

    replay = service.receive(_comment(external_message_id="id-1"))

    assert replay.duplicate is False
    assert replay.command == "join"
    assert replay.declared_player_name is None


def test_logs_do_not_include_message_external_message_id_user_key():
    logs: list[str] = []
    service = CommentReceiveService(log_writer=logs.append)

    service.receive(_comment(external_message_id="sensitive-id", message="参加希望 名前 たなかたろう", user_key="sensitive-user"))
    service.receive(_comment(external_message_id="sensitive-id", message="参加希望 名前 たなかたろう", user_key="sensitive-user"))

    combined = "\n".join(logs)
    assert "たなかたろう" not in combined
    assert "sensitive-id" not in combined
    assert "sensitive-user" not in combined
    assert "source=external" in combined
    assert "display_name=視聴者A" in combined
    assert "declared_player_name=yes" in combined
    assert "重複コメントを除外" in combined


def test_receive_parses_declared_player_name_only_for_join():
    logs: list[str] = []
    service = CommentReceiveService(log_writer=logs.append)

    join_with_name = service.receive(_comment(external_message_id="name-1", message="参加希望 名前 たなかたろう"))
    join_without_name = service.receive(_comment(external_message_id="name-2", message="参加希望"))
    ignore = service.receive(_comment(external_message_id="name-3", message="参加希望者 名前 たなかたろう"))
    ignore_order = service.receive(_comment(external_message_id="name-4", message="参加希望順 名前 たなかたろう"))
    cancel = service.receive(_comment(external_message_id="name-5", message="参加辞退 名前 たなかたろう"))
    cancel2 = service.receive(_comment(external_message_id="name-6", message="参加を辞退 名前 たなかたろう"))

    assert join_with_name.command == "join"
    assert join_with_name.declared_player_name == "たなかたろう"
    assert join_without_name.command == "join"
    assert join_without_name.declared_player_name is None
    assert ignore.command == "ignore"
    assert ignore.declared_player_name is None
    assert ignore_order.command == "ignore"
    assert ignore_order.declared_player_name is None
    assert cancel.command == "cancel"
    assert cancel.declared_player_name is None
    assert cancel2.command == "cancel"
    assert cancel2.declared_player_name is None
