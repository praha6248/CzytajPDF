"""Find words in a PDF and replace them with other text.

Native text layer
    The text object ("run") that holds the word is rebuilt with the replacement, in the same position,
    size and colour, using a TrueType font that has Polish letters (``font=`` or a system font). The
    original text is removed, so search and copy-paste see the new word. The rest of that run gets the
    replacement font too.
Scans / pages without text
    With ``ocr=True`` words come from Tesseract; the old word is covered with a patch in the sampled
    background colour and the new one is drawn on top. The scanned image itself still contains the old
    pixels under the patch (this is a visual edit, not a redaction).
"""

from __future__ import annotations

import ctypes
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Iterable, Mapping

from ._errors import CzytajPDFError, MissingDependencyError
from ._pages import parse_pages
from ._types import BBox

log = logging.getLogger("czytajpdf")

_WORD = re.compile(r"[^\W_]+(?:[-'’][^\W_]+)*")
_FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/noto/NotoSans-Regular.ttf",
    "/Library/Fonts/Arial.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
)


class FontNotFoundError(CzytajPDFError, OSError):
    """No TrueType font with the needed glyphs could be located; pass ``font=``."""


@dataclass(frozen=True)
class WordMatch:
    """A word (or phrase) located in the PDF. Use it as a key in :func:`edit_pdf` to edit exactly this one."""

    id: int
    page: int                       # 1-based
    text: str
    bbox: BBox                      # PDF points from the page's top-left corner
    context: str = ""
    source: str = "pdf"             # "pdf" (text layer) or "ocr"
    char_start: int = -1            # text-layer character index (source == "pdf")
    char_count: int = 0

    def __str__(self) -> str:
        return f"[{self.id}] p.{self.page} {self.text!r}  …{self.context}…"


@dataclass(frozen=True)
class Edit:
    old: str
    new: str
    page: int | None = None         # restrict to one page
    occurrence: int | None = None   # 1-based n-th match (document order); None = every match


@dataclass(frozen=True)
class Replacement:
    page: int
    old: str
    new: str
    method: str                     # "text" (run rebuilt), "overlay" (cover + draw)
    bbox: BBox
    residual: bool = False          # True when part of the old text may remain in the text layer


@dataclass(frozen=True)
class EditReport:
    replacements: tuple[Replacement, ...] = ()
    skipped: tuple[tuple[str, str], ...] = ()   # (what, reason)

    @property
    def count(self) -> int:
        return len(self.replacements)


def find_font(font: str | os.PathLike | None = None) -> Path:
    if font:
        path = Path(font).expanduser()
        if not path.is_file():
            raise FontNotFoundError(f"font file not found: {path}")
        return path
    for candidate in (os.environ.get("CZYTAJPDF_FONT"), *_FONT_CANDIDATES):
        if candidate and Path(candidate).is_file():
            return Path(candidate)
    raise FontNotFoundError("no TrueType font found; pass font='/path/to/Font.ttf' or set CZYTAJPDF_FONT")


class _Doc:
    """A PDF held in memory so that the output may overwrite the input."""

    def __init__(self, path, password):
        try:
            import pypdfium2 as pdfium
        except ImportError as exc:
            raise MissingDependencyError("editing requires czytajpdf[ocr] (pypdfium2)") from exc
        from ._core import load_source
        from ._ocr import open_pdf

        source = load_source(path)
        self.payload = source.read_bytes() if isinstance(source, Path) else source
        self.pdf = open_pdf(self.payload, password)
        self.pdfium = pdfium
        self.fonts: list = []

    def close(self) -> None:
        import pypdfium2.raw as raw

        for font in self.fonts:
            raw.FPDFFont_Close(font)
        self.pdf.close()


def _page_geometry(page):
    left, bottom, right, top = page.get_bbox()
    return left, bottom, right, top


def _to_top_left(page, l, b, r, t) -> BBox:
    pl, pb, pr, pt = _page_geometry(page)
    return (round(l - pl, 2), round(pt - t, 2), round(r - pl, 2), round(pt - b, 2))


def _to_pdf(page, bbox: BBox):
    pl, pb, pr, pt = _page_geometry(page)
    x0, y0, x1, y1 = bbox
    return pl + x0, pt - y1, pl + x1, pt - y0   # left, bottom, right, top


