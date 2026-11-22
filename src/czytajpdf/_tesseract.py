"""Offline recognition after a one-time download of the Polish LSTM model."""

from functools import lru_cache
from pathlib import Path

import pooch
from tesserocr import PSM, PyTessBaseAPI

_MODEL_URL = (
    "https://raw.githubusercontent.com/tesseract-ocr/tessdata_best/"
    "e12c65a915945e4c28e237a9b52bc4a8f39a0cec/pol.traineddata"
)


@lru_cache(maxsize=1)
def _model_directory() -> Path:
    model = pooch.retrieve(
        url=_MODEL_URL,
        known_hash="sha256:e80cc4cefbdface06e9223f43f089556b9dcf104020fbc0a200f6863c57d4405",
        path=pooch.os_cache("czytajpdf") / "tessdata_best",
        fname="pol.traineddata",
    )
    return Path(model).parent


def open_engine():
    return PyTessBaseAPI(path=str(_model_directory()), lang="pol", psm=PSM.AUTO)


def read_page(engine, image, dpi):
    engine.ClearAdaptiveClassifier()
    engine.SetImage(image)
    engine.SetSourceResolution(dpi)
    return engine.GetUTF8Text().strip()
