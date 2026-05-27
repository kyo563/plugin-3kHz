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

    def _find_and_remove_user(self, state: dict, user_id: str):
        for section in ("current", "waiting"):
            users = state[section]
            for index, user in enumerate(users):
                if user.get("user_id") == user_id:
                    return users.pop(index)
        return None

    def add_user(self, state: dict, user: dict) -> bool:
        if not state["is_open"]:
            self._log(state, "受付終了中の参加希望")
            return False

        if len(state["current"]) < self.group_size:
            state["current"].append(user)
            self._log(state, f"{user['display_name']} をNOWへ補充しました")
            return True

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
                return True

        state["waiting"].append(user)
        self._log(state, f"{user['display_name']} を待機列へ追加しました")
        return True

    def join_or_requeue_user_by_id(self, state: dict, user: dict) -> bool:
        existing_user = None
        for section in ("current", "waiting"):
            users = state[section]
            for index, queued_user in enumerate(users):
                if queued_user.get("user_id") == user.get("user_id"):
                    existing_user = users.pop(index)
                    break
            if existing_user is not None:
                break

        if existing_user is None:
            return self.add_user(state, user)

        if not state["is_open"]:
            state[section].insert(index, existing_user)
            self._log(state, "受付終了中の再参加希望")
            return False

        declared_player_name = user.get("declared_player_name")
        existing_count = existing_user.get("participation_count", 0)
        incoming_count = user.get("participation_count", 0)
        try:
            existing_count = int(existing_count)
        except (TypeError, ValueError):
            existing_count = 0
        try:
            incoming_count = int(incoming_count)
        except (TypeError, ValueError):
            incoming_count = 0
        merged_count = max(existing_count, incoming_count, 0)
        merged_user = {
            **existing_user,
            "display_name": user.get("display_name", existing_user.get("display_name", "")),
            "participation_count": merged_count,
        }
        if declared_player_name:
            merged_user["declared_player_name"] = declared_player_name
            self._log(state, f"{merged_user['display_name']} の申告名を更新して最後尾へ移動しました")
        else:
            self._log(state, f"{merged_user['display_name']} が再参加希望したため最後尾へ移動しました")

        state["waiting"].append(merged_user)
        return True

    def reorder_waiting(self, state: dict, ordered_user_ids: list[str]) -> None:
        waiting = list(state["waiting"])
        waiting_by_id = {
            user.get("user_id"): user
            for user in waiting
            if user.get("user_id")
        }
        used = set()
        reordered = []

        for user_id in ordered_user_ids:
            user = waiting_by_id.get(user_id)
            if user is not None and user_id not in used:
                reordered.append(user)
                used.add(user_id)

        for user in waiting:
            user_id = user.get("user_id")
            if user_id not in used:
                reordered.append(user)

        state["waiting"] = reordered
        self._log(state, "待機列を手動で並び替えました")

    def remove_user_by_id(self, state: dict, user_id: str) -> None:
        removed = self._find_and_remove_user(state, user_id)
        if removed is None:
            self._log(state, "手動削除: 対象が見つかりません")
            return
        self._log(state, f"{removed.get('display_name', '')} を手動で削除しました")

    def move_user_to_waiting_tail(self, state: dict, user_id: str) -> None:
        user = self._find_and_remove_user(state, user_id)
        if user is None:
            self._log(state, "手動移動: 対象が見つかりません")
            return
        state["waiting"].append(user)
        self._log(state, f"{user.get('display_name', '')} を待機列最後尾へ移動しました")

    def update_declared_player_name(self, state: dict, user_id: str, declared_player_name: str | None) -> None:
        normalized = (declared_player_name or "").strip()
        trimmed = normalized[:32]
        new_value = trimmed or None

        for section in ("current", "waiting"):
            for user in state[section]:
                if user.get("user_id") == user_id:
                    user["declared_player_name"] = new_value
                    self._log(state, "申告名を更新しました")
                    return

        self._log(state, "申告名更新: 対象が見つかりません")

    def cancel_user(self, state: dict) -> None:
        if state["waiting"]:
            removed = state["waiting"].pop(0)
            self._log(state, f"{removed['display_name']} を取消しました")
            return
        self._log(state, "取消対象がいません")

    def cancel_user_by_id(self, state: dict, user_id: str) -> bool:
        for section in ("waiting", "current"):
            users = state[section]
            for index, user in enumerate(users):
                if user.get("user_id") == user_id:
                    removed = users.pop(index)
                    self._log(state, f"{removed['display_name']} を取消しました")
                    return True
        self._log(state, "取消対象がいません")
        return False

    def move_next(self, state: dict) -> None:
        counts = state.setdefault("participation_counts", {})
        for user in state["current"]:
            if user.get("is_placeholder"):
                continue
            user_id = user.get("user_id")
            if not user_id:
                continue
            try:
                base = int(counts.get(user_id, 0))
            except (TypeError, ValueError):
                base = 0
            if base < 0:
                base = 0
            counts[user_id] = base + 1
            user["participation_count"] = max(int(user.get("participation_count", 0)), counts[user_id])

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
