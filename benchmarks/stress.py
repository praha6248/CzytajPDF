"""Synthetic stress benchmark: full-page scans with typical defects, with no pre-processing, --preprocess (rotate+deskew) and --preprocess rotate,deskew,denoise.

Unlike score.py (clean heading crops of real archival scans) this renders whole pages itself, so the
ground truth is exact and the run is reproducible offline once models are cached.
Run: python benchmarks/stress.py > benchmarks/stress_results.json   (needs czytajpdf[ocr], DejaVu or Times font)
"""

import io
import json
import random
import unicodedata
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from czytajpdf import extract

FONTS = ("/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf", "C:/Windows/Fonts/times.ttf",
         "/Library/Fonts/Times New Roman.ttf")
PL = ["ROZPORZĄDZENIE MINISTRA SPRAWIEDLIWOŚCI", "z dnia 5 lutego 1958 r.",
      "w sprawie składu komisji egzaminacyjnej", "oraz zasad przeprowadzania egzaminu państwowego.",
      "§ 1. Komisja składa się z przewodniczącego,", "jego zastępcy i trzech członków powołanych",
      "przez Ministra na okres dwóch lat."]
EN = ["The Court granted certiorari to decide", "whether the Fourteenth Amendment bars",
      "criminal prosecution of the petitioner", "under the statute as construed below.",
      "Justice Black delivered the opinion of", "the Court, which is reproduced in part."]


def font(size):
    path = next((p for p in FONTS if Path(p).exists()), None)
    if path is None:
        raise SystemExit("no TrueType font found; edit FONTS")
    return ImageFont.truetype(path, size)


def render(lines, size=38, columns=1):
    image = Image.new("RGB", (1654, 2339), "white")
    draw = ImageDraw.Draw(image)
    f = font(size)
    width = 1654 - 300
    for i, line in enumerate(lines):
        col, row = (i % columns, i // columns) if columns > 1 else (0, i)
        draw.text((150 + col * width // columns, 200 + row * 80), line, font=f, fill="black")
    return image


def noisy(image, amount=25, seed=1):
    rng = random.Random(seed)
    px = image.load()
    for _ in range(image.width * image.height // 90):
        x, y = rng.randrange(image.width), rng.randrange(image.height)
        v = rng.randrange(0, 255 - amount * 2)
        px[x, y] = (v, v, v)
    return image


CASES = [
    ("clean", "pl", PL, lambda im: im),
    ("skew 2°", "pl", PL, lambda im: im.rotate(2, fillcolor="white", resample=Image.BICUBIC)),
    ("skew 4° + blur", "pl", PL, lambda im: im.rotate(4, fillcolor="white", resample=Image.BICUBIC).filter(ImageFilter.GaussianBlur(1.1))),
    ("rotated 90°", "pl", PL, lambda im: im.rotate(90, expand=True, fillcolor="white")),
    ("upside down", "pl", PL, lambda im: im.rotate(180, fillcolor="white")),
    ("speckle noise", "pl", PL, lambda im: noisy(im)),
    ("low contrast", "pl", PL, lambda im: im.point(lambda v: 150 + v // 3)),
    ("clean", "en", EN, lambda im: im),
    ("skew 3° + noise", "en", EN, lambda im: noisy(im.rotate(3, fillcolor="white", resample=Image.BICUBIC), seed=2)),
]


def norm(text):
    return " ".join(unicodedata.normalize("NFC", text).split())


def distance(a, b):
    row = list(range(len(b) + 1))
    for i, left in enumerate(a, 1):
        following = [i]
        for j, right in enumerate(b, 1):
            following.append(min(row[j] + 1, following[-1] + 1, row[j - 1] + (left != right)))
        row = following
    return row[-1]


def run(lang, reference, image, preprocess):
    buffer = io.BytesIO()
    image.save(buffer, "PDF", resolution=200)
    page, = extract(buffer.getvalue(), ocr=True, lang=lang, preprocess=preprocess).pages
    text = norm(page.text)
    return dict(cer=round(100 * distance(reference, text) / len(reference), 2),
                wer=round(100 * distance(reference.split(), text.split()) / len(reference.split()), 2),
                confidence=round(page.confidence or 0, 1))


if __name__ == "__main__":
    rows = []
    for name, lang, lines, damage in CASES:
        reference = norm("\n".join(lines))
        image = damage(render(lines))
        rows.append(dict(case=name, lang=lang, chars=len(reference),
                         plain=run(lang, reference, image, False), preprocess=run(lang, reference, image, True),
                         preprocess_denoise=run(lang, reference, image, "rotate,deskew,denoise")))
    print(json.dumps(rows, ensure_ascii=False, indent=2))
