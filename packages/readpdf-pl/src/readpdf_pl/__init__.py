"""Page-wise Polish PDF text extraction powered by CzytajPDF."""

from pathlib import Path
from typing import BinaryIO, Iterator

from czytajpdf import (
    Chunk,
    Correction,
    CzytajPDFError,
    Document,
    InvalidPDFError,
    MissingDependencyError,
    ModelNotFoundError,
    Page,
    PasswordRequiredError,
    Word,
    download_models,
    make_searchable,
)
from czytajpdf import extract as _extract
from czytajpdf import extract_iter as _extract_iter

__all__ = [
    "Chunk", "Correction", "CzytajPDFError", "Document", "InvalidPDFError", "MissingDependencyError",
    "ModelNotFoundError", "Page", "PasswordRequiredError", "Word", "download_models", "extract",
    "extract_iter", "make_searchable",
]


def extract(path: str | Path | bytes | BinaryIO, *, lang: str = "pl", **kwargs) -> Document:
    """Read all pages of a PDF; OCR falls back to Polish by default. See ``czytajpdf.extract``."""
    return _extract(path, lang=lang, **kwargs)


def extract_iter(path: str | Path | bytes | BinaryIO, *, lang: str = "pl", **kwargs) -> Iterator[Page]:
    """Yield pages one by one. See ``czytajpdf.extract_iter``."""
    return _extract_iter(path, lang=lang, **kwargs)
