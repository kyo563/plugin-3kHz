from __future__ import annotations

from app.schemas.comment import CommentReceiveResult, ReceivedComment
from app.services.persistence_service import PersistenceService
from app.services.queue_service import QueueService
from app.services.state_change_cooldown_service import StateChangeCooldownService
from app.services.user_identity_service import UserIdentityService


class CommentQueueApplyService:
    def __init__(
        self,
        persistence_service: PersistenceService,
        queue_service: QueueService,
        user_identity_service: UserIdentityService,
        cooldown_service: StateChangeCooldownService | None = None,
    ) -> None:
        self._persistence_service = persistence_service
        self._queue_service = queue_service
        self._user_identity_service = user_identity_service
        self._cooldown_service = cooldown_service or StateChangeCooldownService()

    def apply(self, comment: ReceivedComment, result: CommentReceiveResult) -> None:
        if result.duplicate or result.command == "ignore":
            return

        user_id = self._user_identity_service.build_comment_user_id(comment.source, comment.user_key)

        def _apply(state: dict) -> None:
            self._cooldown_service.clear_expired(state)

            if result.command == "join" and self._cooldown_service.is_locked(state, user_id):
                state.setdefault("logs", []).append(f"{comment.display_name} は状態変更ロック中のため参加希望を無視しました")
                state["logs"] = state["logs"][-30:]
                return

            if result.command == "cancel" and self._cooldown_service.is_locked(state, user_id):
                state.setdefault("logs", []).append(f"{comment.display_name} は状態変更ロック中のため参加辞退を無視しました")
                state["logs"] = state["logs"][-30:]
                return

            changed = False
            if result.command == "join":
                changed = self._queue_service.join_or_requeue_user_by_id(
                    state,
                    {
                        "user_id": user_id,
                        "display_name": comment.display_name,
                        "declared_player_name": result.declared_player_name,
                        "participation_count": 0,
                    },
                )
            elif result.command == "cancel":
                changed = self._queue_service.cancel_user_by_id(state, user_id)

            if changed:
                self._cooldown_service.mark_changed(state, user_id)

        self._persistence_service.mutate_state(_apply)
