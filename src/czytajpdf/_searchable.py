"""Turn scans into searchable PDFs by adding an invisible Tesseract text layer."""

from __future__ import annotations

import logging
import os
import tempfile
from contextlib import ExitStack
from pathlib import Path
from typing import BinaryIO, Iterable

from pypdf import PdfReader, PdfWriter, Transformation

from . import _core, _models, _preprocess
from ._errors import MissingDependencyError
from ._langs import parse_lang
from ._pages import parse_pages

log = logging.getLogger("czytajpdf")


def make_searchable(
    path: str | Path | bytes | BinaryIO,
    output: str | os.PathLike,
    *,
    lang: str = "pl",
    pages: str | int | Iterable[int] | None = None,
    force: bool = False,
    min_chars: int = 40,
    preprocess: bool | str | Iterable[str] = False,
    password: str | None = None,
    dpi: int = 300,
    tessdata_dir: str | Path | None = None,
    offline: bool | None = None,
) -> list[int]:
    """Write ``output`` as a copy of the PDF in which scanned or garbled pages gain a searchable text layer.

    Pages with a good text layer are copied untouched (unless ``force=True``). When no geometry-changing
    pre-processing (rotate/deskew) is requested the invisible text is overlaid on the *original* page;
    otherwise the page is replaced by the straightened image with its text layer.
    Returns the 1-based numbers of the pages that were OCR'd. Tesseract only.
    """
    try:
        from tesserocr import PSM, PyTessBaseAPI
    except ImportError as exc:
        raise MissingDependencyError("make_searchable requires czytajpdf[ocr]") from exc
    from ._ocr import _render, open_pdf

    spec = parse_lang(lang)
    steps = _preprocess.normalize_steps(preprocess)
    geometry = bool({"rotate", "deskew"} & set(steps))
    source = _core.load_source(path)

    with ExitStack() as stack:
        native = _core.open_backend("pypdf", stack, source, password)
        selected = parse_pages(pages, len(native))
        todo = [i for i in selected if force or _core.needs_ocr(native.text(i), min_chars, spec)]
        reader = native._reader  # same decrypted reader, reused for copying pages
        writer = PdfWriter(clone_from=reader)
        replacements: dict[int, object] = {}
        layers: list[PdfReader] = []  # keep alive until the file is written
        if todo:
            codes = list(spec.tess) + (["osd"] if "rotate" in steps else [])
            model_dir = _models.resolve(codes, tessdata_dir, offline)
            pdf = stack.enter_context(open_pdf(source, password))
            workdir = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix="czytajpdf-")))
            api = stack.enter_context(PyTessBaseAPI(path=str(model_dir), lang="+".join(spec.tess), psm=PSM.AUTO))
            api.SetVariable("tessedit_create_pdf", "1")
            api.SetVariable("textonly_pdf", "0" if geometry else "1")
            osd = None
            if "rotate" in steps:
                from ._tesseract import detect_rotation

                osd = lambda image: detect_rotation(model_dir, image)  # noqa: E731

            for index in todo:
                page = pdf[index]
                try:
                    image = _preprocess.apply(_render(page, dpi), steps, osd)
                finally:
                    page.close()
                image_path = workdir / f"p{index}.png"
                image.save(image_path, dpi=(dpi, dpi))
                base = str(workdir / f"p{index}")
                api.ClearAdaptiveClassifier()
                if not api.ProcessPages(base, str(image_path)):
                    log.warning("OCR failed on page %d; leaving it unchanged", index + 1)
                    continue
                layer_reader = PdfReader(base + ".pdf")
                layers.append(layer_reader)
                layer = layer_reader.pages[0]
                original = writer.pages[index]
                rotated = int(original.get("/Rotate", 0) or 0) % 360
                if geometry or rotated:
                    replacements[index] = layer
                else:
                    box = original.cropbox
                    sx = float(box.width) / float(layer.mediabox.width)
                    sy = float(box.height) / float(layer.mediabox.height)
                    original.merge_transformed_page(
                        layer, Transformation().scale(sx, sy).translate(float(box.left), float(box.bottom))
                    )
        for index, layer in replacements.items():
            writer.insert_page(layer, index)
            writer.remove_page(index + 1)
        writer.write(output)
    return [i + 1 for i in todo]
