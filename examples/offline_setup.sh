#!/bin/sh
# One-off, while online: fetch models into a folder you can copy to an air-gapped machine.
czytajpdf download-models --lang pl en --osd --dir ./tessdata
# Later, with no network:
CZYTAJPDF_TESSDATA=./tessdata czytajpdf skan.pdf --ocr --lang pl
