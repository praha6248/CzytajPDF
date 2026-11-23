"""Rasterization and Polish/English recognition adapted from odwolania2json (Apache-2.0)."""

from __future__ import annotations

import logging
from concurrent.futures import Executor
from contextlib import ExitStack
from functools import lru_cache
from pathlib import Path
from threading import Lock

import pypdfium2 as pdfium

from . import _preprocess
from ._errors import MissingDependencyError, PasswordRequiredError
from ._langs import TESSERACT_TO_ISO, detect_lang
from ._types import Correction, OcrOptions, OcrPage, Word

log = logging.getLogger("czytajpdf")
_lock = Lock()


@lru_cache(maxsize=2)
def _engine(lang: str = "pl"):
    from rapidocr import ModelType, OCRVersion, RapidOCR

    return RapidOCR(params={
        "Rec.lang_type": lang,
        "Rec.ocr_version": OCRVersion.PPOCRV6,
        "Rec.model_type": ModelType.SMALL,
    })


def _render(page, dpi):
    bitmap = page.render(scale=dpi / 72)
    try:
        return bitmap.to_pil().convert("RGB")
    finally:
        bitmap.close()


def open_pdf(source: Path | bytes, password: str | None = None):
    try:
        return pdfium.PdfDocument(source, password=password)
    except pdfium.PdfiumError as exc:
        if "password" in str(exc).lower():
            raise PasswordRequiredError("the PDF is encrypted and the password is missing or wrong") from exc
        raise


def _correct(raw: str, alternate, spell_langs: tuple[str, ...], tess_langs, correct: bool):
    """Return (text, page language, corrections) for a raw OCR text."""
    page_lang = detect_lang(raw, spell_langs)
    if not correct or page_lang is None:
        return raw, page_lang, ()
    from ._spell import correct_text, diff_corrections, needs_second_read, reconcile_words

    text = raw
    if needs_second_read(raw, page_lang):
        text = reconcile_words(raw, alternate(), page_lang)
    protect = tuple(lang for lang in spell_langs if lang != page_lang)
    text = correct_text(text, lang=page_lang, protect=protect)
    return text, page_lang, tuple(Correction(*c) for c in diff_corrections(raw, text))


def _recognize_chunk(source: Path | bytes, indices: list[int], o: OcrOptions) -> dict[int, OcrPage]:
    if o.correct:
        from ._spell import ensure_dependencies

        for lang in o.spell_langs:
            ensure_dependencies(lang)
    steps = o.preprocess
    result: dict[int, OcrPage] = {}
    with ExitStack() as stack:
        pdf = stack.enter_context(open_pdf(source, o.password))
        osd = None
        if o.engine == "tesseract":
            try:
                from . import _models
                from ._tesseract import detect_rotation, open_engine, read_page
            except ImportError as exc:
                raise MissingDependencyError("OCR requires czytajpdf[ocr]") from exc
            codes = list(o.tess_langs) + (["osd"] if "rotate" in steps else [])
            model_dir = _models.resolve(codes, o.tessdata_dir, o.offline)
            tesseract = stack.enter_context(open_engine(o.tess_langs, model_dir))
            osd = (lambda image: detect_rotation(model_dir, image)) if "rotate" in steps else None
        else:
            import numpy as np

        for index in indices:
            page = pdf[index]
            try:
                log.debug("OCR page %d with %s", index + 1, o.engine)
                if o.engine == "tesseract":
                    image = _preprocess.apply(_render(page, o.dpi), steps, osd)
                    scan = read_page(tesseract, image, o.dpi)
                    raw, words, confidence = scan.text, scan.words, scan.confidence
                    size = (image.width * 72 / o.dpi, image.height * 72 / o.dpi)

                    def alternate(page=page):
                        second = _preprocess.apply(_render(page, o.second_dpi), steps, osd)
                        return read_page(tesseract, second, o.second_dpi).text
                else:
                    image = _preprocess.apply(_render(page, 180), steps)
                    output = _engine(o.spell_langs[0])(np.asarray(image)[:, :, ::-1].copy())
                    raw = "\n".join(output.txts or ())
                    words, confidence = _rapid_lines(output)
                    size = (image.width * 72 / 180, image.height * 72 / 180)
                    alternate = lambda: raw  # noqa: E731 - RapidOCR has no second read
                text, page_lang, corrections = _correct(raw, alternate, o.spell_langs, o.tess_langs, o.correct)
                result[index] = OcrPage(
                    raw=raw, corrected=text, confidence=confidence, lang=page_lang or (TESSERACT_TO_ISO.get(o.tess_langs[0], o.tess_langs[0]) if o.tess_langs else None),
                    width=round(size[0], 2), height=round(size[1], 2), words=words, corrections=corrections,
                )
            finally:
                page.close()
    return result


def _rapid_lines(output) -> tuple[tuple[Word, ...], float | None]:
    texts = list(output.txts or ())
    if not texts:
        return (), None
    scores = list(output.scores) if getattr(output, "scores", None) is not None else [0.0] * len(texts)
    boxes = output.boxes if getattr(output, "boxes", None) is not None else [None] * len(texts)
    scale = 72 / 180
    lines = []
    for text, score, box in zip(texts, scores, boxes):
        if box is None:
            continue
        xs, ys = [p[0] for p in box], [p[1] for p in box]
        lines.append(Word(text, tuple(round(float(v) * scale, 2) for v in (min(xs), min(ys), max(xs), max(ys))),
                          round(float(score) * 100, 2)))
    mean = sum(w.confidence for w in lines) / len(lines) if lines else None
    return tuple(lines), mean


def _split(indices: list[int], parts: int) -> list[list[int]]:
    size, extra = divmod(len(indices), parts)
    chunks, start = [], 0
    for n in range(parts):
        end = start + size + (1 if n < extra else 0)
        if end > start:
            chunks.append(indices[start:end])
        start = end
    return chunks


def recognize(
    source: Path | bytes,
    indices: list[int],
    options: OcrOptions,
    executor: Executor | None = None,
    workers: int = 1,
) -> dict[int, OcrPage]:
    """OCR the given zero-based pages, in worker processes when an executor is supplied."""
    if executor is not None and workers > 1 and len(indices) > 1:
        futures = [executor.submit(_recognize_chunk, source, chunk, options)
                   for chunk in _split(indices, min(workers, len(indices)))]
        merged: dict[int, OcrPage] = {}
        for future in futures:
            merged.update(future.result())
        return merged
    # PDFium is not thread-safe. Serialize access to it and the shared OCR model.
    with _lock:
        return _recognize_chunk(source, indices, options)
