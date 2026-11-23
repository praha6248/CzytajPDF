"""Command-line interface for czytajpdf, readpdf-pl, and readpdf-en."""

from __future__ import annotations

import argparse
import glob
import json
import logging
import sys
from pathlib import Path
from typing import Literal, Sequence

from . import Document, Page, extract_iter
from ._errors import CzytajPDFError

_EXTENSIONS = {"txt": ".txt", "json": ".json", "md": ".md"}


def _build_parser(prog: str | None, default_lang: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=prog,
        description="Extract text from hybrid Polish and English PDFs with optional local OCR and spelling repair.",
        epilog="Other commands: `%(prog)s edit IN.pdf OUT.pdf -r old=new` replaces words; `%(prog)s download-models [--lang pl en ...] [--dir DIR]` prefetches OCR models for offline use.",
    )
    parser.add_argument(
        "path", nargs="+",
        help="PDF files, directories (searched recursively), glob patterns, or '-' to read PDF bytes from stdin.",
    )
    parser.add_argument("--ocr", action="store_true", help="Run local OCR on missing, short, or garbled pages.")
    parser.add_argument("--correct", action="store_true", help="Repair OCR spelling mistakes (requires --ocr).")
    parser.add_argument("--suggest", action="store_true",
                        help="List proposed spelling fixes without applying them (requires --ocr).")
    parser.add_argument("--lang", default=default_lang,
                        help=f"pl, en, pl+en, auto, or any Tesseract language such as de (default: {default_lang}).")
    parser.add_argument("--engine", choices=("tesseract", "rapidocr"), default="tesseract",
                        help="OCR engine to use when --ocr is enabled (default: tesseract).")
    parser.add_argument("--min-chars", type=int, default=40,
                        help="Minimum non-whitespace characters before OCR fallback runs (default: 40).")
    parser.add_argument("--pages", help='Pages to read, e.g. "1-3,7,10-" (default: all).')
    parser.add_argument("--backend", choices=("pypdf", "pdfium"), default="pypdf",
                        help="Library for the native text layer (default: pypdf).")
    parser.add_argument("--password", help="Password for encrypted PDFs.")
    parser.add_argument("--workers", type=int, default=1, help="Parallel OCR processes (default: 1).")
    parser.add_argument("--preprocess", nargs="?", const="auto", default=None, metavar="STEPS",
                        help="Straighten scans before OCR: bare flag = rotate,deskew; or a list of "
                             "rotate,deskew,denoise,binarize.")
    parser.add_argument("--cache", nargs="?", const=True, default=False, metavar="DIR",
                        help="Reuse OCR results of unchanged pages (optional cache directory).")
    parser.add_argument("--model-dir", help="Directory with <code>.traineddata files; never downloads.")
    parser.add_argument("--offline", action="store_true", help="Never download models.")
    parser.add_argument("-o", "--output", metavar="DIR", help="Write one result file per input into DIR.")
    parser.add_argument("--format", choices=tuple(_EXTENSIONS), default="txt",
                        help="Output format (default: txt). With several inputs on stdout, json is JSON Lines.")
    parser.add_argument("--json", action="store_true", help="Shortcut for --format json.")
    parser.add_argument("--words", action="store_true", help="Include word boxes and confidences in JSON.")
    parser.add_argument("--searchable", action="store_true",
                        help="Also write <name>.searchable.pdf (OCR text layer added to scanned pages). "
                             "Goes to --output, or next to the input.")
    parser.add_argument("--min-confidence", type=float, metavar="PCT",
                        help="Warn on stderr about OCR pages below this mean confidence (0-100).")
    parser.add_argument("--skip-existing", action="store_true", help="Skip inputs whose output file already exists.")
    parser.add_argument("--fail-fast", action="store_true", help="Stop at the first failing file.")
    parser.add_argument("--progress", action="store_true", help="Report progress on stderr.")
    parser.add_argument("-v", "--verbose", action="store_true", help="Debug logging on stderr.")
    return parser


def _expand(patterns: Sequence[str]) -> list[str]:
    files: list[str] = []
    for pattern in patterns:
        if pattern == "-":
            files.append(pattern)
        elif Path(pattern).is_dir():
            files.extend(str(p) for p in sorted(Path(pattern).rglob("*")) if p.suffix.lower() == ".pdf")
        elif glob.has_magic(pattern):
            files.extend(sorted(glob.glob(pattern, recursive=True)))
        else:
            files.append(pattern)  # a missing file becomes a per-file error
    return files


def _render(doc: Document, fmt: str, name: str, words: bool) -> str:
    if fmt == "json":
        return doc.to_json(words=words)
    if fmt == "md":
        return doc.to_markdown(title=name)
    return doc.text


