"""Tesseract model resolution: pinned downloads, a user-supplied directory, or strict offline mode.

Resolution order:
1. ``tessdata_dir=`` argument, then the ``CZYTAJPDF_TESSDATA`` environment variable: a directory that
   already holds ``<code>.traineddata`` files. Nothing is ever downloaded in this mode.
2. The per-user cache (``czytajpdf download-models`` fills it). Missing files are downloaded
   (SHA-256 verified) unless offline mode is on (``offline=True`` or ``CZYTAJPDF_OFFLINE=1``).
"""

from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path
from typing import Iterable

from ._errors import MissingDependencyError, ModelNotFoundError

log = logging.getLogger("czytajpdf")

_BASE_URL = (
    "https://raw.githubusercontent.com/tesseract-ocr/tessdata_best/"
    "e12c65a915945e4c28e237a9b52bc4a8f39a0cec/"
)

# SHA-256 of tessdata_best files at the pinned commit above.
MODELS = {
    "pol": "e80cc4cefbdface06e9223f43f089556b9dcf104020fbc0a200f6863c57d4405",
    "eng": "8280aed0782fe27257a68ea10fe7ef324ca0f8d85bd2fd145d1c2b560bcb66ba",
    "osd": "9cf5d576fcc47564f11265841e5ca839001e7e6f38ff7f7aacf46d15a96b00ff",
    "deu": "8407331d6aa0229dc927685c01a7938fc5a641d1a9524f74838cdac599f0d06e",
    "fra": "907743d98915c91a3906dfbf6e48b97598346698fe53aaa797e1a064ffcac913",
    "spa": "e2c1ffdad8b30f26c45d4017a9183d3a7f9aa69e59918be4f88b126fac99ab2c",
    "ita": "8df9c89176fb93f56bf4b2d4ede04c01c1f31d4b7697fbd76cc336df700f3f38",
    "ces": "d821773116d3c4e0360ea750066436c60ae45af02c39da3a840a543d761b3f41",
    "ukr": "1277f6e3b6f707063a92d40e7678e7f57154e8414e328e340be9ee9275eea9c8",
    "rus": "b617eb6830ffabaaa795dd87ea7fd251adfe9cf0efe05eb9a2e8128b7728d6b6",
    "por": "711de9dbb8052067bd42f16b9119967f30bada80d57e2ef24f65d09f531adb04",
    "nld": "92e7a1ad4bf8082e268de57c7823316ec024935702c6ed2a1e473b3a071aa733",
    "slk": "3553e335f64408412c8741fec19e443b5fda81d88abe59aa1401cba4e8825bed",
    "lat": "60054dd32ac03ebd9b4f87d0665bd491a7ffe0d3ee99ceb91aefaf348b65e94f",
}


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def cache_directory() -> Path:
    try:
        import pooch
    except ImportError as exc:
        raise MissingDependencyError("OCR requires czytajpdf[ocr]") from exc
    return Path(pooch.os_cache("czytajpdf")) / "tessdata_best"


def configured_directory(tessdata_dir: str | os.PathLike | None = None) -> Path | None:
    chosen = tessdata_dir or os.environ.get("CZYTAJPDF_TESSDATA")
    return Path(chosen).expanduser() if chosen else None


def resolve(codes: Iterable[str], tessdata_dir: str | os.PathLike | None = None,
            offline: bool | None = None) -> Path:
    """Return a directory that contains every requested ``<code>.traineddata`` file."""
    wanted = list(dict.fromkeys(codes))
    local = configured_directory(tessdata_dir)
    if local is not None:
        missing = [c for c in wanted if not (local / f"{c}.traineddata").is_file()]
        if missing:
            raise ModelNotFoundError(
                f"missing {', '.join(c + '.traineddata' for c in missing)} in {local} "
                "(tessdata_dir / CZYTAJPDF_TESSDATA never triggers downloads)"
            )
        return local

    if offline is None:
        offline = _truthy(os.environ.get("CZYTAJPDF_OFFLINE"))
    directory = cache_directory()
    for code in wanted:
        if code not in MODELS:
            raise ModelNotFoundError(
                f"no pinned download for language {code!r}; put {code}.traineddata in a directory "
                "and pass tessdata_dir= (or set CZYTAJPDF_TESSDATA)"
            )
        target = directory / f"{code}.traineddata"
        if target.is_file() and _sha256(target) == MODELS[code]:
            continue
        if offline:
            raise ModelNotFoundError(
                f"{code}.traineddata is not in the cache ({directory}) and offline mode is on; "
                "run `czytajpdf download-models` once while online, or set CZYTAJPDF_TESSDATA"
            )
        import pooch

        log.info("downloading %s.traineddata", code)
        pooch.retrieve(url=_BASE_URL + f"{code}.traineddata", known_hash=f"sha256:{MODELS[code]}",
                       path=directory, fname=f"{code}.traineddata")
    return directory


def download(codes: Iterable[str], directory: str | os.PathLike | None = None) -> Path:
    """Fetch (and verify) models into the cache, or into ``directory``. Returns the directory."""
    codes = list(dict.fromkeys(codes))
    if directory is None:
        return resolve(codes, offline=False) if not configured_directory() else resolve(codes)
    import pooch

    target = Path(directory).expanduser()
    for code in codes:
        if code not in MODELS:
            raise ModelNotFoundError(f"no pinned download for language {code!r}")
        pooch.retrieve(url=_BASE_URL + f"{code}.traineddata", known_hash=f"sha256:{MODELS[code]}",
                       path=target, fname=f"{code}.traineddata")
    return target
