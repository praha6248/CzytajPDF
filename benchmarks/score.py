"""Score the twelve transcribed headings. Run with Python, czytajpdf[ocr,polish] and reportlab."""

import json
import tempfile
import unicodedata
from pathlib import Path
from urllib.request import urlopen

import pypdfium2 as pdfium
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas

from czytajpdf import extract


def distance(a, b):
    row = list(range(len(b) + 1))
    for i, left in enumerate(a, 1):
        following = [i]
        for j, right in enumerate(b, 1):
            following.append(min(row[j] + 1, following[-1] + 1, row[j - 1] + (left != right)))
        row = following
    return row[-1]


def normalize(text):
    return " ".join(unicodedata.normalize("NFC", text).split())


def measure(folder, year, top, bottom, reference):
    url = f"https://api.sejm.gov.pl/eli/acts/DU/{year}/100/text.pdf"
    with urlopen(url, timeout=60) as response, pdfium.PdfDocument(response.read()) as pdf:
        image = pdf[0].render(scale=2.5).to_pil().convert("RGB")
    # Crop coordinates were marked on previews fitted into 590 x 740 pixels.
    scale = min(590 / image.width, 740 / image.height)
    crop = image.crop((0, round(int(top) / scale), image.width, round(int(bottom) / scale)))
    path = folder / f"{year}.pdf"
    size = (crop.width / 2.5, crop.height / 2.5)
    canvas = Canvas(str(path), pagesize=size)
    canvas.drawImage(ImageReader(crop), 0, 0, *size)
    canvas.save()
    page, = extract(path, ocr=True, correct=True).pages
    raw, corrected = map(normalize, (page.raw_text, page.text))
    return dict(year=int(year), source=url, reference=reference, raw=raw, corrected=corrected,
                chars=len(reference), words=len(reference.split()),
                raw_char_errors=distance(reference, raw), corrected_char_errors=distance(reference, corrected),
                raw_word_errors=distance(reference.split(), raw.split()),
                corrected_word_errors=distance(reference.split(), corrected.split()))


if __name__ == "__main__":
    lines = Path(__file__).with_name("headings.txt").read_text(encoding="utf-8").splitlines()
    with tempfile.TemporaryDirectory() as directory:
        rows = [measure(Path(directory), *line.split("|", 3)) for line in lines]
    print(json.dumps(rows, ensure_ascii=False, indent=2))
