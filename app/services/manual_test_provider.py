from app.schemas.comment import ReceivedComment


class ManualTestProvider:
    def receive(self, comment: ReceivedComment) -> ReceivedComment:
        return comment.model_copy(update={"source": "manual"})
