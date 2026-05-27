from fastapi import APIRouter

from app import mock_state
from app.schemas.comment import CommentReceiveResult, ReceivedComment
from app.services.comment_receive_service import CommentReceiveService
from app.services.external_chat_provider import ExternalChatProvider
from app.services.manual_test_provider import ManualTestProvider

router = APIRouter()
_external_provider = ExternalChatProvider()
_manual_provider = ManualTestProvider()
_receive_service = CommentReceiveService(log_writer=mock_state.add_log)


@router.post("/api/comments/receive", response_model=CommentReceiveResult)
def receive_external_comment(comment: ReceivedComment) -> CommentReceiveResult:
    received = _external_provider.receive(comment)
    return _receive_service.receive(received)


@router.post("/api/comments/manual", response_model=CommentReceiveResult)
def receive_manual_comment(comment: ReceivedComment) -> CommentReceiveResult:
    received = _manual_provider.receive(comment)
    return _receive_service.receive(received)
