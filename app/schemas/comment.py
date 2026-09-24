from app.schemas.avatar import AvatarUrl
from pydantic import BaseModel, ConfigDict, Field, field_validator


class CommentBadges(BaseModel):
    owner: bool = False
    moderator: bool = False
    member: bool = False


class ReceivedComment(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    source: str = Field(min_length=1, max_length=64)
    external_message_id: str | None = Field(default=None, alias="externalMessageId", max_length=512)
    received_at: str = Field(alias="receivedAt", min_length=1, max_length=64)
    display_name: str = Field(alias="displayName", min_length=1, max_length=200)
    youtube_handle: str | None = Field(default=None, alias="youtubeHandle", pattern=r"^@[^\s]{1,199}$", max_length=200)
    youtube_nickname: str | None = Field(default=None, alias="youtubeNickname", min_length=1, max_length=200)
    avatar_url: AvatarUrl = Field(default=None, alias="avatarUrl")
    onecomme_memo: str | None = Field(default=None, alias="oneCommeMemo", max_length=4000)
    user_key: str = Field(alias="userKey", min_length=1, max_length=512)
    message: str = Field(max_length=4096)
    badges: CommentBadges = CommentBadges()

    @field_validator("display_name")
    @classmethod
    def valid_display_name(cls, value: str) -> str:
        value = value.strip()
        if not value or value == "参加者募集中":
            raise ValueError("空の表示名・表示用プレースホルダー名は使用できません")
        return value


class CommentReceiveResult(BaseModel):
    status: str
    duplicate: bool
    command: str
    declared_player_name: str | None = None
