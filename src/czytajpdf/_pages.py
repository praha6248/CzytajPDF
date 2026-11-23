"""Page selection such as ``"1-3,7,10-"``."""

from __future__ import annotations

from typing import Iterable


def parse_pages(spec: str | int | Iterable[int] | None, total: int) -> list[int]:
    """Return sorted unique zero-based indices for a 1-based page specification."""
    if spec is None:
        return list(range(total))
    chosen: set[int] = set()
    if isinstance(spec, int) and not isinstance(spec, bool):
        spec = str(spec)
    if isinstance(spec, str):
        for part in spec.replace(" ", "").split(","):
            if not part:
                continue
            first, dash, last = part.partition("-")
            try:
                start = int(first) if first else 1
                stop = (int(last) if last else total) if dash else start
            except ValueError:
                raise ValueError(f"invalid page specification {part!r}") from None
            if start < 1 or stop < start:
                raise ValueError(f"invalid page range {part!r}")
            if start > total:
                raise ValueError(f"page {start} is out of range (document has {total} pages)")
            chosen.update(range(start - 1, min(stop, total)))
    else:
        for number in spec:
            if not isinstance(number, int) or isinstance(number, bool) or not 1 <= number <= total:
                raise ValueError(f"page {number!r} is out of range (document has {total} pages)")
            chosen.add(number - 1)
    if not chosen:
        raise ValueError("page selection is empty")
    return sorted(chosen)
