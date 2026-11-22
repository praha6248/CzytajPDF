"""Rasterization and Polish/English recognition adapted from odwolania2json (Apache-2.0)."""

from contextlib import ExitStack
from functools import lru_cache
from pathlib import Path
from threading import Lock

import pypdfium2 as pdfium

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


def recognize(
    source: Path | bytes,
    indices: list[int],
    engine: str,
    correct: bool,
    lang: str = "pl",
) -> dict[int, tuple[str, str]]:
    result = {}
    if correct:
        from ._spell import correct_text, ensure_dependencies, needs_second_read, reconcile_words

        ensure_dependencies(lang)
    # PDFium is not thread-safe. Serialize access to it and the shared OCR model.
    with _lock, pdfium.PdfDocument(source) as pdf, ExitStack() as stack:
        if engine == "tesseract":
            try:
                from ._tesseract import open_engine, read_page
            except ImportError as exc:
                raise ImportError("OCR requires czytajpdf[ocr]") from exc

            tesseract = stack.enter_context(open_engine(lang))
        else:
            import numpy as np

        for index in indices:
            page = pdf[index]
            try:
                if engine == "tesseract":
                    raw = read_page(tesseract, _render(page, 300), 300)
                    text = raw
                    if correct and needs_second_read(raw, lang):
                        alternate = read_page(tesseract, _render(page, 180), 180)
                        text = reconcile_words(raw, alternate, lang)
                else:
                    image = np.asarray(_render(page, 180))[:, :, ::-1].copy()
                    output = _engine(lang)(image)
                    raw = text = "\n".join(output.txts or ())
                result[index] = raw, correct_text(text, lang=lang) if correct else text
            finally:
                page.close()
    return result
