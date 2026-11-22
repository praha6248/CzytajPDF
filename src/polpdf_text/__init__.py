"""Read Polish PDF text, preserving the origin and original wording of each page."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pypdf import PdfReader


@dataclass(frozen=True)
class Page:
    number: int
    source: Literal["pdf", "rapidocr"]
    raw_text: str
    text: str


@dataclass(frozen=True)
class Document:
    pages: tuple[Page, ...]

    @property
    def text(self) -> str:
        return "\n".join(page.text for page in self.pages)


def extract(path: str | Path, *, ocr: bool = False, correct: bool = False,
            min_chars: int = 40) -> Document:
    """Read all pages. When enabled, try OCR below min_chars non-whitespace characters."""
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
                raise ImportError("OCR requires polpdf-text[ocr]") from exc
            recognized = recognize(path, indices)

    pages = []
    for index, original in enumerate(native):
        candidate = recognized.get(index, "")
        if not candidate.strip():
            pages.append(Page(index + 1, "pdf", original, original))
            continue
        text = candidate
        if correct:
            try:
                from ._spell import correct_text
            except ImportError as exc:
                raise ImportError("Spelling repair requires polpdf-text[polish]") from exc
            text = correct_text(candidate)
        pages.append(Page(index + 1, "rapidocr", candidate, text))
    return Document(tuple(pages))
