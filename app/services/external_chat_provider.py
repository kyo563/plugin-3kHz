from app.schemas.comment import ReceivedComment


class ExternalChatProvider:
    def receive(self, comment: ReceivedComment) -> ReceivedComment:
        return comment
