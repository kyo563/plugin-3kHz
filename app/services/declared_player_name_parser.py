class DeclaredPlayerNameParser:
    JOIN_TRIGGER = "参加希望"
    JOIN_EXCLUDES = ("参加希望者", "参加希望順")
    CANCEL_TRIGGERS = ("参加辞退", "参加を辞退")
    KEYWORD = "名前"
    MAX_NAME_LENGTH = 32

    def parse(self, normalized_message: str) -> str | None:
        if any(trigger in normalized_message for trigger in self.CANCEL_TRIGGERS):
            return None
        if any(exclude in normalized_message for exclude in self.JOIN_EXCLUDES):
            return None
        if self.JOIN_TRIGGER not in normalized_message:
            return None
        if self.KEYWORD not in normalized_message:
            return None

        declared_name = normalized_message.split(self.KEYWORD, 1)[1].strip()
        if not declared_name:
            return None

        return declared_name[: self.MAX_NAME_LENGTH]