def _output_path(directory: Path, source: str, fmt: str, used: set[Path]) -> Path:
    stem = "stdin" if source == "-" else Path(source).stem
    path = directory / f"{stem}{_EXTENSIONS[fmt]}"
    counter = 2
    while path in used:
        path = directory / f"{stem}-{counter}{_EXTENSIONS[fmt]}"
        counter += 1
    used.add(path)
    return path


def _download_models(argv: Sequence[str], prog: str | None) -> int:
    parser = argparse.ArgumentParser(prog=f"{prog or 'czytajpdf'} download-models",
                                     description="Download and verify OCR models for offline use.")
    parser.add_argument("--lang", nargs="+", default=["pl", "en"], help="Languages (default: pl en).")
    parser.add_argument("--dir", help="Target directory (default: the user cache). Use it as --model-dir later.")
    parser.add_argument("--osd", action="store_true", help="Also fetch the orientation model used by --preprocess.")
    args = parser.parse_args(argv)
    from . import download_models

    try:
        target = download_models(args.lang, args.dir, include_osd=args.osd)
    except (CzytajPDFError, OSError, ValueError, ImportError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(target)
    return 0


def _edit_command(argv: Sequence[str], prog: str | None, default_lang: str) -> int:
    parser = argparse.ArgumentParser(
        prog=f"{prog or 'czytajpdf'} edit",
        description="Replace words in a PDF. List words first (--list), then pick by text or by id.",
    )
    parser.add_argument("input", help="Input PDF.")
    parser.add_argument("output", nargs="?", help="Output PDF (required unless --list).")
    parser.add_argument("--list", nargs="?", const="", metavar="QUERY",
                        help="Print numbered words (or only those matching QUERY) with context, then exit.")
    parser.add_argument("-r", "--replace", action="append", default=[], metavar="OLD=NEW",
                        help="Replace every occurrence of OLD with NEW (repeatable).")
    parser.add_argument("-s", "--select", action="append", default=[], metavar="ID=NEW",
                        help="Replace the single word with this id from `--list` (repeatable).")
    parser.add_argument("--page", type=int, help="Limit -r to one page.")
    parser.add_argument("--occurrence", type=int, help="With -r: only the n-th match (1-based).")
    parser.add_argument("--match-case", action="store_true", help="Case-sensitive matching.")
    parser.add_argument("--partial", action="store_true", help="Allow matches inside longer words.")
    parser.add_argument("--font", help="TrueType font for the new text (default: a system font with Polish letters).")
    parser.add_argument("--ocr", action="store_true", help="Also read pages without a text layer (scans) with OCR.")
    parser.add_argument("--lang", default=default_lang, help=f"OCR language (default: {default_lang}).")
    parser.add_argument("--password", help="Password for encrypted PDFs.")
    args = parser.parse_args(argv)
    from . import edit_pdf, find_words
    from ._edit import Edit

    common = dict(match_case=args.match_case, whole_word=not args.partial, ocr=args.ocr, lang=args.lang,
                  password=args.password)
    try:
        if args.list is not None:
            # ids always index the full word list, so they can be passed to --select unchanged
            query = args.list if args.match_case else args.list.lower()
            for match in find_words(args.input, None, **common):
                probe = match.text if args.match_case else match.text.lower()
                if not query or (probe == query if not args.partial else query in probe):
                    print(match)
            return 0
        if not args.output:
            parser.error("output PDF required (or use --list)")
        if not (args.replace or args.select):
            parser.error("give at least one --replace or --select")
        edits = []
        for item in args.replace:
            old, sep, new = item.partition("=")
            if not sep or not old:
                parser.error(f"--replace expects OLD=NEW, got {item!r}")
            edits.append(Edit(old, new, args.page, args.occurrence))
        replacements: dict = {}
        if args.select:
            words = find_words(args.input, None, **common)
            for item in args.select:
                ident, sep, new = item.partition("=")
                if not sep or not ident.isdigit() or int(ident) >= len(words):
                    parser.error(f"--select expects ID=NEW with an id from --list, got {item!r}")
                replacements[words[int(ident)]] = new
        report = edit_pdf(args.input, args.output, [*edits] if not replacements else {**replacements,
                          **{e.old: e.new for e in edits}}, font=args.font, **common)
    except (CzytajPDFError, OSError, ValueError, TypeError, ImportError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    for item in report.replacements:
        note = " (old text may remain in the text layer)" if item.residual else ""
        print(f"p.{item.page}: {item.old!r} -> {item.new!r} [{item.method}]{note}", file=sys.stderr)
    for what, reason in report.skipped:
        print(f"skipped {what!r}: {reason}", file=sys.stderr)
    print(f"{report.count} replacement(s) written to {args.output}", file=sys.stderr)
    return 0 if report.count else 1


def main(argv: Sequence[str] | None = None, *, default_lang: Literal["pl", "en"] = "pl",
         prog: str | None = None) -> int:
    """CLI entrypoint returning process exit status (0 ok, 1 when any file failed, 2 for usage errors)."""
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["edit"]:
        return _edit_command(argv[1:], prog, default_lang)
    if argv[:1] == ["download-models"]:
        return _download_models(argv[1:], prog)
    parser = _build_parser(prog, default_lang)
    args = parser.parse_args(argv)
    if (args.correct or args.suggest) and not args.ocr:
        parser.error("--correct/--suggest require --ocr")
    if args.correct and args.suggest:
        parser.error("--correct and --suggest are mutually exclusive")
    if args.searchable and args.engine != "tesseract":
        parser.error("--searchable works with the tesseract engine only")
    if args.json:
        args.format = "json"
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, format="%(name)s: %(message)s")

    out_dir = Path(args.output) if args.output else None
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)
    inputs = _expand(args.path)
    if not inputs:
        print("error: no PDF files matched", file=sys.stderr)
        return 1
    if args.searchable and "-" in inputs and not out_dir:
        parser.error("--searchable with stdin requires --output")

    correct: bool | str = "suggest" if args.suggest else args.correct
    options = dict(
        ocr=args.ocr, correct=correct, min_chars=args.min_chars, engine=args.engine, lang=args.lang,
        pages=args.pages, backend=args.backend, password=args.password, workers=args.workers,
        preprocess=args.preprocess or False, cache=args.cache, tessdata_dir=args.model_dir,
        offline=True if args.offline else None,
    )
    stdin_bytes = None
    failures = used = 0
    used_paths: set[Path] = set()
    multiple = len(inputs) > 1
    for number, source in enumerate(inputs, 1):
        label = "<stdin>" if source == "-" else source
        target = _output_path(out_dir, source, args.format, used_paths) if out_dir else None
        if target and args.skip_existing and target.exists():
            if args.progress:
                print(f"[{number}/{len(inputs)}] {label}: skipped (exists)", file=sys.stderr)
            continue
        try:
            if source == "-":
                stdin_bytes = sys.stdin.buffer.read() if stdin_bytes is None else stdin_bytes
            payload = stdin_bytes if source == "-" else source
            collected: list[Page] = []
            for page in extract_iter(payload, **options):
                collected.append(page)
                if args.progress:
                    print(f"[{number}/{len(inputs)}] {label}: page {page.number} ({page.source})",
                          file=sys.stderr, flush=True)
                if (args.min_confidence is not None and page.confidence is not None
                        and page.confidence < args.min_confidence):
                    print(f"warning: {label} page {page.number}: OCR confidence {page.confidence:.0f}% "
                          f"< {args.min_confidence:g}%", file=sys.stderr)
            doc = Document(tuple(collected))
            if args.searchable:
                from . import make_searchable

                searchable = (out_dir or Path(source).parent) / f"{'stdin' if source == '-' else Path(source).stem}.searchable.pdf"
                done = make_searchable(payload, searchable, lang=args.lang, pages=args.pages,
                                       min_chars=args.min_chars, preprocess=args.preprocess or False,
                                       password=args.password, tessdata_dir=args.model_dir,
                                       offline=True if args.offline else None)
                print(f"{label}: wrote {searchable} ({len(done)} page(s) OCR'd)", file=sys.stderr)
        except (CzytajPDFError, OSError, ValueError, TypeError, ImportError) as exc:
            failures += 1
            print(f"error: {label}: {exc}", file=sys.stderr)
            if args.fail_fast:
                break
            continue

        used += 1
        if target:
            target.write_text(_render(doc, args.format, label, args.words), encoding="utf-8")
        elif multiple and args.format == "json":
            data = doc.to_dict(words=args.words)
            print(json.dumps({"path": label, **data}, ensure_ascii=False))
        elif multiple:
            print(_render(doc, args.format, label, args.words) if args.format == "md"
                  else f"===== {label} =====\n{doc.text}")
        else:
            print(_render(doc, args.format, label, args.words) if args.format != "md" else doc.to_markdown(label))
    if multiple:
        print(f"done: {used} ok, {failures} failed", file=sys.stderr)
    return 1 if failures else 0


def main_pl(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint for readpdf-pl."""
    return main(argv, default_lang="pl", prog="readpdf-pl")


def main_en(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint for readpdf-en."""
    return main(argv, default_lang="en", prog="readpdf-en")
