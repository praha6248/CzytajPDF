"""On-disk cache of OCR results keyed by PDF content, page and OCR options."""

from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import asdict
from pathlib import Path

from ._types import Correction, OcrPage, Word

log = logging.getLogger("czytajpdf")
_VERSION = 1


def resolve_dir(cache: bool | str | os.PathLike | None) -> Path | None:
    if not cache:
        return None
    if cache is True:
        env = os.environ.get("CZYTAJPDF_CACHE")
        base = Path(env) if env else Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "czytajpdf" / "pages"
    else:
        base = Path(cache)
    base = base.expanduser()
    base.mkdir(parents=True, exist_ok=True)
    return base


def digest(source: Path | bytes) -> str:
    h = hashlib.sha256()
    if isinstance(source, bytes):
        h.update(source)
    else:
        with Path(source).open("rb") as stream:
            for block in iter(lambda: stream.read(1 << 20), b""):
                h.update(block)
    return h.hexdigest()


def _path(directory: Path, pdf_digest: str, signature: str, index: int) -> Path:
    key = hashlib.sha256(f"{_VERSION}|{pdf_digest}|{signature}|{index}".encode()).hexdigest()
    return directory / key[:2] / f"{key}.json"


def load(directory: Path, pdf_digest: str, signature: str, index: int) -> OcrPage | None:
    path = _path(directory, pdf_digest, signature, index)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return OcrPage(
            raw=data["raw"], corrected=data["corrected"], confidence=data["confidence"], lang=data["lang"],
            width=data["width"], height=data["height"],
            words=tuple(Word(w["text"], tuple(w["bbox"]), w["confidence"]) for w in data["words"]),
            corrections=tuple(Correction(**c) for c in data["corrections"]),
        )
    except (OSError, ValueError, KeyError, TypeError):
        return None


def store(directory: Path, pdf_digest: str, signature: str, index: int, page: OcrPage) -> None:
    path = _path(directory, pdf_digest, signature, index)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(page), ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)
    except OSError as exc:  # a read-only cache must never break extraction
        log.warning("could not write cache entry: %s", exc)
