from __future__ import annotations

from copy import deepcopy

GROUP_SIZE = 3
OPEN_SLOT_LABEL = "参加者募集中"


class QueueService:
    def __init__(self, group_size: int = GROUP_SIZE, open_slot_label: str = OPEN_SLOT_LABEL):
        self.group_size = group_size
        self.open_slot_label = open_slot_label

    def _log(self, state: dict, message: str) -> None:
        state["logs"].append(message)
        state["logs"] = state["logs"][-30:]

    def _pad_open_slots(self, users: list[dict]) -> list[dict]:
        return users + [
            {"display_name": self.open_slot_label, "is_placeholder": True}
            for _ in range(max(0, self.group_size - len(users)))
        ]

    def add_user(self, state: dict, user: dict) -> None:
        if not state["is_open"]:
            self._log(state, "受付終了中の参加希望")
            return

        if len(state["current"]) < self.group_size:
            state["current"].append(user)
            self._log(state, f"{user['display_name']} をNOWへ補充しました")
            return

        if state["priority_mode"] and len(state["waiting"]) >= self.group_size:
            next_slice = state["waiting"][: self.group_size]
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
                state["waiting"] = new_next + [demoted] + state["waiting"][self.group_size :]
                self._log(
                    state,
                    f"低消化優先: {user['display_name']} をNEXTへ、"
                    f"{demoted['display_name']} をQUEUE先頭へ",
                )
                return

        state["waiting"].append(user)
        self._log(state, f"{user['display_name']} を待機列へ追加しました")

    def cancel_user(self, state: dict) -> None:
        if state["waiting"]:
            removed = state["waiting"].pop(0)
            self._log(state, f"{removed['display_name']} を取消しました")
            return
        self._log(state, "取消対象がいません")

    def cancel_user_by_id(self, state: dict, user_id: str) -> None:
        for section in ("waiting", "current"):
            users = state[section]
            for index, user in enumerate(users):
                if user.get("user_id") == user_id:
                    removed = users.pop(index)
                    self._log(state, f"{removed['display_name']} を取消しました")
                    return
        self._log(state, "取消対象がいません")

    def move_next(self, state: dict) -> None:
        for user in state["current"]:
            user["participation_count"] += 1

        next_users = state["waiting"][: self.group_size]
        state["waiting"] = state["waiting"][self.group_size :]
        state["current"] = next_users
        self._log(state, "次へ進めるを実行しました")

    def toggle_open(self, state: dict) -> None:
        state["is_open"] = not state["is_open"]
        self._log(state, "受付状態を切り替えました")

    def toggle_priority(self, state: dict) -> None:
        state["priority_mode"] = not state["priority_mode"]
        self._log(state, "低消化回数優先モードを切り替えました")

    def build_view_state(self, state: dict) -> dict:
        snapshot = deepcopy(state)
        current = list(snapshot["current"])
        waiting = snapshot["waiting"]

        next_users = waiting[: self.group_size]
        queue_users = waiting[self.group_size :]

        return {
            **snapshot,
            "now_view": self._pad_open_slots(current),
            "next_view": self._pad_open_slots(next_users),
            "queue_view": queue_users,
            "total_waiting_count": len(waiting),
            "total_waiting_group_count": (len(waiting) + self.group_size - 1) // self.group_size,
            "queue_count": len(queue_users),
            "queue_group_count": (len(queue_users) + self.group_size - 1) // self.group_size,
        }
