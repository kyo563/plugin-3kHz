from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from app.services.comment_normalizer import CommentNormalizer

class CommandSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    join: list[str] = Field(default_factory=lambda: ["参加希望"], min_length=1, max_length=20)
    cancel: list[str] = Field(default_factory=lambda: ["参加辞退", "参加を辞退"], min_length=1, max_length=20)

    @field_validator("join", "cancel")
    @classmethod
    def normalize_words(cls, words):
        normalized = [CommentNormalizer().normalize(word) for word in words]
        if any(not word or len(word) > 64 or "『" in word or "』" in word for word in normalized):
            raise ValueError("各文言は1〜64文字で入力し、『』は含めないでください")
        return list(dict.fromkeys(normalized))

    @model_validator(mode="after")
    def no_conflict(self):
        if any(a in b or b in a for a in self.join for b in self.cancel):
            raise ValueError("参加と辞退で同じ文言、または互いを含む文言は登録できません")
        return self
