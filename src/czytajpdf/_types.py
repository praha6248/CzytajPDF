"""Public result types and internal option containers (no heavy imports)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

BBox = tuple[float, float, float, float]


@dataclass(frozen=True)
class Word:
    """A recognized word (Tesseract) or text line (RapidOCR).

    ``bbox`` is ``(x0, y0, x1, y1)`` in PDF points measured from the top-left corner of the
    (pre-processed) page image; ``confidence`` is 0-100.
    """

    text: str
    bbox: BBox
    confidence: float


@dataclass(frozen=True)
class Correction:
    """One spelling change relative to the raw OCR text. ``offset`` indexes ``Page.raw_text``."""

    raw: str
    fixed: str
    offset: int


@dataclass(frozen=True)
class Page:
    number: int
    source: Literal["pdf", "rapidocr", "tesseract"]
    raw_text: str
    text: str
    confidence: float | None = None
    lang: str | None = None
    width: float | None = None
    height: float | None = None
    words: tuple[Word, ...] = ()
    corrections: tuple[Correction, ...] = ()


@dataclass(frozen=True)
class OcrOptions:
    """Everything a worker needs to OCR pages. Must stay picklable."""

    engine: str
    correct: bool
    tess_langs: tuple[str, ...]
    spell_langs: tuple[str, ...]
    preprocess: tuple[str, ...] = ()
    tessdata_dir: str | None = None
    offline: bool | None = None
    password: str | None = field(default=None, repr=False)
    dpi: int = 300
    second_dpi: int = 180

    def signature(self) -> str:
        """Stable description of everything that influences OCR output (for the page cache)."""
        parts: dict[str, Any] = {
            "engine": self.engine, "correct": self.correct, "tess": self.tess_langs,
            "spell": self.spell_langs, "pre": self.preprocess, "dpi": self.dpi, "dpi2": self.second_dpi,
        }
        return repr(sorted(parts.items()))


@dataclass(frozen=True)
class OcrPage:
    """Raw recognition result for one page, before ``correct="suggest"`` semantics are applied."""

    raw: str
    corrected: str
    confidence: float | None = None
    lang: str | None = None
    width: float | None = None
    height: float | None = None
    words: tuple[Word, ...] = ()
    corrections: tuple[Correction, ...] = ()
