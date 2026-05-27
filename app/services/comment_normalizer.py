import re
import unicodedata


class CommentNormalizer:
    def normalize(self, message: str) -> str:
        normalized = unicodedata.normalize("NFKC", message)
        normalized = normalized.replace("\u3000", " ")
        normalized = normalized.replace("\n", " ").replace("\r", " ").replace("\t", " ")
        normalized = re.sub(r"\s+", " ", normalized).strip()
        return normalized.lower()
