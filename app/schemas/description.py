from pydantic import BaseModel, ConfigDict, Field

LEGACY_DEFAULT_DESCRIPTION = '【参加方法】\nコメントで「参加希望」と送ってください。\n名前を指定したい場合は「参加希望 『◯◯』」のように、希望する名前を『』で囲んでください。\n\n【参加を辞退する場合】\nコメントで「参加辞退」または「参加を辞退」と送ってください。\n\n【参加後に表示名を変更したい場合】\n表示名を変更したいときは配信者にお知らせください。手動で変更します。'

DEFAULT_DESCRIPTION = '【参加方法】\nコメントで「参加希望」と送ってください。\nゲーム内プレイヤー名が異なる場合は「参加希望 『◯◯』」のように、プレイヤー名を『』で囲んで教えてください。\n\n【参加を辞退する場合】\nコメントで「参加辞退」または「参加を辞退」と送ってください。\n※配信者都合で名称を変更させて頂く場合があります。'

class DescriptionSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    text: str = Field(default=DEFAULT_DESCRIPTION, max_length=10000)
