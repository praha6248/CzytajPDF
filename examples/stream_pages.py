"""Process a long PDF page by page without holding it all in memory."""

import sys

from czytajpdf import extract_iter

if __name__ == "__main__":
    for page in extract_iter(sys.argv[1], ocr=True, pages="1-", batch_size=8):
        print(page.number, page.source, len(page.text))
