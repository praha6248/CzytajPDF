"""Shared plumbing: source loading, native text backends, OCR routing."""

from __future__ import annotations

import logging
from contextlib import ExitStack
from io import BytesIO
from pathlib import Path
from pypdf import PdfReader
from pypdf.errors import DependencyError, PdfReadError, PdfStreamError

from . import _cache, _preprocess
from ._errors import InvalidPDFError, MissingDependencyError, PasswordRequiredError
from ._langs import LangSpec, parse_lang
from ._quality import is_garbled
from ._types import OcrOptions

log = logging.getLogger("czytajpdf")

PdfSource = "str | Path | bytes | BinaryIO"


def load_source(path) -> Path | bytes:
    if isinstance(path, (bytes, bytearray, memoryview)):
        return bytes(path)
    if hasattr(path, "read"):
        payload = path.read()
        if not isinstance(payload, (bytes, bytearray, memoryview)):
            raise TypeError("Binary stream must return bytes")
        return bytes(payload)
    return Path(path)


class _PypdfBackend:
    def __init__(self, stack: ExitStack, source: Path | bytes, password: str | None) -> None:
        stream = BytesIO(source) if isinstance(source, bytes) else stack.enter_context(source.open("rb"))
        try:
            self._reader = PdfReader(stream)
            if self._reader.is_encrypted:
                if not self._reader.decrypt(password or ""):
                    raise PasswordRequiredError(
                        "the PDF is encrypted; pass password=" if password is None else "wrong PDF password"
                    )
        except DependencyError as exc:
            raise MissingDependencyError(f"encrypted PDFs need the 'cryptography' package: {exc}") from exc
        except (PdfReadError, PdfStreamError) as exc:
            raise InvalidPDFError(f"cannot read PDF: {exc}") from exc

    def __len__(self) -> int:
        try:
            return len(self._reader.pages)
        except (PdfReadError, PdfStreamError) as exc:
            raise InvalidPDFError(f"cannot read PDF: {exc}") from exc

    def text(self, index: int) -> str:
        return self._reader.pages[index].extract_text() or ""


class _PdfiumBackend:
    def __init__(self, stack: ExitStack, source: Path | bytes, password: str | None) -> None:
        try:
            from ._ocr import open_pdf
        except ImportError as exc:
            raise MissingDependencyError("backend='pdfium' requires czytajpdf[ocr] (pypdfium2)") from exc
        try:
            self._pdf = stack.enter_context(open_pdf(source, password))
        except PasswordRequiredError:
            raise
        except Exception as exc:
            raise InvalidPDFError(f"cannot read PDF: {exc}") from exc

    def __len__(self) -> int:
        return len(self._pdf)

    def text(self, index: int) -> str:
        page = self._pdf[index]
        try:
            textpage = page.get_textpage()
            try:
                return textpage.get_text_range().replace("\r\n", "\n")
            finally:
                textpage.close()
        finally:
            page.close()


def open_backend(name: str, stack: ExitStack, source: Path | bytes, password: str | None):
    if name == "pypdf":
        return _PypdfBackend(stack, source, password)
    if name == "pdfium":
        return _PdfiumBackend(stack, source, password)
    raise ValueError("backend must be pypdf or pdfium")


def needs_ocr(text: str, min_chars: int, spec: LangSpec) -> bool:
    """A page needs OCR when its text layer is short, or garbled under every candidate language."""
    if len("".join(text.split())) < min_chars:
        return True
    langs = spec.spell or ("other",)
    return all(is_garbled(text, lang) for lang in langs)


def build_options(*, engine, correct, spec: LangSpec, preprocess, tessdata_dir, offline, password) -> OcrOptions:
    if engine == "rapidocr" and not spec.spell:
        raise ValueError("engine='rapidocr' supports only Polish and English")
    return OcrOptions(
        engine=engine, correct=bool(correct), tess_langs=spec.tess, spell_langs=spec.spell,
        preprocess=_preprocess.normalize_steps(preprocess),
        tessdata_dir=str(tessdata_dir) if tessdata_dir else None, offline=offline, password=password,
    )


def recognize_cached(source, todo, options: OcrOptions, cache_dir, executor_factory, workers: int,
                     digest_box: list):
    """OCR pages, consulting the on-disk cache. ``executor_factory`` creates the pool lazily."""
    try:
        from ._ocr import recognize
    except ImportError as exc:
        raise MissingDependencyError("OCR requires czytajpdf[ocr]") from exc

    results = {}
    missing = list(todo)
    signature = options.signature()
    if cache_dir is not None:
        if not digest_box:
            digest_box.append(_cache.digest(source))
        missing = []
        for index in todo:
            hit = _cache.load(cache_dir, digest_box[0], signature, index)
            if hit is None:
                missing.append(index)
            else:
                results[index] = hit
        log.debug("cache: %d hit(s), %d miss(es)", len(results), len(missing))
    if missing:
        executor = executor_factory() if workers > 1 and len(missing) > 1 else None
        fresh = recognize(source, missing, options, executor, workers) if executor is not None \
            else recognize(source, missing, options)
        results.update(fresh)
        if cache_dir is not None:
            for index, page in fresh.items():
                _cache.store(cache_dir, digest_box[0], signature, index, page)
    return results


__all__ = ["load_source", "open_backend", "needs_ocr", "build_options", "recognize_cached", "parse_lang"]
