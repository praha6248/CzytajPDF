"""Language specifications: 'pl', 'en', 'pl+en', 'auto', or any Tesseract language."""

from __future__ import annotations

import re
from dataclasses import dataclass

ISO_TO_TESSERACT = {
    "pl": "pol", "en": "eng", "de": "deu", "fr": "fra", "es": "spa", "it": "ita", "cs": "ces",
    "uk": "ukr", "ru": "rus", "pt": "por", "nl": "nld", "sk": "slk", "la": "lat",
}
TESSERACT_TO_ISO = {v: k for k, v in ISO_TO_TESSERACT.items()}
SPELL_LANGS = ("pl", "en")
_CODE = re.compile(r"^[a-z]{2,3}(_[a-z0-9]+)?$")


@dataclass(frozen=True)
class LangSpec:
    tess: tuple[str, ...]    # Tesseract model codes, e.g. ("pol", "eng")
    spell: tuple[str, ...]   # subset of ("pl", "en") usable for spelling repair / lexicon checks
    label: str


def parse_lang(lang: str) -> LangSpec:
    if not isinstance(lang, str) or not lang.strip():
        raise ValueError("lang must be a non-empty string such as 'pl', 'en', 'pl+en' or 'auto'")
    text = lang.strip().lower()
    if text == "auto":
        return LangSpec(("pol", "eng"), ("pl", "en"), "auto")
    tess: list[str] = []
    for part in text.split("+"):
        if not _CODE.match(part):
            raise ValueError(f"invalid language code {part!r}; use e.g. 'pl', 'en', 'deu', 'pl+en' or 'auto'")
        code = ISO_TO_TESSERACT.get(part, part)
        if code not in tess:
            tess.append(code)
    spell = tuple(TESSERACT_TO_ISO[c] for c in tess if TESSERACT_TO_ISO.get(c) in SPELL_LANGS)
    return LangSpec(tuple(tess), spell, text)


def detect_lang(text: str, candidates: tuple[str, ...]) -> str | None:
    """Pick the candidate whose lexicon recognizes most words of the text (first one on ties)."""
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]
    from ._quality import WORD
    from ._spell import fold, lexicon

    words = [w.lower() for w in WORD.findall(text)]
    best, best_hits = candidates[0], -1
    for lang in candidates:
        known, index, _ = lexicon(lang)
        hits = sum(1 for w in words if w in known or (lang == "pl" and fold(w) in index and w == fold(w)))
        if hits > best_hits:
            best, best_hits = lang, hits
    return best
