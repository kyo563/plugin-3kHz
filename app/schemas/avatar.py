from urllib.parse import urlsplit
from typing import Annotated
from pydantic import BeforeValidator


def normalize_avatar_url(value):
    if not isinstance(value, str) or len(value) > 2048:
        return None
    try:
        url = urlsplit(value)
        host = url.hostname or ""
        allowed = any(host == domain or host.endswith("." + domain)
                      for domain in ("ggpht.com", "googleusercontent.com"))
        if url.scheme == "https" and allowed and not url.username and not url.password and url.port in (None, 443):
            return value
    except ValueError:
        pass
    return None


AvatarUrl = Annotated[str | None, BeforeValidator(normalize_avatar_url)]
