from uuid import uuid4
from fastapi import HTTPException
from app.schemas.backup import Backup, BackupState


def add_participant(services, display_name: str, user_id: str | None):
    name = display_name.strip()
    if not name or name == "参加者募集中":
        raise HTTPException(422, "参加者の表示名を入力してください（参加者募集中は使用できません）")
    identity = (user_id or "").strip() or "manual:" + uuid4().hex
    def mutate(state):
        if not state["is_open"]:
            raise HTTPException(409, "受付を開始してから追加してください")
        if any(u["user_id"] == identity for u in state["current"] + state["waiting"]):
            raise HTTPException(409, "この参加者IDは登録済みです")
        count = state["participation_counts"].get(identity, 0)
        services.queue_service.add_user(state, {"user_id": identity, "display_name": name,
            "participation_count": count})
        state["participation_counts"][identity] = count
    services.persistence_service.manual_mutate(mutate)


def correct_count(services, user_id: str, count: int):
    def mutate(state):
        found = False
        for user in state["current"] + state["waiting"]:
            if user["user_id"] == user_id:
                user["participation_count"] = count
                found = True
        if not found and user_id not in state["participation_counts"]:
            raise HTTPException(404, "参加者が見つかりません")
        state["participation_counts"][user_id] = count
        services.queue_service._log(state, f"参加回数を{count}回に補正しました")
    services.persistence_service.manual_mutate(mutate)


def export_backup(services):
    state, _, _ = services.persistence_service.snapshot()
    state.pop("user_action_locks", None)
    for user in state["current"] + state["waiting"]:
        user.pop("created_at", None)
        user.pop("updated_at", None)
    return Backup(state=BackupState.model_validate(state))
