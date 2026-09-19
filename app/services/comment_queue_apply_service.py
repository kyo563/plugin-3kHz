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
            if result.command in {"join", "cancel"} and any(u.get("user_id") == user_id for u in state["current"]):
                state.setdefault("logs", []).append(f"{comment.display_name} はNOW参加中のため参加・辞退コメントを無視しました。変更は管理画面から行ってください")
                state["logs"] = state["logs"][-30:]
                return
            if result.command == "join" and not state["is_open"]:
                state.setdefault("logs", []).append("受付終了中の参加希望")
                state["logs"] = state["logs"][-30:]
                return
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
                saved_counts = state.get("participation_counts") or {}
                try:
                    saved_participation_count = int(saved_counts.get(user_id, 0))
                except (TypeError, ValueError):
                    saved_participation_count = 0
                if saved_participation_count < 0:
                    saved_participation_count = 0
                from app.services.declared_player_name_parser import DeclaredPlayerNameParser
                quoted = DeclaredPlayerNameParser().parse_quoted(comment.message, state.get("command_settings", {}).get("join"))
                saved_names = state.setdefault("comment_names", {})
                # Retain already-declared names from older versions when distinguishable
                # from the automatic YouTube nickname.
                existing = next((u for u in state["current"] + state["waiting"] if u.get("user_id") == user_id), None)
                prior = existing.get("declared_player_name") if existing else None
                if prior and prior != (existing.get("youtube_nickname") or existing.get("display_name")) and user_id not in saved_names:
                    if len(saved_names) < 20000:
                        saved_names[user_id] = prior
                if quoted and user_id not in saved_names:
                    if len(saved_names) >= 20000:
                        state.setdefault("logs", []).append("コメント指定名の保存上限です。管理画面から追加してください")
                        state["logs"] = state["logs"][-30:]
                        return
                    saved_names[user_id] = quoted
                changed = self._queue_service.join_or_requeue_user_by_id(
                    state,
                    {
                        "user_id": user_id,
                        "display_name": comment.display_name,
                        "declared_player_name": state.get("name_overrides", {}).get(user_id) or saved_names.get(user_id) or result.declared_player_name or (
                            (comment.youtube_nickname or comment.display_name) if comment.youtube_handle or comment.source.lower() == 'youtube'
                            else result.declared_player_name),
                        "youtube_handle": comment.youtube_handle,
                        "avatar_url": comment.avatar_url,
                        "youtube_nickname": comment.youtube_nickname or (comment.display_name if comment.youtube_handle or comment.source.lower() == 'youtube' else None),
                        "participation_count": saved_participation_count,
                    },
                )
            elif result.command == "cancel":
                changed = self._queue_service.cancel_user_by_id(state, user_id)

            if changed:
                self._cooldown_service.mark_changed(state, user_id)

        self._persistence_service.mutate_state(_apply)