def _context(text: str, start: int, count: int, width: int = 28) -> str:
    return " ".join(text[max(0, start - width):start + count + width].split())


def _collect(doc: _Doc, query, pages, match_case, whole_word, ocr, lang, min_chars, first_id=0) -> list[WordMatch]:
    from ._core import needs_ocr
    from ._langs import parse_lang

    pdf = doc.pdf
    spec = parse_lang(lang)
    found: list[WordMatch] = []
    next_id = first_id
    for index in parse_pages(pages, len(pdf)):
        page = pdf[index]
        textpage = page.get_textpage()
        try:
            total = textpage.count_chars()
            text = textpage.get_text_range(0, total) if total else ""
            if ocr and needs_ocr(text, min_chars, spec):
                from ._ocr import _recognize_chunk
                from ._types import OcrOptions

                options = OcrOptions("tesseract", False, spec.tess, spec.spell)
                scan = _recognize_chunk(doc.payload, [index], options)[index]
                lowered = query if match_case else (query or "").lower()
                for word in scan.words:
                    candidate = word.text.strip(".,;:!?()[]„”\"'")
                    probe = candidate if match_case else candidate.lower()
                    if query is None or (probe == lowered if whole_word else lowered in probe):
                        found.append(WordMatch(next_id, index + 1, word.text, word.bbox, scan.raw[:0], "ocr"))
                        next_id += 1
                continue
            spans: list[tuple[int, int]] = []
            if query is None:
                spans = [(m.start(), len(m.group())) for m in _WORD.finditer(text)]
            elif query:
                searcher = textpage.search(query, match_case=match_case, match_whole_word=whole_word)
                while (hit := searcher.get_next()) is not None:
                    spans.append((hit[0], hit[1]))
            for start, count in spans:
                boxes = [textpage.get_charbox(i) for i in range(start, start + count)]
                boxes = [b for b in boxes if b[2] > b[0]]
                if not boxes:
                    continue
                l, b, r, t = (min(x[0] for x in boxes), min(x[1] for x in boxes),
                              max(x[2] for x in boxes), max(x[3] for x in boxes))
                found.append(WordMatch(next_id, index + 1, text[start:start + count],
                                       _to_top_left(page, l, b, r, t), _context(text, start, count),
                                       "pdf", start, count))
                next_id += 1
        finally:
            textpage.close()
            page.close()
    return found


def find_words(
    path: str | Path | bytes | BinaryIO,
    query: str | None = None,
    *,
    pages: str | int | Iterable[int] | None = None,
    match_case: bool = False,
    whole_word: bool = True,
    ocr: bool = False,
    lang: str = "pl",
    min_chars: int = 40,
    password: str | None = None,
) -> list[WordMatch]:
    """List occurrences of ``query`` (or every word when ``query`` is None) with ids, boxes and context.

    With ``ocr=True``, pages without a usable text layer are read with Tesseract (single words only).
    """
    doc = _Doc(path, password)
    try:
        return _collect(doc, query, pages, match_case, whole_word, ocr, lang, min_chars)
    finally:
        doc.close()


# ---------------------------------------------------------------------------------------------------
def _load_font(doc: _Doc, path: Path):
    import pypdfium2.raw as raw

    data = path.read_bytes()
    buffer = (ctypes.c_uint8 * len(data)).from_buffer_copy(data)
    handle = raw.FPDFText_LoadFont(doc.pdf.raw, buffer, len(data), raw.FPDF_FONT_TRUETYPE, 1)
    if not handle:
        raise FontNotFoundError(f"PDFium could not load font {path}")
    doc.fonts.append(handle)
    return handle


