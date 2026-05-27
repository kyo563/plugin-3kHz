from __future__ import annotations

from app.schemas.comment import CommentReceiveResult, ReceivedComment
from app.services.persistence_service import PersistenceService
from app.services.queue_service import QueueService
from app.services.user_identity_service import UserIdentityService


class CommentQueueApplyService:
    def __init__(
        self,
        persistence_service: PersistenceService,
        queue_service: QueueService,
        user_identity_service: UserIdentityService,
    ) -> None:
        self._persistence_service = persistence_service
        self._queue_service = queue_service
        self._user_identity_service = user_identity_service

    def apply(self, comment: ReceivedComment, result: CommentReceiveResult) -> None:
        if result.duplicate or result.command == "ignore":
            return

        user_id = self._user_identity_service.build_comment_user_id(comment.source, comment.user_key)

        def _apply(state: dict) -> None:
            if result.command == "join":
                self._queue_service.add_user(
                    state,
                    {
                        "user_id": user_id,
                        "display_name": comment.display_name,
                        "declared_player_name": result.declared_player_name,
                        "participation_count": 0,
                    },
                )
                return

            if result.command == "cancel":
                self._queue_service.cancel_user_by_id(state, user_id)

        self._persistence_service.mutate_state(_apply)
