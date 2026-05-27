from typing import Protocol

from app.schemas.comment import ReceivedComment


class ChatProvider(Protocol):
    def receive(self, comment: ReceivedComment) -> ReceivedComment:
        ...
