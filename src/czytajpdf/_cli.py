"""Command-line interface for czytajpdf, readpdf-pl, and readpdf-en."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import sys
from typing import Literal, Sequence

from . import extract


def _build_parser(prog: str | None, default_lang: Literal["pl", "en"]) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=prog,
        description="Extract text from hybrid Polish and English PDFs with optional local OCR and spelling repair.",
    )
    parser.add_argument("path", help="Path to a PDF file, or '-' to read PDF bytes from stdin.")
    parser.add_argument("--ocr", action="store_true", help="Run local OCR on missing, short, or garbled pages.")
    parser.add_argument("--correct", action="store_true", help="Repair OCR spelling mistakes (requires --ocr).")
    parser.add_argument(
        "--lang",
        choices=("pl", "en"),
        default=default_lang,
        help=f"Document language for OCR and spelling repair (default: {default_lang}).",
    )
    parser.add_argument(
        "--engine",
        choices=("tesseract", "rapidocr"),
        default="tesseract",
        help="OCR engine to use when --ocr is enabled (default: tesseract).",
    )
    parser.add_argument(
        "--min-chars",
        type=int,
        default=40,
        help="Minimum non-whitespace characters before OCR fallback runs (default: 40).",
    )
    parser.add_argument("--json", action="store_true", help="Emit page provenance and text as JSON.")
    return parser


def main(argv: Sequence[str] | None = None, *, default_lang: Literal["pl", "en"] = "pl",
         prog: str | None = None) -> int:
    """CLI entrypoint returning process exit status."""
    parser = _build_parser(prog, default_lang)
    args = parser.parse_args(argv)
    if args.correct and not args.ocr:
        parser.error("--correct requires --ocr")
    source = sys.stdin.buffer.read() if args.path == "-" else args.path
    try:
        doc = extract(
            source,
            ocr=args.ocr,
            correct=args.correct,
            min_chars=args.min_chars,
            engine=args.engine,
            lang=args.lang,
        )
    except (OSError, ValueError, TypeError, ImportError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.json:
        payload = {"pages": [asdict(page) for page in doc.pages], "text": doc.text}
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(doc.text)
    return 0


def main_pl(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint for readpdf-pl."""
    return main(argv, default_lang="pl", prog="readpdf-pl")


def main_en(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint for readpdf-en."""
    return main(argv, default_lang="en", prog="readpdf-en")
