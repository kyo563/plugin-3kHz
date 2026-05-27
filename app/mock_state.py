from __future__ import annotations

from app.services.overlay_state_service import OverlayStateService
from app.services.queue_service import GROUP_SIZE, OPEN_SLOT_LABEL, QueueService
from app.services.sqlite_persistence_service import SQLitePersistenceService

INITIAL_STATE = {
    "is_open": True,
    "priority_mode": True,
    "cooldown_seconds": 40,
    "current": [
        {"user_id": "u1", "display_name": "Aさん", "participation_count": 1},
        {"user_id": "u2", "display_name": "Bさん", "participation_count": 2},
    ],
    "waiting": [
        {"user_id": "u3", "display_name": "Cさん", "participation_count": 0},
        {"user_id": "u4", "display_name": "Dさん", "participation_count": 1},
        {
            "user_id": "u5",
            "display_name": "とても長い名前の参加希望者サンプルさん",
            "participation_count": 0,
        },
        {"user_id": "u6", "display_name": "Eさん", "participation_count": 3},
    ],
    "show_declared_player_name_on_overlay": False,
    "logs": ["モックを初期化しました"],
}

TEST_USERS = [
    {"display_name": "テスト参加者1", "participation_count": 0},
    {"display_name": "テスト参加者2", "participation_count": 1},
    {"display_name": "テスト参加者3", "participation_count": 2},
    {"display_name": "長い名前のテスト参加者サンプル", "participation_count": 0},
]

_add_counter = 0
_queue_service = QueueService(group_size=GROUP_SIZE, open_slot_label=OPEN_SLOT_LABEL)
_overlay_service = OverlayStateService()
_persistence_service = SQLitePersistenceService(initial_state=INITIAL_STATE)


def reset_state() -> None:
    global _add_counter
    _persistence_service.reset_state()
    _add_counter = 0


def set_mock_state_for_test(new_state: dict) -> None:
    _persistence_service.set_state(new_state)


def _build_next_user() -> dict:
    global _add_counter
    template = TEST_USERS[_add_counter % len(TEST_USERS)]
    _add_counter += 1
    return {
        "user_id": f"test{_add_counter}",
        "display_name": template["display_name"],
        "participation_count": template["participation_count"],
    }


def add_mock_user() -> None:
    _persistence_service.mutate_state(lambda app_state: _queue_service.add_user(app_state, _build_next_user()))


def cancel_mock_user() -> None:
    _persistence_service.mutate_state(_queue_service.cancel_user)


def move_next() -> None:
    _persistence_service.mutate_state(_queue_service.move_next)


def toggle_open() -> None:
    _persistence_service.mutate_state(_queue_service.toggle_open)


def toggle_priority() -> None:
    _persistence_service.mutate_state(_queue_service.toggle_priority)


def build_view_state() -> dict:
    return _queue_service.build_view_state(_persistence_service.get_state())


def build_overlay_state() -> dict:
    return _overlay_service.build_overlay_state(build_view_state())


def toggle_overlay_player_name() -> None:
    def _toggle(state: dict) -> None:
        state["show_declared_player_name_on_overlay"] = not state.get("show_declared_player_name_on_overlay", False)
    _persistence_service.mutate_state(_toggle)


def add_log(message: str) -> None:
    def _append_log(app_state: dict) -> None:
        app_state.setdefault("logs", []).append(message)

    _persistence_service.mutate_state(_append_log)
