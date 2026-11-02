from pydantic import BaseModel, ConfigDict, Field

LEGACY_DEFAULT_DESCRIPTION = '【参加方法】\nコメントで「参加希望」と送ってください。\n名前を指定したい場合は「参加希望 『◯◯』」のように、希望する名前を『』で囲んでください。\n\n【参加を辞退する場合】\nコメントで「参加辞退」または「参加を辞退」と送ってください。\n\n【参加後に表示名を変更したい場合】\n表示名を変更したいときは配信者にお知らせください。手動で変更します。'

DEFAULT_DESCRIPTION = '【参加方法】\nコメントで「参加希望」と送ってください。\nゲーム内プレイヤー名が異なる場合は「参加希望 『◯◯』」のように、プレイヤー名を『』で囲んで教えてください。\n\n【参加を辞退する場合】\nコメントで「参加辞退」または「参加を辞退」と送ってください。\n※配信者都合で名称を変更させて頂く場合があります。'

PREVIOUS_ONECOMME_DEFAULT_DESCRIPTION = DEFAULT_DESCRIPTION + '\n\n参加回数が少ない方を優先させる場合があります。\n\n【Botの使い方】\n待機順を確認する場合は、@JoinQueueBotへリプライしてください。\n※Botが稼働している場合に利用できます。'

PREVIOUS_HANDLE_ONECOMME_DEFAULT_DESCRIPTION = PREVIOUS_ONECOMME_DEFAULT_DESCRIPTION.replace(
    '待機順を確認する場合は、@JoinQueueBotへリプライしてください。',
    '参加順を確認する場合は、コメントに「@参加列整理bot」または「@bot」を入れて送ってください。',
)

ONECOMME_DEFAULT_DESCRIPTION = '''【参加方法】
コメントで「参加希望」と送ると自動的に登録されます。
ゲーム内プレイヤー名が異なる場合は「参加希望 『◯◯』」のように、プレイヤー名を『』で囲んで教えてください。

【参加を辞退する場合】
コメントで「参加辞退」または「参加を辞退」と送ってください。
※配信者都合で名称を変更させて頂く場合があります。

参加回数が少ない方を優先させる場合があります。

参加希望を2回送った場合、2回目の希望順に並び直しになります。
荒し対策のため、連続で参加希望や辞退を送った場合反映されない場合があります。

【Botの使い方】
参加順を確認する場合は、コメントに「@参加列整理bot」または「@bot」を入れて送ってください。
現在の順番を回答します。'''

# Match only the previously shipped default, never an edited description.
LEGACY_ONECOMME_DEFAULT_DESCRIPTION = PREVIOUS_ONECOMME_DEFAULT_DESCRIPTION.replace(
    '\n※Botが稼働している場合に利用できます。',
    '\n特定の質問文言は不要です。自分の待機順と所属グループをお知らせします。'
    '\n対戦中の場合は「現在参加中です」とお知らせします。'
    '\n同じ方への回答は3分に1回です。'
    '\n※Botが稼働している場合に利用できます。',
)

class DescriptionSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    text: str = Field(default=DEFAULT_DESCRIPTION, max_length=10000)
