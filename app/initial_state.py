from copy import deepcopy

INITIAL_STATE = {
    "total_match_count": 0,
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
    "user_action_locks": {},
    "participation_counts": {},
    "logs": ["モックを初期化しました"],
}

TEST_USERS = [
    {"display_name": "テスト参加者1", "participation_count": 0},
    {"display_name": "テスト参加者2", "participation_count": 1},
    {"display_name": "テスト参加者3", "participation_count": 2},
    {"display_name": "長い名前のテスト参加者サンプル", "participation_count": 0},
]


def initial_state(*, desktop: bool = False) -> dict:
    state = deepcopy(INITIAL_STATE)
    if desktop:
        state.update(current=[], waiting=[], logs=["待機列を初期化しました"])
    return state
