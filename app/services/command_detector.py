class CommandDetector:
    JOIN_TRIGGER = "参加希望"
    CANCEL_TRIGGERS = ("参加辞退", "参加を辞退")
    JOIN_EXCLUDES = ("参加希望者", "参加希望順")

    def detect(self, normalized_message: str) -> str:
        if self._has_cancel(normalized_message):
            return "cancel"

        if self._has_join_exclude(normalized_message):
            return "ignore"

        if self.JOIN_TRIGGER in normalized_message:
            return "join"

        return "ignore"

    def _has_cancel(self, normalized_message: str) -> bool:
        return any(trigger in normalized_message for trigger in self.CANCEL_TRIGGERS)

    def _has_join_exclude(self, normalized_message: str) -> bool:
        return any(exclude in normalized_message for exclude in self.JOIN_EXCLUDES)
