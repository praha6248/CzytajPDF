# readpdf-en

Python library and CLI for page-wise extraction of hybrid English PDFs — native text layer via `pypdf`, automatic fallback to local OCR (`tesserocr` / `rapidocr`) on missing or garbled pages, and dual-resolution English OCR repair while keeping `source` and `raw_text` per page (part of [CzytajPDF](https://github.com/praha6248/CzytajPDF), created on the basis of [odwolania2json](https://github.com/praha6248/odwolania2Json)).

```sh
python -m pip install 'readpdf-en[all]'
```

```sh
readpdf-en filing-with-exhibits.pdf --ocr --correct --json
```

```python
from readpdf_en import extract

doc = extract("filing-with-exhibits.pdf", ocr=True, correct=True)
for page in doc.pages:
    print(page.number, page.source, page.text)
```

`extract(...)` accepts a file path (`str | Path`), `bytes`, or a binary stream (`BinaryIO`). For born-digital PDFs with an embedded text layer, `pip install readpdf-en` suffices without OCR dependencies. See [CzytajPDF](https://github.com/praha6248/CzytajPDF) for full documentation, RAG examples, and benchmarks.
