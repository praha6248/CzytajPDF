"""Read Polish and English PDF text, preserving the origin and original wording of each page."""

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import BinaryIO, Literal

from pypdf import PdfReader

from ._quality import needs_ocr


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


def _read_native_pages(path: str | Path | bytes | BinaryIO) -> tuple[list[str], Path | bytes]:
    if isinstance(path, (bytes, bytearray, memoryview)):
        payload = bytes(path)
        reader = PdfReader(BytesIO(payload))
        return [page.extract_text() or "" for page in reader.pages], payload
    if hasattr(path, "read"):
        payload = path.read()
        if not isinstance(payload, (bytes, bytearray, memoryview)):
            raise TypeError("Binary stream must return bytes")
        payload_bytes = bytes(payload)
        reader = PdfReader(BytesIO(payload_bytes))
        return [page.extract_text() or "" for page in reader.pages], payload_bytes
    file_path = Path(path)
    with file_path.open("rb") as stream:
        reader = PdfReader(stream)
        return [page.extract_text() or "" for page in reader.pages], file_path


def extract(
    path: str | Path | bytes | BinaryIO,
    *,
    ocr: bool = False,
    correct: bool = False,
    min_chars: int = 40,
    engine: Literal["tesseract", "rapidocr"] = "tesseract",
    lang: Literal["pl", "en"] = "pl",
) -> Document:
    """Read all pages from a file path, bytes, or binary stream, running OCR when needed."""
    if lang not in ("pl", "en"):
        raise ValueError("lang must be pl or en")
    if engine not in ("rapidocr", "tesseract"):
        raise ValueError("engine must be tesseract or rapidocr")
    if min_chars < 1:
        raise ValueError("min_chars must be positive")
    if correct and not ocr:
        raise ValueError("correct=True requires ocr=True")

    native, source = _read_native_pages(path)

    recognized = {}
    if ocr:
        indices = [i for i, text in enumerate(native) if needs_ocr(text, min_chars, lang)]
        if indices:
            try:
                from ._ocr import recognize
            except ImportError as exc:
                raise ImportError("OCR requires czytajpdf[ocr]") from exc
            recognized = recognize(source, indices, engine, correct, lang)

    pages = []
    for index, original in enumerate(native):
        candidate, text = recognized.get(index, ("", ""))
        if not candidate.strip():
            pages.append(Page(index + 1, "pdf", original, original))
            continue
        pages.append(Page(index + 1, engine, candidate, text))
    return Document(tuple(pages))
