# CzytajPDF

[![CI](https://github.com/praha6248/CzytajPDF/actions/workflows/ci.yml/badge.svg)](https://github.com/praha6248/CzytajPDF/actions/workflows/ci.yml)

[Polska wersja (README.md)](README.md)

**Polish and English PDFs and scanned attachments in a single Python call.** CzytajPDF reads documents page by page. When a letter has an embedded text layer and an attachment is a scan, it returns one unified result recording where each page's text came from. Optional spelling repair fixes OCR artifacts and reconciles uncertain words while preserving the original OCR text for auditing.

## Packages in this repository

One repository provides the shared core library plus two language-specific packages with preset defaults:

- **`czytajpdf`** — unified library with `lang="pl"` (default) or `lang="en"`
- **`readpdf-pl`** (`packages/readpdf-pl`) — Polish default wrapper (`lang="pl"`)
- **`readpdf-en`** (`packages/readpdf-en`) — English default wrapper (`lang="en"`, no `morfeusz2` dependency)

## Quick start

Python 3.10+. Install from GitHub with OCR and spelling repair:

```sh
# Polish and English (full install)
python -m pip install 'czytajpdf[ocr,polish] @ git+https://github.com/praha6248/CzytajPDF.git'

# English only (no morfeusz2)
python -m pip install 'czytajpdf[ocr,english] @ git+https://github.com/praha6248/CzytajPDF.git'
```

```python
from czytajpdf import extract

en_doc = extract("filing-with-exhibits.pdf", ocr=True, correct=True, lang="en")
for page in en_doc.pages:
    print(page.number, page.source, page.text)

pl_doc = extract("pismo-z-zalacznikami.pdf", ocr=True, correct=True, lang="pl")
```

For digitally generated PDFs, install the base package without extras and call `extract("document.pdf")`. The concatenated text is available as `doc.text`. Page numbering starts at 1. Language-specific wrappers expose `from readpdf_en import extract` and `from readpdf_pl import extract`.

## Extraction statistics

| Document | Language | Pages | From text layer | From OCR | OCR characters |
| --- | --- | ---: | ---: | ---: | ---: |
| [Dz.U. 2024 poz. 1](https://api.sejm.gov.pl/eli/acts/DU/2024/1/text.pdf) | `pl` | 8 | 8 | 0 | 0 |
| [Dz.U. 1945 nr 5 poz. 17](https://api.sejm.gov.pl/eli/acts/DU/1945/17/text.pdf) | `pl` | 2 | 2 | 0 | 0 |
| Mixed PDF from the first pages of both Polish documents | `pl` | 2 | 1 | 1 | 2716 |
| [SCOTUS No. 22-451](https://www.supremecourt.gov/opinions/23pdf/22-451_7m58.pdf) | `en` | 114 | 114 | 0 | 0 |
| [Brown v. Board of Education, 347 U.S. 483](https://cdn.loc.gov/service/ll/usrep/usrep347/usrep347483/usrep347483.pdf) | `en` | 14 | 14 | 0 | 0 |
| Mixed PDF from the first pages of both English documents | `en` | 2 | 1 | 1 | 2204 |

## Polish OCR spelling repair benchmark

The Polish benchmark covers headings from 18 archival scans of *Dziennik Ustaw*. On the original 12-heading sample, **word errors dropped from 79 to 2** using the exact same cropped images and ground-truth transcriptions.

| Sample and library version | Character errors (CER) after repair | Word errors (WER) after repair |
| --- | ---: | ---: |
| 12 original headings · 0.1.0, RapidOCR | 382 / 2129 · 17.94% | 79 / 293 · 26.96% |
| Same 12 headings · 0.2.0 / 0.3.0, Tesseract | 2 / 2129 · 0.09% | 2 / 293 · 0.68% |
| 3 additional headings used to verify hyphenated line-break handling · 0.2.0 / 0.3.0 | 0 / 593 · 0.00% | 0 / 87 · 0.00% |
| 3 separate headings used for final validation · 0.2.0 / 0.3.0 | 1 / 430 · 0.23% | 1 / 67 · 1.49% |

On the original 12-heading sample, raw Tesseract produced 5 word errors, and the second-resolution reconciliation + spelling repair removed 3, leaving `r.` → `r,` and `i` → `1`. On the validation set, OCR added an extra period after `lutego`.

CER and WER count character/word substitutions, insertions, and deletions against human transcriptions after normalizing whitespace while keeping punctuation and case. [0.1.0 results](benchmarks/rapidocr-0.1.0.json) · [0.2.0/0.3.0 results](benchmarks/results.json) · [Holdout sample](benchmarks/holdout.json) · [Final validation](benchmarks/validation.json) · [Scoring script](benchmarks/score.py)

## English OCR benchmark (`lang="en"`)

The English benchmark evaluates 9 archival *United States Reports* scans from the Library of Congress (1937–1989). Across the 6 main cases, post-OCR repair fixed `Amendfnent` → `Amendment` and `eriminal` → `criminal` (reducing WER from 17 to 15 out of 897 words), while making zero false-positive changes on the 3 independent validation scans.

| English sample (0.3.0, Tesseract `eng`) | Raw CER / WER | Repaired CER | Repaired WER |
| --- | ---: | ---: | ---: |
| 6 *U.S. Reports* scans (1937–1984) | 0.35% / 1.90% (17 / 897) | 17 / 5745 · 0.30% | 15 / 897 · 1.67% |
| 3 independent validation scans (1943, 1964, 1989) | 0.32% / 1.99% (6 / 301) | 6 / 1871 · 0.32% | 6 / 301 · 1.99% |

[English results](benchmarks/english_results.json) · [English validation](benchmarks/english_validation.json)

## How extraction works

- By default, `pypdf` extracts embedded text. With `ocr=True`, pages with fewer than 40 non-whitespace characters are routed to Tesseract for the chosen language (`lang="pl"` or `lang="en"`; `engine="rapidocr"` selects RapidOCR; `min_chars` changes the threshold). A long garbled text layer can still pass this threshold.
- `page.source` is `"pdf"`, `"tesseract"`, or `"rapidocr"`. An empty OCR result falls back to the PDF text layer. Output preserves page boundaries without word coordinates or table layout.
- `correct=True` enables OCR spelling repair (`wordfreq` + `Morfeusz 2` for `lang="pl"`, `wordfreq` + conservative OCR confusion rules for `lang="en"`). Tesseract can perform a second pass at 180 DPI to reconcile unrecognized words against the 300 DPI pass. The original first pass stays available in `page.raw_text`, which helps when auditing proper names.
- Recognition runs locally. On first use, Tesseract downloads the matching `tessdata_best` model (~12 MB for `pol` or ~15 MB for `eng`), verifies its SHA-256 hash, and caches it locally so subsequent runs work offline.

## License and origin

Library source code is licensed under [Apache-2.0](LICENSE). The project adapts PDF/OCR and Polish spelling repair logic from [odwolania2json](https://github.com/praha6248/odwolania2Json). OCR model weights, morphological dictionaries, and frequency lists are separate dependencies under their respective licenses.
