"""Offline recognition after a one-time download of tessdata_best LSTM models."""

from functools import lru_cache
from pathlib import Path

import pooch
from tesserocr import PSM, PyTessBaseAPI

_BASE_URL = (
    "https://raw.githubusercontent.com/tesseract-ocr/tessdata_best/"
    "e12c65a915945e4c28e237a9b52bc4a8f39a0cec/"
)

_MODELS = {
    "pl": (
        "pol",
        "sha256:e80cc4cefbdface06e9223f43f089556b9dcf104020fbc0a200f6863c57d4405",
    ),
    "en": (
        "eng",
        "sha256:8280aed0782fe27257a68ea10fe7ef324ca0f8d85bd2fd145d1c2b560bcb66ba",
    ),
}


@lru_cache(maxsize=2)
def _model_directory(lang: str = "pl") -> tuple[Path, str]:
    tess_lang, known_hash = _MODELS[lang]
    filename = f"{tess_lang}.traineddata"
    model = pooch.retrieve(
        url=_BASE_URL + filename,
        known_hash=known_hash,
        path=pooch.os_cache("czytajpdf") / "tessdata_best",
        fname=filename,
    )
    return Path(model).parent, tess_lang


def open_engine(lang: str = "pl"):
    model_dir, tess_lang = _model_directory(lang)
    return PyTessBaseAPI(path=str(model_dir), lang=tess_lang, psm=PSM.AUTO)


def read_page(engine, image, dpi):
    engine.ClearAdaptiveClassifier()
    engine.SetImage(image)
    engine.SetSourceResolution(dpi)
    return engine.GetUTF8Text().strip()
