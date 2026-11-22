"""Rasterization and Polish recognition adapted from odwolania2json (Apache-2.0)."""

from functools import lru_cache
from pathlib import Path
from threading import Lock

import numpy as np
import pypdfium2 as pdfium
from rapidocr import ModelType, OCRVersion, RapidOCR

_lock = Lock()


@lru_cache(maxsize=1)
def _engine():
    return RapidOCR(params={
        "Rec.lang_type": "pl",
        "Rec.ocr_version": OCRVersion.PPOCRV6,
        "Rec.model_type": ModelType.SMALL,
    })


def recognize(path: Path, indices: list[int]) -> dict[int, str]:
    result = {}
    # PDFium is not thread-safe. Serialize access to it and the shared OCR model.
    with _lock, pdfium.PdfDocument(path) as pdf:
        for index in indices:
            page = pdf[index]
            try:
                bitmap = page.render(scale=2.5)
                try:
                    image = np.array(bitmap.to_pil().convert("RGB"))[:, :, ::-1].copy()
                finally:
                    bitmap.close()
            finally:
                page.close()
            output = _engine()(image)
            result[index] = "\n".join(output.txts or ())
    return result
