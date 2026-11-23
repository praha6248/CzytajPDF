"""Scan a folder of PDFs in parallel and build RAG chunks (run: python batch_to_rag.py akta/)."""

import sys
from pathlib import Path

from czytajpdf import extract


def main(folder: str) -> None:
    for pdf in sorted(Path(folder).rglob("*.pdf")):
        doc = extract(pdf, ocr=True, correct="suggest", lang="auto", workers=4, preprocess=True, cache=True)
        for page in doc.low_confidence_pages(70):
            print(f"{pdf.name}: page {page.number} has low OCR confidence ({page.confidence:.0f}%)")
        chunks = doc.chunks(max_chars=1200, overlap=150)
        print(f"{pdf.name}: {len(doc.pages)} pages -> {len(chunks)} chunks")


if __name__ == "__main__":  # required when workers > 1
    main(sys.argv[1])
