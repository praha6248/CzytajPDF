"""Rasterization and Polish recognition adapted from odwolania2json (Apache-2.0)."""

from contextlib import ExitStack
from functools import lru_cache
from pathlib import Path
from threading import Lock

import pypdfium2 as pdfium

_lock = Lock()


@lru_cache(maxsize=1)
def _engine():
    from rapidocr import ModelType, OCRVersion, RapidOCR

    return RapidOCR(params={
        "Rec.lang_type": "pl",
        "Rec.ocr_version": OCRVersion.PPOCRV6,
        "Rec.model_type": ModelType.SMALL,
    })


def _render(page, dpi):
    bitmap = page.render(scale=dpi / 72)
    try:
        return bitmap.to_pil().convert("RGB")
    finally:
        bitmap.close()


def recognize(path: Path, indices: list[int], engine: str, correct: bool) -> dict[int, tuple[str, str]]:
    result = {}
    if correct:
        try:
            from ._spell import correct_text, needs_second_read, reconcile_words
        except ImportError as exc:
            raise ImportError("Spelling repair requires czytajpdf[polish]") from exc
    # PDFium is not thread-safe. Serialize access to it and the shared OCR model.
    with _lock, pdfium.PdfDocument(path) as pdf, ExitStack() as stack:
        if engine == "tesseract":
            from ._tesseract import open_engine, read_page

            tesseract = stack.enter_context(open_engine())
        else:
            import numpy as np

        for index in indices:
            page = pdf[index]
            try:
                if engine == "tesseract":
                    raw = read_page(tesseract, _render(page, 300), 300)
                    text = raw
                    if correct and needs_second_read(raw):
                        alternate = read_page(tesseract, _render(page, 180), 180)
                        text = reconcile_words(raw, alternate)
                else:
                    image = np.asarray(_render(page, 180))[:, :, ::-1].copy()
                    output = _engine()(image)
                    raw = text = "\n".join(output.txts or ())
                result[index] = raw, correct_text(text) if correct else text
            finally:
                page.close()
    return result
