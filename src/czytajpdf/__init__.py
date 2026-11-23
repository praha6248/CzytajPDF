"""Read Polish and English PDF text, preserving the origin and original wording of each page."""

from __future__ import annotations

import logging
from concurrent.futures import ProcessPoolExecutor
from contextlib import ExitStack
from pathlib import Path
from typing import BinaryIO, Iterable, Iterator, Literal

from . import _core
from ._document import Chunk, Document
from ._errors import (
    CzytajPDFError,
    InvalidPDFError,
    MissingDependencyError,
    ModelNotFoundError,
    PasswordRequiredError,
)
from ._langs import parse_lang
from ._pages import parse_pages
from ._types import Correction, Page, Word

__version__ = "0.5.0"

__all__ = [
    "Chunk", "Correction", "CzytajPDFError", "Document", "InvalidPDFError", "MissingDependencyError",
    "ModelNotFoundError", "Page", "PasswordRequiredError", "Word", "download_models", "extract",
    "extract_iter", "make_searchable", "parse_pages",
]

logging.getLogger("czytajpdf").addHandler(logging.NullHandler())
log = logging.getLogger("czytajpdf")

CorrectMode = bool | Literal["suggest"]


def extract_iter(path: str | Path | bytes | BinaryIO, **kwargs) -> Iterator[Page]:
    """Yield pages one by one (memory-friendly for long documents); arguments as in :func:`extract`.

    Arguments are validated immediately; the file is opened when iteration starts. OCR runs in
    batches of ``batch_size`` pages (default ``16 * workers``).
    """
    return _extract_iter(path, False, **kwargs)


def _extract_iter(
    path: str | Path | bytes | BinaryIO,
    eager: bool,
    *,
    ocr: bool = False,
    correct: CorrectMode = False,
    min_chars: int = 40,
    engine: Literal["tesseract", "rapidocr"] = "tesseract",
    lang: str = "pl",
    pages: str | int | Iterable[int] | None = None,
    backend: Literal["pypdf", "pdfium"] = "pypdf",
    password: str | None = None,
    workers: int = 1,
    preprocess: bool | str | Iterable[str] = False,
    cache: bool | str | Path = False,
    tessdata_dir: str | Path | None = None,
    offline: bool | None = None,
    batch_size: int | None = None,
) -> Iterator[Page]:
    spec = parse_lang(lang)
    if engine not in ("rapidocr", "tesseract"):
        raise ValueError("engine must be tesseract or rapidocr")
    if backend not in ("pypdf", "pdfium"):
        raise ValueError("backend must be pypdf or pdfium")
    if min_chars < 1:
        raise ValueError("min_chars must be positive")
    if workers < 1:
        raise ValueError("workers must be at least 1")
    if batch_size is not None and batch_size < 1:
        raise ValueError("batch_size must be positive")
    if correct not in (True, False, "suggest"):
        raise ValueError("correct must be True, False or 'suggest'")
    if correct and not ocr:
        raise ValueError("correct=True requires ocr=True")
    if correct and not spec.spell:
        raise ValueError("spelling repair is available for Polish and English only (lang containing pl and/or en)")
    options = _core.build_options(
        engine=engine, correct=correct, spec=spec, preprocess=preprocess,
        tessdata_dir=tessdata_dir, offline=offline, password=password,
    )
    suggest = correct == "suggest"
    return _iterate(path, ocr, suggest, min_chars, engine, spec, pages, backend, password, workers, options,
                    cache, batch_size, eager)


def _iterate(path, ocr, suggest, min_chars, engine, spec, pages, backend, password, workers, options,
             cache, batch_size, eager) -> Iterator[Page]:
    from . import _cache

    source = _core.load_source(path)
    cache_dir = _cache.resolve_dir(cache) if ocr else None
    digest_box: list[str] = []
    pool: list[ProcessPoolExecutor] = []

    def executor_factory() -> ProcessPoolExecutor:
        if not pool:
            import multiprocessing

            pool.append(ProcessPoolExecutor(workers, mp_context=multiprocessing.get_context("spawn")))
        return pool[0]

    with ExitStack() as stack:
        reader = _core.open_backend(backend, stack, source, password)
        selected = parse_pages(pages, len(reader))
        step = batch_size or (len(selected) if eager else 16 * workers)
        try:
            for start in range(0, len(selected), step):
                batch = selected[start:start + step]
                native = {i: reader.text(i) for i in batch}
                todo = [i for i in batch if ocr and _core.needs_ocr(native[i], min_chars, spec)]
                recognized = _core.recognize_cached(source, todo, options, cache_dir, executor_factory,
                                                    workers, digest_box) if todo else {}
                for index in batch:
                    result = recognized.get(index)
                    if result is None or not result.raw.strip():
                        original = native[index]
                        yield Page(index + 1, "pdf", original, original)
                        continue
                    yield Page(
                        index + 1, engine, result.raw, result.raw if suggest else result.corrected,
                        confidence=result.confidence, lang=result.lang, width=result.width,
                        height=result.height, words=result.words, corrections=result.corrections,
                    )
        finally:
            for executor in pool:
                executor.shutdown(wait=True, cancel_futures=True)


def extract(path: str | Path | bytes | BinaryIO, **kwargs) -> Document:
    """Read all (or the selected) pages from a file path, bytes, or binary stream, running OCR when needed.

    Parameters
    ----------
    ocr, correct, min_chars, engine, lang
        As before. ``correct`` may also be ``"suggest"``: ``Page.text`` stays raw and
        ``Page.corrections`` lists proposed changes. ``lang`` accepts ``"pl"``, ``"en"``,
        ``"pl+en"``, ``"auto"`` (Polish+English, detected per page) or any Tesseract language
        (e.g. ``"de"``, ``"deu"``; spelling repair only for pl/en).
    pages
        ``"1-3,7,10-"``, an int, or an iterable of 1-based page numbers.
    backend
        Native text extractor: ``"pypdf"`` (default) or ``"pdfium"`` (faster, often better reading order).
    password
        For encrypted PDFs.
    workers
        OCR processes (CPU-bound). Scripts must use ``if __name__ == "__main__":`` when ``workers > 1``.
    preprocess
        ``True`` (rotate + deskew), or a comma list/iterable of ``rotate, deskew, denoise, binarize``.
    cache
        ``True`` (``$CZYTAJPDF_CACHE`` or ``~/.cache/czytajpdf``) or a directory: skip re-OCR of unchanged pages.
    tessdata_dir, offline
        Use local models only / never download (see ``czytajpdf download-models``).
    """
    return Document(tuple(_extract_iter(path, kwargs.get("batch_size") is None, **kwargs)))


def make_searchable(*args, **kwargs):
    """Write a searchable PDF (invisible text layer); see :func:`czytajpdf._searchable.make_searchable`."""
    from ._searchable import make_searchable as _make

    return _make(*args, **kwargs)


def download_models(languages: Iterable[str] = ("pl", "en"), directory: str | Path | None = None,
                    include_osd: bool = False) -> Path:
    """Download and verify Tesseract models once, so later runs can be fully offline."""
    from . import _models

    codes = [c for lang in languages for c in parse_lang(lang).tess]
    if include_osd:
        codes.append("osd")
    return _models.download(codes, directory)
