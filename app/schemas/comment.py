from pydantic import BaseModel, ConfigDict, Field


class CommentBadges(BaseModel):
    owner: bool = False
    moderator: bool = False
    member: bool = False


class ReceivedComment(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    source: str
    external_message_id: str | None = Field(default=None, alias="externalMessageId")
    received_at: str = Field(alias="receivedAt")
    display_name: str = Field(alias="displayName")
    user_key: str = Field(alias="userKey")
    message: str
    badges: CommentBadges = CommentBadges()


class CommentReceiveResult(BaseModel):
    status: str
    duplicate: bool
    command: str
