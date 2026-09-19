class CommandDetector:
    JOIN_TRIGGER = "参加希望"
    CANCEL_TRIGGERS = ("参加辞退", "参加を辞退")
    JOIN_EXCLUDES = ("参加希望者", "参加希望順")

    def detect(self, normalized_message: str, settings=None) -> str:
        words = settings or {"join": [self.JOIN_TRIGGER], "cancel": list(self.CANCEL_TRIGGERS)}
        if any(word in normalized_message for word in words["cancel"]):
            return "cancel"

        if any(word in normalized_message and (word != self.JOIN_TRIGGER or not self._has_join_exclude(normalized_message))
               for word in words["join"]):
            return "join"

        return "ignore"

    def _has_cancel(self, normalized_message: str) -> bool:
        return any(trigger in normalized_message for trigger in self.CANCEL_TRIGGERS)

    def _has_join_exclude(self, normalized_message: str) -> bool:
        return any(exclude in normalized_message for exclude in self.JOIN_EXCLUDES)
