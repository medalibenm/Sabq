"""Text cleaning shared by all extractors. Arabic is kept as-is, only NFC-normalised."""

import html
import re
import unicodedata

_TAGS = re.compile(r"<[^>]+>")
_SPACES = re.compile(r"\s+")


def clean_text(value: object, max_chars: int | None = None) -> str:
    """Strip HTML tags and entities, collapse whitespace, NFC-normalise, optionally shorten at a
    word boundary (with "…"). Entities are unescaped twice: some feeds double-escape."""
    if value is None:
        return ""
    text = html.unescape(html.unescape(_TAGS.sub(" ", str(value))))
    text = unicodedata.normalize("NFC", _SPACES.sub(" ", _TAGS.sub(" ", text)).strip())
    if max_chars and len(text) > max_chars:
        cut = text[:max_chars]
        text = (cut.rsplit(" ", 1)[0] if " " in cut else cut) + "…"
    return text
