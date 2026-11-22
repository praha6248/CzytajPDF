"""End-to-end smoke test with public Polish (Sejm ELI) and English (SCOTUS / LoC) PDFs."""

import argparse
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.request import Request, urlopen

import pypdfium2 as pdfium
from pypdf import PdfReader, PdfWriter
from pypdf.errors import DependencyError
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas

from czytajpdf import extract


def _page_image(archive: Path):
    """Return a PIL image of page 1 without its embedded text layer."""
    try:
        images = list(PdfReader(archive).pages[0].images)
        if images:
            return max((item.image for item in images), key=lambda im: im.width * im.height)
    except DependencyError:
        pass
    with pdfium.PdfDocument(archive) as pdf:
        bitmap = pdf[0].render(scale=300 / 72)
        try:
            return bitmap.to_pil().convert("RGB")
        finally:
            bitmap.close()


def download(url: str, path: Path) -> Path:
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(request, timeout=60) as response:
        path.write_bytes(response.read())
    return path


def check_mixed_pair(
    directory: Path,
    modern_url: str,
    archive_url: str,
    modern_pages: int,
    archive_pages: int,
    expected_phrase: str,
    expected_token: str,
    lang: str,
) -> None:
    modern = download(modern_url, directory / f"{lang}-modern.pdf")
    archive = download(archive_url, directory / f"{lang}-archive.pdf")
    for path, count in [(modern, modern_pages), (archive, archive_pages)]:
        pages = extract(path, ocr=True, correct=True, lang=lang).pages
        assert len(pages) == count
        assert all(page.source == "pdf" and page.text.strip() for page in pages)
        print(f"[{lang}] {path.name}: {count} pages from the text layer")

    # Keep the historical page image and omit its existing searchable layer.
    historical_page = PdfReader(archive).pages[0]
    image = _page_image(archive)
    size = (float(historical_page.mediabox.width), float(historical_page.mediabox.height))
    scan = directory / f"{lang}-scan.pdf"
    canvas = Canvas(str(scan), pagesize=size)
    canvas.drawImage(ImageReader(image), 0, 0, *size)
    canvas.showPage()
    canvas.save()
    mixed = directory / f"{lang}-mixed.pdf"
    writer = PdfWriter()
    writer.add_page(PdfReader(modern).pages[0])
    writer.add_page(PdfReader(scan).pages[0])
    writer.write(mixed)

    native = extract(mixed, lang=lang)
    assert not native.pages[1].text.strip()
    digital, scanned = extract(mixed, ocr=True, correct=True, lang=lang).pages
    assert digital == native.pages[0]
    assert scanned.number == 2 and scanned.source == "tesseract"
    assert expected_phrase in scanned.raw_text.upper()
    assert expected_token in scanned.text
    print(f"[{lang}] Mixed PDF: pdf + tesseract, {len(scanned.raw_text)} OCR characters")
    for before, after in zip(scanned.raw_text.split(), scanned.text.split()):
        if before != after:
            print(f"  {before} -> {after}")


def check_polish(directory: Path) -> None:
    check_mixed_pair(
        directory,
        "https://api.sejm.gov.pl/eli/acts/DU/2024/1/text.pdf",
        "https://api.sejm.gov.pl/eli/acts/DU/1945/17/text.pdf",
        8,
        2,
        "DZIENNIK USTAW",
        "1945",
        "pl",
    )


def check_english(directory: Path) -> None:
    check_mixed_pair(
        directory,
        "https://www.supremecourt.gov/opinions/23pdf/22-451_7m58.pdf",
        "https://cdn.loc.gov/service/ll/usrep/usrep347/usrep347483/usrep347483.pdf",
        114,
        14,
        "BOARD OF EDUCATION",
        "1954",
        "en",
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--lang", choices=["pl", "en", "all"], default="all")
    selected = parser.parse_args().lang
    with TemporaryDirectory() as folder:
        tmp = Path(folder)
        if selected in ("pl", "all"):
            check_polish(tmp)
        if selected in ("en", "all"):
            check_english(tmp)
