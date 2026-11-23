"""Cheap image clean-up for skewed, rotated or noisy scans (Pillow + numpy only)."""

from __future__ import annotations

from typing import Callable, Iterable

STEPS = ("rotate", "deskew", "denoise", "binarize")
DEFAULT_STEPS = ("rotate", "deskew")


def normalize_steps(preprocess: bool | str | Iterable[str] | None) -> tuple[str, ...]:
    if not preprocess:
        return ()
    if preprocess is True or preprocess == "auto":
        return DEFAULT_STEPS
    names = preprocess.replace(" ", "").split(",") if isinstance(preprocess, str) else list(preprocess)
    if "all" in names:
        return STEPS
    unknown = [n for n in names if n not in STEPS]
    if unknown:
        raise ValueError(f"unknown preprocess step(s) {unknown}; choose from {', '.join(STEPS)}")
    return tuple(s for s in STEPS if s in names)  # canonical order


def _otsu(gray) -> int:
    import numpy as np

    hist = np.bincount(gray.ravel(), minlength=256).astype(float)
    total = hist.sum()
    sum_all = (np.arange(256) * hist).sum()
    best, weight_b, sum_b, threshold = -1.0, 0.0, 0.0, 128
    for level in range(256):
        weight_b += hist[level]
        if weight_b == 0:
            continue
        weight_f = total - weight_b
        if weight_f == 0:
            break
        sum_b += level * hist[level]
        between = weight_b * weight_f * (sum_b / weight_b - (sum_all - sum_b) / weight_f) ** 2
        if between > best:
            best, threshold = between, level
    return threshold


def estimate_skew(image, limit: float = 6.0) -> float:
    """Angle in degrees (counter-clockwise positive, as used by ``Image.rotate``) that straightens text."""
    import numpy as np
    from PIL import Image

    gray = image.convert("L")
    gray.thumbnail((1000, 1000))
    threshold = _otsu(np.asarray(gray))
    ink = gray.point(lambda v: 255 if v <= threshold else 0)  # text -> bright
    if not np.asarray(ink).any():
        return 0.0

    def score(angle: float) -> float:
        rows = np.asarray(ink.rotate(angle, resample=Image.BILINEAR, fillcolor=0), dtype=np.float32).sum(axis=1)
        return float(np.var(rows))

    coarse = max((a / 2 for a in range(int(-2 * limit), int(2 * limit) + 1)), key=score)
    fine = max((coarse + d / 10 for d in range(-5, 6)), key=score)
    return round(fine, 2)


def apply(image, steps: tuple[str, ...], osd: Callable[[object], int] | None = None):
    """Return a pre-processed RGB copy of ``image``."""
    from PIL import Image, ImageFilter

    if not steps:
        return image
    if "rotate" in steps and osd is not None:
        degrees = osd(image)
        if degrees:
            image = image.rotate(degrees, expand=True, fillcolor=(255, 255, 255))
    if "deskew" in steps:
        angle = estimate_skew(image)
        if abs(angle) >= 0.2:
            image = image.rotate(angle, resample=Image.BICUBIC, fillcolor=(255, 255, 255))
    if "denoise" in steps:
        image = image.filter(ImageFilter.MedianFilter(3))
    if "binarize" in steps:
        import numpy as np

        gray = image.convert("L")
        threshold = _otsu(np.asarray(gray))
        image = gray.point(lambda v: 255 if v > threshold else 0).convert("RGB")
    return image