def _text_object(doc: _Doc, font, size: float, text: str, color, matrix):
    import pypdfium2.raw as raw

    obj = raw.FPDFPageObj_CreateTextObj(doc.pdf.raw, font, size)
    units = text.encode("utf-16-le")
    buffer = (ctypes.c_uint16 * (len(units) // 2 + 1))(*memoryview(units).cast("H"))
    if not raw.FPDFText_SetText(obj, buffer):
        raise CzytajPDFError("PDFium refused the replacement text")
    r, g, b = color
    raw.FPDFPageObj_SetFillColor(obj, r, g, b, 255)
    raw.FPDFPageObj_Transform(obj, *matrix)
    return obj


def _fill_color(obj) -> tuple[int, int, int]:
    import pypdfium2.raw as raw

    r, g, b, a = (ctypes.c_uint() for _ in range(4))
    if raw.FPDFPageObj_GetFillColor(obj.raw, r, g, b, a):
        return r.value, g.value, b.value
    return 0, 0, 0


def _sample_colors(page, bbox: BBox):
    """(background, ink) colours estimated from a render of the page around ``bbox``."""
    import numpy as np

    scale = 2.0
    image = page.render(scale=scale).to_pil().convert("RGB")
    x0, y0, x1, y1 = (int(v * scale) for v in bbox)
    pad = int(3 * scale)
    outer = np.asarray(image.crop((max(0, x0 - pad), max(0, y0 - pad), x1 + pad, y1 + pad))).reshape(-1, 3)
    inner = np.asarray(image.crop((max(0, x0), max(0, y0), x1, y1))).reshape(-1, 3)
    if not len(inner):
        return (255, 255, 255), (0, 0, 0)
    background = tuple(int(v) for v in np.median(outer, axis=0))
    order = inner.sum(axis=1).argsort()[: max(1, len(inner) // 10)]
    ink = tuple(int(v) for v in inner[order].mean(axis=0))
    return background, ink


def _text_width(font_path: Path, text: str, size: float) -> float:
    from PIL import ImageFont

    return ImageFont.truetype(str(font_path), 100).getlength(text) * size / 100


def _overlay(doc, page, font, font_path, match: WordMatch, new: str, fit: bool, removed_all: bool, colors):
    import pypdfium2.raw as raw

    l, b, r, t = _to_pdf(page, match.bbox)
    background, ink = colors
    pad = 0.8
    if not removed_all:
        rect = raw.FPDFPageObj_CreateNewRect(l - pad, b - pad, (r - l) + 2 * pad, (t - b) + 2 * pad)
        raw.FPDFPageObj_SetFillColor(rect, *background, 255)
        raw.FPDFPath_SetDrawMode(rect, raw.FPDF_FILLMODE_ALTERNATE, 0)
        raw.FPDFPage_InsertObject(page.raw, rect)
    size = max(4.0, (t - b) / 1.15)
    if fit:
        width = _text_width(font_path, new, size)
        if width > (r - l) * 1.05:
            size = max(size * 0.6, size * (r - l) * 1.05 / width)
    baseline = b + (t - b) * 0.2
    obj = _text_object(doc, font, size, new, ink, (1, 0, 0, 1, l, baseline))
    raw.FPDFPage_InsertObject(page.raw, obj)


def _rewrite_run(doc, page, font, textobj, new_text: str):
    """Replace one text run by an equivalent one in ``font``; the old run is removed."""
    import pypdfium2.raw as raw

    matrix = textobj.get_matrix().get()
    size = textobj.get_font_size()
    color = _fill_color(textobj)
    new = _text_object(doc, font, size, new_text, color, matrix)
    page.remove_obj(textobj)
    raw.FPDFPage_InsertObject(page.raw, new)


def _normalize_edits(replacements) -> list[tuple[Edit | None, WordMatch | None, str]]:
    items: list[tuple[Edit | None, WordMatch | None, str]] = []
    if isinstance(replacements, Mapping):
        for key, value in replacements.items():
            items.append((None, key, value) if isinstance(key, WordMatch) else (Edit(key, value), None, value))
    else:
        for edit in replacements:
            if not isinstance(edit, Edit):
                raise TypeError("replacements must be a mapping or an iterable of Edit")
            items.append((edit, None, edit.new))
    return items


def edit_pdf(
    path: str | Path | bytes | BinaryIO,
    output: str | os.PathLike | BinaryIO,
    replacements: Mapping[str | WordMatch, str] | Iterable[Edit],
    *,
    pages: str | int | Iterable[int] | None = None,
    match_case: bool = False,
    whole_word: bool = True,
    font: str | os.PathLike | None = None,
    fit: bool = True,
    ocr: bool = False,
    lang: str = "pl",
    min_chars: int = 40,
    password: str | None = None,
) -> EditReport:
    """Replace words in a PDF and save the result.

    ``replacements`` is ``{"stare": "nowe"}`` (every occurrence), a list of :class:`Edit`
    (page/occurrence control), or ``{match: "nowe"}`` with :class:`WordMatch` objects from
    :func:`find_words` to edit exactly the chosen occurrence. Returns an :class:`EditReport`.
    Output is written unencrypted; the input file is not modified (``output`` may equal it).
    """
    items = _normalize_edits(replacements)
    font_path = find_font(font)
    doc = _Doc(path, password)
    replaced: list[Replacement] = []
    skipped: list[tuple[str, str]] = []
    try:
        targets: list[tuple[WordMatch, str]] = []
        for edit, match, new in items:
            if match is not None:
                targets.append((match, new))
                continue
            scope = edit.page if edit.page is not None else pages
            hits = _collect(doc, edit.old, scope, match_case, whole_word, ocr, lang, min_chars)
            if edit.occurrence is not None:
                hits = hits[edit.occurrence - 1:edit.occurrence]
            if not hits:
                skipped.append((edit.old, "no match"))
            targets.extend((hit, new) for hit in hits)

        font_handle = _load_font(doc, font_path) if targets else None
        by_page: dict[int, list[tuple[WordMatch, str]]] = {}
        for match, new in targets:
            by_page.setdefault(match.page, []).append((match, new))

        for number, page_targets in sorted(by_page.items()):
            page = doc.pdf[number - 1]
            try:
                if page.get_rotation():
                    skipped.extend((m.text, f"page {number} is rotated") for m, _ in page_targets)
                    continue
                textpage = page.get_textpage()
                try:
                    runs: dict[int, list] = {}
                    leftovers: list[tuple[WordMatch, str]] = []
                    for match, new in page_targets:
                        run = _locate_run(textpage, match) if match.source == "pdf" else None
                        if run is None:
                            leftovers.append((match, new))
                        else:
                            runs.setdefault(run[0], [run[1], []])[1].append((run[2], match, new))
                    for _, (obj, edits) in runs.items():
                        text = obj.extract()
                        for offset, match, new in sorted(edits, key=lambda e: -e[0]):
                            text = text[:offset] + new + text[offset + match.char_count:]
                            replaced.append(Replacement(number, match.text, new, "text", match.bbox))
                        _rewrite_run(doc, page, font_handle, obj, text)
                    for match, new in leftovers:
                        removed_all, residual = (False, False)
                        if match.source == "pdf":
                            removed_all, residual = _remove_covered(page, textpage, match)
                        colors = _sample_colors(page, match.bbox)
                        _overlay(doc, page, font_handle, font_path, match, new, fit, removed_all, colors)
                        replaced.append(Replacement(number, match.text, new, "overlay", match.bbox,
                                                    residual or match.source == "ocr"))
                finally:
                    textpage.close()
                page.gen_content()
            finally:
                page.close()
        doc.pdf.save(output)
    finally:
        doc.close()
    return EditReport(tuple(replaced), tuple(skipped))


def _locate_run(textpage, match: WordMatch):
    """(run id, run object, offset inside run) when the whole match lies in one text object."""
    start, count = match.char_start, match.char_count
    first = textpage.get_textobj(start)
    if first is None:
        return None
    key = ctypes.cast(first.raw, ctypes.c_void_p).value
    for i in range(start, start + count):
        other = textpage.get_textobj(i)
        if other is None or ctypes.cast(other.raw, ctypes.c_void_p).value != key:
            return None
    begin = start
    while begin > 0:
        before = textpage.get_textobj(begin - 1)
        if before is None or ctypes.cast(before.raw, ctypes.c_void_p).value != key:
            break
        begin -= 1
    offset = start - begin
    try:
        text = first.extract()
    except Exception:
        return None
    expected = textpage.get_text_range(start, count)
    if text[offset:offset + count] != expected:
        return None
    return key, first, offset


def _remove_covered(page, textpage, match: WordMatch) -> tuple[bool, bool]:
    """Remove text objects that lie wholly inside the match box. Returns (all removed, residual text)."""
    l, b, r, t = _to_pdf(page, match.bbox)
    seen: dict[int, object] = {}
    for i in range(match.char_start, match.char_start + match.char_count):
        obj = textpage.get_textobj(i)
        if obj is not None:
            seen[ctypes.cast(obj.raw, ctypes.c_void_p).value] = obj
    residual = False
    for obj in seen.values():
        ol, ob, orr, ot = obj.get_bounds()
        if ol >= l - 1 and ob >= b - 1 and orr <= r + 1 and ot <= t + 1:
            page.remove_obj(obj)
        else:
            residual = True
    return not residual, residual
