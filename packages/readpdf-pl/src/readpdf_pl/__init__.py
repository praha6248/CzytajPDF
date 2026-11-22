"""Page-wise Polish PDF text extraction powered by CzytajPDF."""

from pathlib import Path
from typing import BinaryIO, Literal

from czytajpdf import Document, Page
from czytajpdf import extract as _extract

__all__ = ["Document", "Page", "extract"]


def extract(
    path: str | Path | bytes | BinaryIO,
    *,
    ocr: bool = False,
    correct: bool = False,
    min_chars: int = 40,
    engine: Literal["tesseract", "rapidocr"] = "tesseract",
    lang: Literal["pl", "en"] = "pl",
) -> Document:
    """Read all pages of a PDF, falling back to Polish OCR below min_chars or on garbled layers."""
    return _extract(path, ocr=ocr, correct=correct, min_chars=min_chars, engine=engine, lang=lang)
