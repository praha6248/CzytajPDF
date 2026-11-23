"""Add an invisible text layer to scanned pages (run: python searchable_pdf.py skan.pdf wynik.pdf)."""

import sys

from czytajpdf import make_searchable

if __name__ == "__main__":
    ocr_pages = make_searchable(sys.argv[1], sys.argv[2], lang="pl", preprocess=True)
    print("OCR'd pages:", ocr_pages)
