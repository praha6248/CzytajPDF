"""Polish and English OCR spelling repair adapted from odwolania2json under Apache-2.0."""
from __future__ import annotations

from difflib import SequenceMatcher
from functools import lru_cache
import itertools
import re
import unicodedata

from ._quality import WORD

def fold(text: str) -> str:
    text = text.replace("ł", "l").replace("Ł", "L")
    return "".join(c for c in unicodedata.normalize("NFD", text) if not unicodedata.combining(c))


L_LOOKALIKES = "tfh"
MAX_SUBSTITUTIONS = 3
ACCENT_MARGIN = 0.5
ACCENTS = {"a": "ą", "e": "ę", "l": "ł", "t": "ł", "o": "ó", "s": "ś", "c": "ć", "n": "ń", "z": "żź"}

# High-precision visual OCR confusions for English tokens; avoids corrupting proper nouns.
EN_OCR_PAIRS = (
    ("rn", "m"),
    ("fn", "m"),
    ("hi", "m"),
    ("in", "m"),
    ("ni", "m"),
    ("vv", "w"),
    ("cl", "d"),
    ("e", "c"),
    ("c", "e"),
    ("f", "t"),
    ("t", "f"),
    ("l", "i"),
    ("i", "l"),
    ("v", "y"),
)


def ensure_dependencies(lang: str = "pl") -> None:
    """Verify optional spelling dependencies for the selected language."""
    try:
        import wordfreq  # noqa: F401
    except ImportError as exc:
        extra = "polish" if lang == "pl" else "english"
        label = "Polish" if lang == "pl" else "English"
        raise ImportError(f"{label} spelling repair requires czytajpdf[{extra}]") from exc
    if lang == "pl":
        try:
            import morfeusz2  # noqa: F401
        except ImportError as exc:
            raise ImportError("Polish spelling repair requires czytajpdf[polish]") from exc


@lru_cache(maxsize=2)
def lexicon(lang: str = "pl", size: int = 400000) -> tuple[frozenset[str], dict[str, str], dict[str, str]]:
    """Return known words and (for Polish) accent-folded lookup tables."""
    import wordfreq

    words = wordfreq.top_n_list(lang, size)
    if lang != "pl":
        return frozenset(words), {}, {}
    index: dict[str, str] = {}
    accented: dict[str, str] = {}
    for word in words:
        key = fold(word)
        index.setdefault(key, word)
        if word != key:
            accented.setdefault(key, word)
    return frozenset(words), index, accented


@lru_cache(maxsize=1)
def _morfeusz():
    import morfeusz2

    return morfeusz2.Morfeusz(generate=False)


@lru_cache(maxsize=65536)
def is_word(word: str, lang: str = "pl") -> bool:
    """Tell whether a form exists in the frequency lexicon (or Morfeusz2 for Polish)."""
    known = lexicon(lang)[0]
    if word.lower() in known:
        return True
    if lang != "pl":
        return False
    analyser = _morfeusz()
    return any(item[2][2] != "ign" for item in analyser.analyse(word))


def _frequency(word: str, lang: str = "pl") -> float:
    """Zipf frequency of a word (0 when unknown)."""
    import wordfreq

    return wordfreq.zipf_frequency(word, lang)


def _variants(key: str) -> list[str]:
    """Folded variants where up to MAX_SUBSTITUTIONS look-alike letters are read as 'l' (folded 'ł')."""
    positions = [i for i, c in enumerate(key) if c in L_LOOKALIKES]
    out = []
    for count in range(1, min(MAX_SUBSTITUTIONS, len(positions)) + 1):
        for chosen in itertools.combinations(positions, count):
            chars = list(key)
            for i in chosen:
                chars[i] = "l"
            out.append("".join(chars))
    return out


def _restore_with_morfeusz(lower: str, max_changes: int = 2) -> str | None:
    """Find a Polish dictionary form differing by at most two diacritic or 'ł' restorations."""
    if len(lower) > 24:
        return None
    positions = [i for i, c in enumerate(lower) if c in ACCENTS]
    if len(positions) > 8:
        max_changes = 1
    for count in range(1, max_changes + 1):
        for chosen in itertools.combinations(positions, count):
            for letters in itertools.product(*(ACCENTS[lower[i]] for i in chosen)):
                chars = list(lower)
                for i, letter in zip(chosen, letters):
                    chars[i] = letter
                candidate = "".join(chars)
                if is_word(candidate, "pl"):
                    return candidate
    return None


def _match_case(original: str, word: str) -> str:
    """Apply the capitalization pattern of the original token to the replacement."""
    if original.isupper() and len(original) > 1:
        return word.upper()
    if original[0].isupper():
        return word[0].upper() + word[1:]
    return word


