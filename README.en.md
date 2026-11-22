# CzytajPDF

[![CI](https://github.com/praha6248/CzytajPDF/actions/workflows/ci.yml/badge.svg)](https://github.com/praha6248/CzytajPDF/actions/workflows/ci.yml)

[Polska wersja (README.md)](README.md)

**Polish PDFs and scanned attachments in a single Python call.** CzytajPDF reads documents page by page. When a letter has an embedded text layer and an attachment is a scan, it returns one unified result recording where each page's text came from. Optional spelling repair restores Polish diacritics and reconciles uncertain words while preserving the original OCR text for auditing.

## Quick start

Python 3.10+. Install from GitHub with OCR and Polish spelling repair:

```sh
python -m pip install 'czytajpdf[ocr,polish] @ git+https://github.com/praha6248/CzytajPDF.git'
```

```python
from czytajpdf import extract

doc = extract("letter-with-attachments.pdf", ocr=True, correct=True)
for page in doc.pages:
    print(page.number, page.source, page.text)
```

For digitally generated PDFs, install the base package without extras and call `extract("document.pdf")`. The concatenated text is available as `doc.text`. Page numbering starts at 1.

## Extraction statistics

| Document | Pages | From text layer | From OCR | OCR characters |
| --- | ---: | ---: | ---: | ---: |
| [Dz.U. 2024 poz. 1](https://api.sejm.gov.pl/eli/acts/DU/2024/1/text.pdf) | 8 | 8 | 0 | 0 |
| [Dz.U. 1945 nr 5 poz. 17](https://api.sejm.gov.pl/eli/acts/DU/1945/17/text.pdf) | 2 | 2 | 0 | 0 |
| Mixed PDF from the first pages of both documents | 2 | 1 | 1 | 2716 |

## Polish OCR spelling repair benchmark

The benchmark covers headings from 18 archival scans of the Polish Journal of Laws (*Dziennik Ustaw*). On the original 12-heading sample, **word errors dropped from 79 to 2** using the exact same cropped images and ground-truth transcriptions.

| Sample and library version | Character errors (CER) after repair | Word errors (WER) after repair |
| --- | ---: | ---: |
| 12 original headings · 0.1.0, RapidOCR | 382 / 2129 · 17.94% | 79 / 293 · 26.96% |
| Same 12 headings · 0.2.0, Tesseract | 2 / 2129 · 0.09% | 2 / 293 · 0.68% |
| 3 additional headings used to verify hyphenated line-break handling · 0.2.0 | 0 / 593 · 0.00% | 0 / 87 · 0.00% |
| 3 separate headings used for final validation · 0.2.0 | 1 / 430 · 0.23% | 1 / 67 · 1.49% |

On the original 12-heading sample, raw Tesseract produced 5 word errors, and the second-resolution reconciliation + spelling repair removed 3, leaving `r.` → `r,` and `i` → `1`. On the validation set, OCR added an extra period after `lutego`.

CER and WER count character/word substitutions, insertions, and deletions against human transcriptions after normalizing whitespace while keeping punctuation and case. Results apply to cropped printed legal headings. [0.1.0 results](benchmarks/rapidocr-0.1.0.json) · [0.2.0 results](benchmarks/results.json) · [Holdout sample](benchmarks/holdout.json) · [Final validation](benchmarks/validation.json) · [Scoring script](benchmarks/score.py)

## How extraction works

- By default, `pypdf` extracts embedded text. With `ocr=True`, pages with fewer than 40 non-whitespace characters are routed to the Polish Tesseract model (`engine="rapidocr"` selects RapidOCR; `min_chars` changes the threshold). A long garbled text layer can still pass this threshold.
- `page.source` is `"pdf"`, `"tesseract"`, or `"rapidocr"`. An empty OCR result falls back to the PDF text layer. Output preserves page boundaries without word coordinates or table layout.
- `correct=True` enables dictionary-based spelling repair using `wordfreq` and `Morfeusz 2`. Tesseract can also perform a second pass at 180 DPI to reconcile unrecognized words against the 300 DPI pass. The original first pass stays available in `page.raw_text`, which helps when auditing proper names.
- Recognition runs locally. On first use, Tesseract downloads the Polish `tessdata_best` model (~12 MB), verifies its SHA-256 hash, and caches it locally so subsequent runs work offline.

## License and origin

Library source code is licensed under [Apache-2.0](LICENSE). The project adapts PDF/OCR and Polish spelling repair logic from [odwolania2json](https://github.com/praha6248/odwolania2Json). OCR model weights, morphological dictionaries, and frequency lists are separate dependencies under their respective licenses.
