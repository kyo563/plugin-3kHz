from __future__ import annotations

import hashlib


class UserIdentityService:
    def build_comment_user_id(self, source: str, user_key: str) -> str:
        raw = f"{source}:{user_key}".encode("utf-8")
        digest = hashlib.sha256(raw).hexdigest()
        return f"comment:{digest}"
