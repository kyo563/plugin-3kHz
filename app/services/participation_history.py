from datetime import datetime, timezone
from uuid import uuid4


def new_session(state, label=""):
    sessions = state.setdefault("participation_history", [])
    if len(sessions) >= 100:
        raise ValueError("履歴は100配信までです。バックアップ後に全リセットしてください")
    session = {"id": uuid4().hex, "label": label.strip() or "配信の参加履歴", "started_at": datetime.now(timezone.utc).isoformat(), "matches": 0, "users": []}
    sessions.append(session)
    return session


def record_match(state):
    users = [u for u in state["current"] if u.get("user_id") and not u.get("is_placeholder")]
    if not users:
        return
    sessions = state.setdefault("participation_history", [])
    session = sessions[-1] if sessions else new_session(state)
    by_id = {u["user_id"]: u for u in session["users"]}
    if len(set(by_id) | {u["user_id"] for u in users}) > 10000:
        raise ValueError("この配信の履歴が1万人に達しました。新しい配信の履歴を開始してください")
    session["matches"] += 1
    for user in users:
        uid = user["user_id"]
        name = user.get("declared_player_name") or user.get("youtube_nickname") or user["display_name"]
        if uid not in by_id:
            row = {"user_id": uid, "display_name": name, "first_match": session["matches"], "count": 0}
            session["users"].append(row)
            by_id[uid] = row
        by_id[uid]["display_name"] = name
        by_id[uid]["count"] += 1
