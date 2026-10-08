from __future__ import annotations

import re
import unicodedata

STOPWORDS = {
    "va", "cua", "cho", "voi", "cac", "nhung", "mot", "trong", "tren", "duoi", "khi", "nay", "kia", "the",
    "nao", "gi", "la", "co", "khong", "duoc", "de", "tu", "den", "ve", "theo", "toi", "ban", "minh",
    "hop", "lam", "viec", "ngay", "hom", "mai", "tuan", "giup", "xem", "nhe", "can", "phai", "con",
    "and", "the", "for", "with", "from", "this", "that", "của", "những",
}
_WORD_RE = re.compile(r"[a-z0-9]+")
JIRA_KEY_RE = re.compile(r"\b[A-Z][A-Z0-9]{1,9}-\d+\b")


def fold(text: str) -> str:
    """Bỏ dấu tiếng Việt + lowercase để so khớp."""
    text = (text or "").replace("đ", "d").replace("Đ", "D")
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return text.lower()


def keywords(text: str, min_len: int = 3) -> set[str]:
    return {w for w in _WORD_RE.findall(fold(text)) if len(w) >= min_len and w not in STOPWORDS}
