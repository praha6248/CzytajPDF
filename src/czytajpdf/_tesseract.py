"""Offline recognition with tessdata_best LSTM models (see ``_models`` for how they are located)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from tesserocr import PSM, RIL, PyTessBaseAPI, iterate_level

from ._types import Word


@dataclass(frozen=True)
class TessResult:
    text: str
    words: tuple[Word, ...]
    confidence: float | None


def open_engine(langs: Sequence[str], model_dir: Path):
    return PyTessBaseAPI(path=str(model_dir), lang="+".join(langs), psm=PSM.AUTO)


def read_page(engine, image, dpi) -> TessResult:
    engine.ClearAdaptiveClassifier()
    engine.SetImage(image)
    engine.SetSourceResolution(dpi)
    engine.Recognize()
    text = engine.GetUTF8Text().strip()
    scale = 72 / dpi
    words = []
    iterator = engine.GetIterator()
    if iterator is not None:
        for item in iterate_level(iterator, RIL.WORD):
            try:
                word = (item.GetUTF8Text(RIL.WORD) or "").strip()
            except RuntimeError:  # Tesseract reports "No text returned" for empty segments
                continue
            box = item.BoundingBox(RIL.WORD)
            if word and box:
                words.append(Word(word, tuple(round(v * scale, 2) for v in box), float(item.Confidence(RIL.WORD))))
    confidence = float(engine.MeanTextConf()) if text else None
    return TessResult(text, tuple(words), confidence)


def detect_rotation(model_dir: Path, image, min_confidence: float = 2.0) -> int:
    """Degrees (0/90/180/270) by which the image is rotated clockwise; 0 when unsure."""
    try:
        with PyTessBaseAPI(path=str(model_dir), lang="osd", psm=PSM.OSD_ONLY) as api:
            api.SetImage(image)
            result = api.DetectOrientationScript()
    except Exception:  # OSD fails on blank or tiny pages
        return 0
    if not result or result.get("orient_conf", 0) < min_confidence:
        return 0
    return int(result["orient_deg"]) % 360
