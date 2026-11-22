"""End-to-end smoke test with two public documents from the Sejm ELI API."""

from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.request import urlopen

from pypdf import PdfReader, PdfWriter
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas

from czytajpdf import extract


def download(directory: Path, year: int, position: int) -> Path:
    url = f"https://api.sejm.gov.pl/eli/acts/DU/{year}/{position}/text.pdf"
    path = directory / f"{year}-{position}.pdf"
    with urlopen(url, timeout=60) as response:
        path.write_bytes(response.read())
    return path


def check(directory: Path) -> None:
    modern = download(directory, 2024, 1)
    archive = download(directory, 1945, 17)
    for path, count in [(modern, 8), (archive, 2)]:
        pages = extract(path, ocr=True, correct=True).pages
        assert len(pages) == count
        assert all(page.source == "pdf" and page.text.strip() for page in pages)
        print(f"{path.name}: {count} pages from the text layer")

    # Keep the historical page image and omit its existing searchable layer.
    historical_page = PdfReader(archive).pages[0]
    image = max((item.image for item in historical_page.images), key=lambda im: im.width * im.height)
    size = (float(historical_page.mediabox.width), float(historical_page.mediabox.height))
    scan = directory / "scan.pdf"
    canvas = Canvas(str(scan), pagesize=size)
    canvas.drawImage(ImageReader(image), 0, 0, *size)
    canvas.showPage()
    canvas.save()
    mixed = directory / "mixed.pdf"
    writer = PdfWriter()
    writer.add_page(PdfReader(modern).pages[0])
    writer.add_page(PdfReader(scan).pages[0])
    writer.write(mixed)

    native = extract(mixed)
    assert not native.pages[1].text.strip()
    digital, scanned = extract(mixed, ocr=True, correct=True).pages
    assert digital == native.pages[0]
    assert scanned.number == 2 and scanned.source == "rapidocr"
    assert "DZIENNIK USTAW" in scanned.raw_text.upper()
    assert "1945" in scanned.text
    print(f"Mixed PDF: pdf + rapidocr, {len(scanned.raw_text)} OCR characters")
    for before, after in zip(scanned.raw_text.split(), scanned.text.split()):
        if before != after:
            print(f"  {before} -> {after}")


if __name__ == "__main__":
    with TemporaryDirectory() as folder:
        check(Path(folder))
