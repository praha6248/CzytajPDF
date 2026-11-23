# CzytajPDF

[![CI](https://github.com/praha6248/CzytajPDF/actions/workflows/ci.yml/badge.svg)](https://github.com/praha6248/CzytajPDF/actions/workflows/ci.yml)

[Polska wersja (README.md)](README.md)

**Polish and English PDFs and scanned attachments in a single Python call or CLI command.** CzytajPDF reads documents page by page. When a letter has an embedded text layer and an attachment is a scan (or its embedded text layer is garbled), it returns one unified result recording where each page's text came from. Optional spelling repair fixes OCR artifacts and reconciles uncertain words while preserving the original OCR text for auditing.

## Packages in this repository

One repository provides the shared core library plus two language-specific packages with preset defaults:

- **`czytajpdf`** — unified library & CLI with `lang="pl"` (default) or `lang="en"`
- **`readpdf-pl`** (`packages/readpdf-pl`) — Polish default wrapper & CLI (`lang="pl"`)
- **`readpdf-en`** (`packages/readpdf-en`) — English default wrapper & CLI (`lang="en"`, no `morfeusz2` dependency)

## Quick start

Python 3.10+. Install from PyPI with OCR and spelling repair:

```sh
# Polish and English (full install)
python -m pip install 'czytajpdf[ocr,polish]'

# English only (no morfeusz2)
python -m pip install 'czytajpdf[ocr,english]'

# Or use the language-specific packages:
python -m pip install 'readpdf-en[all]'
python -m pip install 'readpdf-pl[all]'
```

### Command-line interface (CLI)

```sh
czytajpdf filing-with-exhibits.pdf --ocr --correct --lang en --json
cat scan.pdf | readpdf-en - --ocr --correct
```

### Python (file path, `bytes`, or `BinaryIO` stream)

```python
from czytajpdf import extract

en_doc = extract("filing-with-exhibits.pdf", ocr=True, correct=True, lang="en")
for page in en_doc.pages:
    print(page.number, page.source, page.text)

# In-memory HTTP upload / S3 bytes without temporary files:
with open("attachment.pdf", "rb") as f:
    from_bytes = extract(f.read(), ocr=True, correct=True, lang="en")
```

For digitally generated PDFs, install the base package without extras (`pip install czytajpdf`) and call `extract("document.pdf")`. The concatenated text is available as `doc.text`. Page numbering starts at 1. Language-specific wrappers expose `from readpdf_en import extract` and `from readpdf_pl import extract`.

## RAG / LLM ingestion recipe (with provenance metadata)

```python
from czytajpdf import extract

doc = extract("case-bundle.pdf", ocr=True, correct=True, lang="en")
chunks = [
    {
        "text": page.text,
        "metadata": {
            "page": page.number,
            "source": page.source,        # "pdf", "tesseract", or "rapidocr"
            "raw_text": page.raw_text,    # pre-repair OCR text for auditing proper names
        },
    }
    for page in doc.pages if page.text.strip()
]
```

## Real-scan before & after examples

- **Dziennik Ustaw 1945 (mixed Polish PDF)**: `ponadkontyugentowych` → `ponadkontyngentowych`
- **Dziennik Ustaw 1958 (300/180 DPI reconciliation)**: `KOZPORZĄDZENIE ... w sprawie skiadu` → `ROZPORZĄDZENIE ... w sprawie składu`
- **U.S. Reports — Brown v. Board of Education (1954)**: `Amendfnent` → `Amendment`; **Roe v. Wade (1973)**: `eriminal` → `criminal`
- **Garbled text layers**: pages emitting `(cid:...)` tokens, `\ufffd`/control/PUA garbage, or unreadable text are routed to OCR automatically even when longer than `min_chars`.

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
| Same 12 headings · 0.2.0+, Tesseract | 2 / 2129 · 0.09% | 2 / 293 · 0.68% |
| 3 additional headings used to verify hyphenated line-break handling · 0.2.0+ | 0 / 593 · 0.00% | 0 / 87 · 0.00% |
| 3 separate headings used for final validation · 0.2.0+ | 1 / 430 · 0.23% | 1 / 67 · 1.49% |

On the original 12-heading sample, raw Tesseract produced 5 word errors, and the second-resolution reconciliation + spelling repair removed 3, leaving `r.` → `r,` and `i` → `1`. On the validation set, OCR added an extra period after `lutego`.

CER and WER count character/word substitutions, insertions, and deletions against human transcriptions after normalizing whitespace while keeping punctuation and case. [0.1.0 results](benchmarks/rapidocr-0.1.0.json) · [0.2.0+ results](benchmarks/results.json) · [Holdout sample](benchmarks/holdout.json) · [Final validation](benchmarks/validation.json) · [Scoring script](benchmarks/score.py)

## English OCR benchmark (`lang="en"`)

The English benchmark evaluates 9 archival *United States Reports* scans from the Library of Congress (1937–1989). Across the 6 main cases, post-OCR repair fixed `Amendfnent` → `Amendment` and `eriminal` → `criminal` (reducing WER from 17 to 15 out of 897 words), while making zero false-positive changes on the 3 independent validation scans.

| English sample (Tesseract `eng`) | Raw CER / WER | Repaired CER | Repaired WER |
| --- | ---: | ---: | ---: |
| 6 *U.S. Reports* scans (1937–1984) | 0.35% / 1.90% (17 / 897) | 17 / 5745 · 0.30% | 15 / 897 · 1.67% |
| 3 independent validation scans (1943, 1964, 1989) | 0.32% / 1.99% (6 / 301) | 6 / 1871 · 0.32% | 6 / 301 · 1.99% |

[English results](benchmarks/english_results.json) · [English validation](benchmarks/english_validation.json)

## What's new in 0.5

### Batch CLI

```sh
czytajpdf akta/ --ocr --correct --workers 4 --preprocess -o out/ --format md --progress
czytajpdf 'scans/**/*.pdf' --ocr --pages 1-5 --min-confidence 70 --skip-existing -o out/
czytajpdf scan.pdf --ocr --searchable -o out/        # out/scan.searchable.pdf with a text layer
czytajpdf download-models --lang pl en --osd --dir ./tessdata
```

Inputs may be files, directories (recursive), globs or `-`. One failing file does not stop the rest (unless `--fail-fast`); the exit status is `1` if anything failed. Without `-o`, several inputs go to stdout (`--json` emits JSON Lines). Formats: `txt`, `json` (add `--words` for word boxes), `md`.

### API

```python
from czytajpdf import extract, extract_iter, make_searchable, download_models

doc = extract("file.pdf", ocr=True, correct="suggest", lang="auto", pages="1-20,25-",
              workers=4, preprocess=True, cache=True, password=None, backend="pdfium")
page = doc.pages[0]
page.confidence, page.lang, page.width, page.height   # mean OCR confidence (0-100), language, size in points
page.words        # Word(text, bbox=(x0, y0, x1, y1) in points from the top-left, confidence)
page.corrections  # Correction(raw, fixed, offset); with correct="suggest" `text` stays raw
doc.low_confidence_pages(70)

for page in extract_iter("500-pages.pdf", ocr=True):  # stream pages without holding the whole result
    ...

make_searchable("scan.pdf", "scan-ocr.pdf", lang="en")   # invisible text layer over the original pages
download_models(["pl", "en"], "./tessdata", include_osd=True)

chunks = doc.chunks(max_chars=1200, overlap=150)         # metadata: page, source, confidence, lang, corrected
docs = doc.to_langchain(max_chars=1200)                  # pip install 'czytajpdf[langchain]'
docs = doc.to_llamaindex()                               # pip install 'czytajpdf[llamaindex]'
```

- **Languages:** `lang="pl"`, `"en"`, `"pl+en"`, `"auto"` (Polish+English, detected per page) or any Tesseract language (`"de"`, `"fra"`, `"uk"`, …). Spelling repair covers `pl` and `en`; in mixed text, words valid in the other language are protected.
- **Pre-processing:** `preprocess=True` fixes 90/180/270° rotation and skew; or pass `"rotate,deskew,denoise,binarize"`. `words` coordinates refer to the processed image.
- **Performance:** `workers=N` runs N OCR processes (scripts need an `if __name__ == "__main__":` guard). `cache=True` (or a directory) skips re-OCR of unchanged pages (key: PDF content, page, options).
- **Offline:** `czytajpdf download-models` fetches and verifies models; then use `tessdata_dir=` / `CZYTAJPDF_TESSDATA` (a folder of `*.traineddata`, never downloads) or `offline=True` / `CZYTAJPDF_OFFLINE=1`.
- **Text backend:** `backend="pdfium"` is often faster than `pypdf` and orders text better.
- **Errors:** `CzytajPDFError` and subclasses (`InvalidPDFError`, `PasswordRequiredError`, `MissingDependencyError`, `ModelNotFoundError`) also inherit `ValueError`/`ImportError`/`OSError`. Logs go to `logging.getLogger("czytajpdf")` (`-v` in the CLI). AES-encrypted PDFs need `czytajpdf[crypto]`.

### Stress benchmark (synthetic full pages)

CER of Tesseract OCR on rendered pages with common defects. [Script](benchmarks/stress.py) · [results](benchmarks/stress_results.json). Real scans can be harder: this is a regression test and a demonstration of pre-processing, not a quality guarantee.

| Case | Lang | No pre-processing | `preprocess=True` | `rotate,deskew,denoise` |
| --- | --- | ---: | ---: | ---: |
| clean | `pl` | 0.36% | 0.36% | 0.36% |
| skew 2° | `pl` | 0.36% | 0.36% | 0.36% |
| skew 4° + blur | `pl` | 27.74% | 0.36% | 0.36% |
| rotated 90° | `pl` | 89.42% | 0.36% | 0.36% |
| upside down | `pl` | 89.78% | 0.36% | 0.36% |
| speckle noise | `pl` | 14.60% | 14.60% | 0.73% |
| low contrast | `pl` | 0.36% | 0.36% | 0.36% |
| clean | `en` | 0.00% | 0.00% | 0.00% |
| skew 3° + noise | `en` | 33.19% | 12.50% | 0.00% |

### Editing PDFs (replace words)

```sh
czytajpdf edit contract.pdf --list contract        # numbered occurrences with context
czytajpdf edit contract.pdf new.pdf -s 5="agreement"  # only the chosen occurrence (id from --list)
czytajpdf edit contract.pdf new.pdf -r "John=Jonathan" -r "2024=2025" --page 1
czytajpdf edit scan.pdf new.pdf -r February=March --ocr   # scans: words come from OCR
```

```python
from czytajpdf import find_words, edit_pdf

hits = find_words("contract.pdf", "contract")        # WordMatch: id, page, text, bbox, context
edit_pdf("contract.pdf", "new.pdf", {hits[1]: "agreement"})   # one chosen occurrence
edit_pdf("contract.pdf", "new.pdf", {"John": "Jonathan"})     # every occurrence
```

- **Text layer:** the text run holding the word is rebuilt with the new word in the same place, size and colour. The old text is gone (search and copy see the new word). The rest of that run gets the replacement font (`font=` or a system font with Polish letters).
- **Scans (`--ocr`):** the old word is covered with a patch in the sampled background colour and the new one is drawn on top. This is a visual edit: the scanned image underneath still holds the old pixels, so it is not a redaction.
- The `EditReport` shows the method used for each change and what was skipped. Rotated pages are skipped. Output is written unencrypted and the input is never modified.

## How extraction works

- By default, `pypdf` extracts embedded text. With `ocr=True`, pages with fewer than 40 non-whitespace characters or a garbled text layer (e.g. `(cid:...)` markers, replacement/control/PUA characters, low alphanumeric share, vowel-less gibberish, or low known-word share when a language lexicon is installed) are routed to Tesseract for the chosen language (`lang="pl"` or `lang="en"`; `engine="rapidocr"` selects RapidOCR; `min_chars` changes the length threshold).
- `page.source` is `"pdf"`, `"tesseract"`, or `"rapidocr"`. An empty OCR result falls back to the PDF text layer. Output preserves page boundaries without word coordinates or table layout.
- `correct=True` enables OCR spelling repair (`wordfreq` + `Morfeusz 2` for `lang="pl"`, `wordfreq` + conservative OCR confusion rules for `lang="en"`). Tesseract can perform a second pass at 180 DPI to reconcile unrecognized words against the 300 DPI pass. The original first pass stays available in `page.raw_text`, which helps when auditing proper names.
- Recognition runs locally. On first use, Tesseract downloads the matching `tessdata_best` model (~12 MB for `pol` or ~15 MB for `eng`), verifies its SHA-256 hash, and caches it locally so subsequent runs work offline.

## License and origin

Library source code is licensed under [Apache-2.0](LICENSE). Created on the basis of PDF extraction, OCR, and spelling-repair logic built in [odwolania2json](https://github.com/praha6248/odwolania2Json). OCR model weights, morphological dictionaries, and frequency lists are separate dependencies under their respective licenses.
