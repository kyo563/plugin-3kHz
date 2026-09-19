"""Portable state only: no paths, credentials, runtime settings or executable data."""
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.schemas.overlay_settings import OverlaySettings
from app.schemas.description import DEFAULT_DESCRIPTION

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
UserId = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=256)]
Count = Annotated[int, Field(strict=True, ge=0, le=2147483647)]

class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

class Participant(StrictModel):
    user_id: UserId
    display_name: Name
    declared_player_name: str | None = Field(default=None, max_length=200)
    youtube_handle: str | None = Field(default=None, max_length=200)
    youtube_nickname: str | None = Field(default=None, max_length=200)
    participation_count: Count

class HistoryUser(StrictModel):
    user_id: UserId
    display_name: Name
    first_match: Count
    count: Count

class HistorySession(StrictModel):
    id: str = Field(min_length=1, max_length=64)
    label: str = Field(max_length=100)
    started_at: str = Field(max_length=64)
    matches: Count
    users: list[HistoryUser] = Field(max_length=10000)

    @model_validator(mode="after")
    def unique_users(self):
        if len({u.user_id for u in self.users}) != len(self.users):
            raise ValueError("履歴の参加者IDが重複しています")
        return self

class BackupState(StrictModel):
    participation_history: list[HistorySession] = Field(default_factory=list, max_length=100)
    description_text: str = Field(default=DEFAULT_DESCRIPTION, max_length=10000)
    total_match_count: Count = 0
    overlay_settings: OverlaySettings = Field(default_factory=OverlaySettings)
    name_overrides: dict[UserId, Name] = Field(default_factory=dict, max_length=20000)
    is_open: bool
    priority_mode: bool
    cooldown_seconds: Literal[40]
    show_declared_player_name_on_overlay: bool
    current: list[Participant] = Field(max_length=3)
    waiting: list[Participant] = Field(max_length=10000)
    participation_counts: dict[UserId, Count] = Field(max_length=20000)
    logs: list[Annotated[str, Field(max_length=8192)]] = Field(max_length=30)

    @model_validator(mode="after")
    def consistent(self):
        users = self.current + self.waiting
        if len({u.user_id for u in users}) != len(users):
            raise ValueError("参加者IDが重複しています")
        for user in users:
            if user.display_name == "参加者募集中":
                raise ValueError("表示専用の名前は登録できません")
            if self.participation_counts.get(user.user_id) != user.participation_count:
                raise ValueError("参加回数が一致していません")
        return self

class Backup(StrictModel):
    format: Literal["waiting-list-backup"] = "waiting-list-backup"
    version: Literal[1] = 1
    state: BackupState

class RestorePayload(StrictModel):
    backup: Backup
    expected_revision: int = Field(ge=0)
