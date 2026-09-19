from fastapi import APIRouter, Request

from app.dependencies import get_services
from app.schemas.comment import CommentReceiveResult, ReceivedComment

router = APIRouter()
development_router = APIRouter()


@router.post("/api/comments/receive", response_model=CommentReceiveResult)
def receive_external_comment(comment: ReceivedComment, request: Request = None) -> CommentReceiveResult:
    services = get_services(request)
    return services.receive_comment(comment)


@development_router.post("/api/comments/manual", response_model=CommentReceiveResult)
def receive_manual_comment(comment: ReceivedComment, request: Request = None) -> CommentReceiveResult:
    services = get_services(request)
    return services.receive_comment(comment, manual=True)