def _correct_english_word(token: str, known: frozenset[str], min_zipf: float) -> str:
    lower = token.lower()
    if len(lower) < 5 or lower in known:
        return token
    candidates = set()
    for old, new in EN_OCR_PAIRS:
        start = 0
        while (idx := lower.find(old, start)) != -1:
            candidate = lower[:idx] + new + lower[idx + len(old):]
            if candidate in known:
                candidates.add(candidate)
            start = idx + 1
    if not candidates:
        return token
    best = max(candidates, key=lambda word: _frequency(word, "en"))
    # Require stronger evidence for title-cased words so proper nouns stay intact.
    threshold = max(min_zipf, 3.5) if token[0].isupper() and not token.isupper() else min_zipf
    if _frequency(best, "en") < threshold:
        return token
    return _match_case(token, best)


def _correct_polish_word(token: str, known: frozenset[str], index: dict[str, str],
                         accented: dict[str, str], min_zipf: float) -> str:
    lower = token.lower()
    key = fold(lower)
    if lower in known:
        better = accented.get(key)
        if better and lower == key and _frequency(better, "pl") - _frequency(lower, "pl") >= ACCENT_MARGIN:
            return _match_case(token, better)
        return token
    if key in index and index[key] != lower:
        return _match_case(token, index[key])
    if is_word(token, "pl"):
        return token
    candidates = [index[variant] for variant in _variants(key) if variant in index]
    if not candidates:
        restored = _restore_with_morfeusz(lower)
        return _match_case(token, restored) if restored else token
    best = max(candidates, key=lambda word: _frequency(word, "pl"))
    if _frequency(best, "pl") < min_zipf:
        return token
    return _match_case(token, best)


def correct_word(token: str, min_zipf: float | None = None, lang: str = "pl") -> str:
    """Return the most likely intended word for an OCR token, or the token itself."""
    if len(token) > 48:
        return token
    known, index, accented = lexicon(lang)
    if not known:
        return token
    if lang == "en":
        return _correct_english_word(token, known, 1.5 if min_zipf is None else min_zipf)
    return _correct_polish_word(token, known, index, accented, 2.0 if min_zipf is None else min_zipf)


# A line-ending hyphen splits one lexical item into two apparent words.
# Keep both fragments intact, including their original line separator.
SPELL_TOKEN = re.compile(r"(?P<split>[^\W\d_]+[-‐]\s*\n[ \t]*[^\W\d_]+)|" + WORD.pattern)


def correct_text(text: str, min_zipf: float | None = None, lang: str = "pl", protect: tuple[str, ...] = ()) -> str:
    """Repair every word of an OCR text that is not in the lexicon.

    Words that are valid in one of the ``protect`` languages (e.g. English quotations inside a
    Polish page) are left untouched.
    """
    def repair(match: re.Match) -> str:
        if match["split"]:
            return match[0]
        word = match[0]
        if any(word.lower() in lexicon(other)[0] for other in protect):
            return word
        return correct_word(word, min_zipf, lang=lang)

    return SPELL_TOKEN.sub(repair, text)


def diff_corrections(raw: str, fixed: str) -> tuple[tuple[str, str, int], ...]:
    """Word-level changes between the raw and the repaired text as ``(raw, fixed, offset_in_raw)``."""
    if raw == fixed:
        return ()
    old = [(m.group(), m.start()) for m in re.finditer(r"\S+", raw)]
    new = [m.group() for m in re.finditer(r"\S+", fixed)]
    changes = []
    matcher = SequenceMatcher(None, [t for t, _ in old], new, autojunk=False)
    for tag, a, b, c, d in matcher.get_opcodes():
        if tag == "replace" and b - a == d - c:
            changes.extend((old[i][0], new[j], old[i][1]) for i, j in zip(range(a, b), range(c, d)))
        elif tag in ("replace", "delete", "insert"):
            before = " ".join(t for t, _ in old[a:b])
            changes.append((before, " ".join(new[c:d]), old[a][1] if a < len(old) else len(raw)))
    return tuple(changes)


def needs_second_read(text: str, lang: str = "pl") -> bool:
    return any(not is_word(word, lang) for word in WORD.findall(text))


def reconcile_words(text: str, second_read: str, lang: str = "pl") -> str:
    """Repair unknown words only when a second reading supplies a similar known form."""
    tokens = list(re.finditer(r"\S+", text))
    first = [token.group() for token in tokens]
    second = second_read.split()
    pieces = []
    last = 0
    for tag, a, b, c, d in SequenceMatcher(None, first, second, autojunk=False).get_opcodes():
        if tag != "replace" or b - a != d - c:
            continue
        for token, candidate in zip(tokens[a:b], second[c:d]):
            original = token.group()
            match = WORD.search(original)
            other = WORD.search(candidate)
            if not match or not other:
                continue
            before, after = match.group(), other.group()
            if (original[:match.start()] != candidate[:other.start()]
                    or original[match.end():] != candidate[other.end():]):
                continue
            if len(before) != len(after) or sum(x != y for x, y in zip(before, after)) > 1:
                continue
            if not is_word(before, lang) and is_word(after, lang):
                pieces.extend((text[last:token.start()], candidate))
                last = token.end()
    pieces.append(text[last:])
    return "".join(pieces)
