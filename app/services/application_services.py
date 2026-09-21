from __future__ import annotations

from threading import RLock

from app.initial_state import TEST_USERS, initial_state
from app.services.overlay_state_service import OverlayStateService
from app.services.queue_service import GROUP_SIZE, OPEN_SLOT_LABEL, QueueService
from app.services.sqlite_persistence_service import SQLitePersistenceService
from app.services.comment_receive_service import CommentReceiveService
from app.services.comment_queue_apply_service import CommentQueueApplyService
from app.services.user_identity_service import UserIdentityService
from app.services.external_chat_provider import ExternalChatProvider
from app.services.manual_test_provider import ManualTestProvider


class ApplicationServices:
    """One service graph per running application, created after the DB lock."""

    def __init__(self, *, db_path: str | None = None, desktop: bool = False):
        self.comment_lock = RLock()
        self.add_counter = 0
        self.queue_service = QueueService(group_size=GROUP_SIZE, open_slot_label=OPEN_SLOT_LABEL)
        self.overlay_service = OverlayStateService()
        self.persistence_service = SQLitePersistenceService(initial_state(desktop=desktop), db_path)
        self.external_provider = ExternalChatProvider()
        self.manual_provider = ManualTestProvider()
        self.receive_service = CommentReceiveService(log_writer=self.add_log)
        self.apply_service = CommentQueueApplyService(
            self.persistence_service, self.queue_service, UserIdentityService()
        )

    def reset_state(self) -> None:
        self.persistence_service.reset_state()
        self.add_counter = 0

    def set_mock_state_for_test(self, new_state: dict) -> None:
        self.persistence_service.set_state(new_state)

    def _build_next_user(self) -> dict:
        template = TEST_USERS[self.add_counter % len(TEST_USERS)]
        self.add_counter += 1
        return {
            "user_id": f"test{self.add_counter}",
            "display_name": template["display_name"],
            "participation_count": template["participation_count"],
        }

    def add_mock_user(self) -> None:
        def _add(app_state: dict) -> None:
            if not app_state["is_open"]:
                app_state.setdefault("logs", []).append("受付終了中の参加希望")
                app_state["logs"] = app_state["logs"][-30:]
                return
            self.queue_service.add_user(app_state, self._build_next_user())

        self.persistence_service.mutate_state(_add)

    def cancel_mock_user(self) -> None:
        self.persistence_service.manual_mutate(self.queue_service.cancel_user)

    def move_next(self) -> None:
        self.persistence_service.manual_mutate(self.queue_service.move_next)
        if getattr(self, 'bot', None):
            self.bot.announce()

    def toggle_open(self) -> None:
        self.persistence_service.manual_mutate(self.queue_service.toggle_open)

    def toggle_priority(self) -> None:
        self.persistence_service.manual_mutate(self.queue_service.toggle_priority)

    def build_view_state(self) -> dict:
        state, revision, undo = self.persistence_service.snapshot()
        return {**self.queue_service.build_view_state(state), "revision": revision, "undo_available": undo}

    def build_overlay_state(self) -> dict:
        return self.overlay_service.build_overlay_state(self.build_view_state())

    def toggle_overlay_player_name(self) -> None:
        def _toggle(state: dict) -> None:
            state["show_declared_player_name_on_overlay"] = not state.get("show_declared_player_name_on_overlay", False)
        self.persistence_service.mutate_state(_toggle)

    def add_log(self, message: str) -> None:
        def _append_log(app_state: dict) -> None:
            app_state.setdefault("logs", []).append(message)

        self.persistence_service.mutate_state(_append_log)

    def receive_comment(self, comment, *, manual=False):
        if getattr(self, 'bot', None) and self.bot.is_self(comment):
            from app.schemas.comment import CommentReceiveResult
            return CommentReceiveResult(status='ignored_bot', duplicate=False, command='ignore')
        with self.comment_lock, self.persistence_service.serialized():
            provider = self.manual_provider if manual else self.external_provider
            received = provider.receive(comment)
            result = self.receive_service.receive(received, self.persistence_service.get_state()["command_settings"])
            self.apply_service.apply(received, result)
            return result
