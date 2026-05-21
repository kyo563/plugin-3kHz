from __future__ import annotations

from copy import deepcopy

GROUP_SIZE = 3
OPEN_SLOT_LABEL = "参加者募集中"

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
        {"user_id": "u5", "display_name": "とても長い名前の参加希望者サンプルさん", "participation_count": 0},
        {"user_id": "u6", "display_name": "Eさん", "participation_count": 3},
    ],
    "logs": ["モックを初期化しました"],
}

TEST_USERS = [
    {"display_name": "テスト参加者1", "participation_count": 0},
    {"display_name": "テスト参加者2", "participation_count": 1},
    {"display_name": "テスト参加者3", "participation_count": 2},
    {"display_name": "長い名前のテスト参加者サンプル", "participation_count": 0},
]

state = deepcopy(INITIAL_STATE)
_add_counter = 0


def _log(message: str) -> None:
    state["logs"].append(message)
    state["logs"] = state["logs"][-30:]


def reset_state() -> None:
    global state, _add_counter
    state = deepcopy(INITIAL_STATE)
    _add_counter = 0


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
    if not state["is_open"]:
        _log("受付終了中の参加希望")
        return

    user = _build_next_user()
    if len(state["current"]) < GROUP_SIZE:
        state["current"].append(user)
        _log(f"{user['display_name']} をNOWへ補充しました")
        return

    if state["priority_mode"] and len(state["waiting"]) >= GROUP_SIZE:
        next_slice = state["waiting"][:GROUP_SIZE]
        candidates = [
            (index, queued_user)
            for index, queued_user in enumerate(next_slice)
            if queued_user["participation_count"] > user["participation_count"]
        ]

        if candidates:
            demote_index, demoted = candidates[-1]
            new_next = [
                queued_user
                for index, queued_user in enumerate(next_slice)
                if index != demote_index
            ]
            new_next.append(user)
            state["waiting"] = new_next + [demoted] + state["waiting"][GROUP_SIZE:]
            _log(f"低消化優先: {user['display_name']} をNEXTへ、{demoted['display_name']} をQUEUE先頭へ")
            return

    state["waiting"].append(user)
    _log(f"{user['display_name']} を待機列へ追加しました")


def cancel_mock_user() -> None:
    if state["waiting"]:
        removed = state["waiting"].pop(0)
        _log(f"{removed['display_name']} を取消しました")
        return
    _log("取消対象がいません")


def move_next() -> None:
    for user in state["current"]:
        user["participation_count"] += 1

    next_users = state["waiting"][:GROUP_SIZE]
    state["waiting"] = state["waiting"][GROUP_SIZE:]
    state["current"] = next_users
    _log("次へ進めるを実行しました")


def toggle_open() -> None:
    state["is_open"] = not state["is_open"]
    _log("受付状態を切り替えました")


def toggle_priority() -> None:
    state["priority_mode"] = not state["priority_mode"]
    _log("低消化回数優先モードを切り替えました")


def build_view_state() -> dict:
    current = list(state["current"])
    now_with_placeholder = current + [
        {"display_name": OPEN_SLOT_LABEL, "is_placeholder": True}
        for _ in range(max(0, GROUP_SIZE - len(current)))
    ]
    waiting = state["waiting"]
    next_users = waiting[:GROUP_SIZE]
    queue_users = waiting[GROUP_SIZE:]

    return {
        **state,
        "now_view": now_with_placeholder,
        "next_view": next_users,
        "queue_view": queue_users,
        "waiting_count": len(waiting),
        "waiting_group_count": (len(waiting) + GROUP_SIZE - 1) // GROUP_SIZE,
    }
