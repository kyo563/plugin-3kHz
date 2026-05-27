from collections import deque
from typing import Callable

from app.schemas.comment import CommentReceiveResult, ReceivedComment
from app.services.command_detector import CommandDetector
from app.services.comment_normalizer import CommentNormalizer


class CommentReceiveService:
    def __init__(self, log_writer: Callable[[str], None], max_recent_ids: int = 1000) -> None:
        self._log_writer = log_writer
        self._max_recent_ids = max_recent_ids
        self._recent_ids: deque[str] = deque()
        self._recent_id_set: set[str] = set()
        self._normalizer = CommentNormalizer()
        self._detector = CommandDetector()

    def receive(self, comment: ReceivedComment) -> CommentReceiveResult:
        duplicate = self._is_duplicate(comment.external_message_id)

        if duplicate:
            self._log_writer(f"重複コメントを除外: source={comment.source}, display_name={comment.display_name}")
            return CommentReceiveResult(status="accepted", duplicate=True, command="ignore")

        self._remember_message_id(comment.external_message_id)
        normalized_message = self._normalizer.normalize(comment.message)
        command = self._detector.detect(normalized_message)
        self._log_writer(f"コメント受信: source={comment.source}, display_name={comment.display_name}, command={command}")
        return CommentReceiveResult(status="accepted", duplicate=False, command=command)

    def _is_duplicate(self, external_message_id: str | None) -> bool:
        if not external_message_id:
            return False
        return external_message_id in self._recent_id_set

    def _remember_message_id(self, external_message_id: str | None) -> None:
        if not external_message_id:
            return

        self._recent_ids.append(external_message_id)
        self._recent_id_set.add(external_message_id)

        while len(self._recent_ids) > self._max_recent_ids:
            removed_id = self._recent_ids.popleft()
            self._recent_id_set.discard(removed_id)
