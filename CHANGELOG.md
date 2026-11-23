# Changelog

## 0.5.0

- **CLI:** many inputs (files, directories, globs), `-o/--output`, `--format txt|json|md`, `--pages`, `--progress`, `--skip-existing`, `--fail-fast`, `--min-confidence`, `--workers`, `--preprocess`, `--cache`, `--password`, `--backend`, `--model-dir`, `--offline`, `--suggest`, `--searchable`, and a `download-models` command. Exit status `1` when any file failed.
- **Searchable PDFs:** `make_searchable()` / `--searchable` adds an invisible Tesseract text layer to scanned pages.
- **Richer results:** `Page.confidence`, `Page.words` (bounding boxes), `Page.lang`, `Page.width/height`, `Page.corrections`; `Document.low_confidence_pages()`, `to_dict()/to_json()/to_markdown()`.
- **Performance:** `workers=N` for parallel OCR, on-disk `cache=`.
- **Pre-processing:** rotation (OSD), deskew, denoise, binarize.
- **`correct="suggest"`** reports changes without applying them.
- **Native text backends:** `backend="pdfium"`.
- **Languages:** `pl+en`, `auto`, and any Tesseract language (de, fr, es, it, cs, uk, ru, pt, nl, sk, la have pinned checksums).
- **Streaming:** `extract_iter()`; page selection via `pages=`.
- **Integrations:** `Document.chunks()`, `to_langchain()`, `to_llamaindex()`.
- **Offline use:** `tessdata_dir=`, `CZYTAJPDF_TESSDATA`, `offline=`, `CZYTAJPDF_OFFLINE`, `download_models()`.
- **Hygiene:** `py.typed`, exception hierarchy, `password=`, `logging`, `examples/`, synthetic stress benchmark.
- **Breaking (internal):** `czytajpdf._ocr.recognize` now takes an `OcrOptions` and returns `OcrPage` objects; `extract()`'s public signature is backwards compatible. `lang` is no longer restricted to `pl`/`en`. `readpdf-pl`/`readpdf-en` forward all `extract()` keywords.

## 0.4.0

Earlier releases: see the Git history.
