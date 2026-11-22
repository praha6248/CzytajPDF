"""Read Polish and English PDF text, preserving the origin and original wording of each page."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pypdf import PdfReader


@dataclass(frozen=True)
class Page:
    number: int
    source: Literal["pdf", "rapidocr", "tesseract"]
    raw_text: str
    text: str


@dataclass(frozen=True)
class Document:
    pages: tuple[Page, ...]

    @property
    def text(self) -> str:
        return "\n".join(page.text for page in self.pages)


def extract(
    path: str | Path,
    *,
    ocr: bool = False,
    correct: bool = False,
    min_chars: int = 40,
    engine: Literal["tesseract", "rapidocr"] = "tesseract",
    lang: Literal["pl", "en"] = "pl",
) -> Document:
    """Read all pages. When enabled, try OCR below min_chars non-whitespace characters."""
    if lang not in ("pl", "en"):
        raise ValueError("lang must be pl or en")
    if engine not in ("rapidocr", "tesseract"):
        raise ValueError("engine must be tesseract or rapidocr")
    if min_chars < 1:
        raise ValueError("min_chars must be positive")
    if correct and not ocr:
        raise ValueError("correct=True requires ocr=True")
    path = Path(path)
    with path.open("rb") as stream:
        reader = PdfReader(stream)
        native = [page.extract_text() or "" for page in reader.pages]

    recognized = {}
    if ocr:
        indices = [i for i, text in enumerate(native) if len("".join(text.split())) < min_chars]
        if indices:
            try:
                from ._ocr import recognize
            except ImportError as exc:
                raise ImportError("OCR requires czytajpdf[ocr]") from exc
            recognized = recognize(path, indices, engine, correct, lang)

    pages = []
    for index, original in enumerate(native):
        candidate, text = recognized.get(index, ("", ""))
        if not candidate.strip():
            pages.append(Page(index + 1, "pdf", original, original))
            continue
        pages.append(Page(index + 1, engine, candidate, text))
    return Document(tuple(pages))
