"""Heuristics for detecting unreadable or corrupted PDF text layers."""

from __future__ import annotations

import re
import unicodedata

_CID_TOKEN = re.compile(r"\(cid:\d+\)|/gid\d+", re.IGNORECASE)
_ALPHA_TOKEN = re.compile(r"[A-Za-zÀ-žĄĆĘŁŃÓŚŹŻąćęłńóśźż]+")
WORD = re.compile(r"[A-Za-zÀ-žĄĆĘŁŃÓŚŹŻąćęłńóśźż]{3,}")
_VOWELS = frozenset("aeiouyąęóAEIOUYĄĘÓ")


def _lexicon_quality(words: list[str], lang: str) -> float | None:
    """Return share of 3+ letter words found in the language lexicon, or None if unavailable."""
    try:
        import wordfreq  # noqa: F401
    except ImportError:
        return None
    from ._spell import fold, is_word, lexicon

    known, folded_index, _ = lexicon(lang)
    if not known:
        return None

    hits = 0
    for word in words:
        lower = word.lower()
        if lower in known:
            hits += 1
        elif lang == "pl" and fold(lower) in folded_index:
            hits += 1
        elif lang == "pl":
            try:
                if is_word(word, "pl"):
                    hits += 1
            except ImportError:
                pass
    return hits / len(words)


def is_garbled(text: str, lang: str = "pl") -> bool:
    """Return True when a non-empty PDF text layer appears corrupted or unreadable."""
    non_ws = "".join(text.split())
    if not non_ws:
        return True

    cid_chars = sum(len(match.group()) for match in _CID_TOKEN.finditer(text))
    if cid_chars > 0.1 * len(non_ws) or len(_CID_TOKEN.findall(text)) >= 3:
        return True

    replacement = sum(1 for ch in non_ws if ch == "\ufffd" or unicodedata.category(ch) == "Cc")
    if replacement >= 3 or replacement / len(non_ws) > 0.03:
        return True

    private_use = sum(1 for ch in non_ws if unicodedata.category(ch) == "Co")
    if private_use / len(non_ws) > 0.15:
        return True

    if sum(ch.isalnum() for ch in non_ws) / len(non_ws) < 0.45:
        return True

    alpha_tokens = _ALPHA_TOKEN.findall(text)
    words = WORD.findall(text)
    if len(alpha_tokens) >= 10:
        single_char_share = sum(len(tok) == 1 for tok in alpha_tokens) / len(alpha_tokens)
        if single_char_share > 0.60 and len(words) < 3:
            return True

    if len(words) >= 5:
        vowel_share = sum(any(ch in _VOWELS for ch in word) for word in words) / len(words)
        if vowel_share < 0.40:
            return True

    if len(words) >= 8 and lang in ("pl", "en"):
        quality = _lexicon_quality(words, lang)
        if quality is not None and quality < 0.35:
            return True

    return False


def needs_ocr(text: str, min_chars: int = 40, lang: str = "pl") -> bool:
    """Tell whether a page's PDF text layer is missing, too short, or garbled."""
    return len("".join(text.split())) < min_chars or is_garbled(text, lang=lang)
