"""Offline unit tests for czytajpdf, readpdf-pl, and readpdf-en."""

from __future__ import annotations

import importlib.util
import io
import json
import sys
import types
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from czytajpdf import Document, Page, extract
from czytajpdf._types import OcrPage
from czytajpdf._cli import main as cli_main
from czytajpdf._cli import main_en, main_pl
from czytajpdf._quality import is_garbled, needs_ocr

HAS_OCR = importlib.util.find_spec("pypdfium2") is not None
HAS_POLISH = all(importlib.util.find_spec(pkg) is not None for pkg in ("morfeusz2", "wordfreq"))
HAS_ENGLISH = importlib.util.find_spec("wordfreq") is not None
HAS_WRAPPERS = all(
    importlib.util.find_spec(pkg) is not None for pkg in ("readpdf_pl", "readpdf_en")
)


def _escape_pdf_text(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _build_pdf(pages_text: list[str | None]) -> bytes:
    """Build a minimal valid PDF with one object per page and optional Helvetica text."""
    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"",  # Placeholder for /Pages (2 0 obj)
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    kids = []
    for text in pages_text:
        page_id = len(objects) + 1
        kids.append(f"{page_id} 0 R")
        if text is None:
            objects.append(
                b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] >>"
            )
            continue
        stream = f"BT /F1 12 Tf 20 150 Td ({_escape_pdf_text(text)}) Tj ET".encode("latin-1")
        content_id = page_id + 1
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {content_id} 0 R >>".encode("ascii")
        )
        objects.append(
            b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream"
        )
    objects[1] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(kids)} >>".encode("ascii")

    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for idx, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out.extend(f"{idx} 0 obj\n".encode("ascii"))
        out.extend(body)
        out.extend(b"\nendobj\n")
    xref_pos = len(out)
    out.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode("ascii"))
    for offset in offsets[1:]:
        out.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    out.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode("ascii")
    )
    return bytes(out)


class ExtractTests(unittest.TestCase):
    def test_argument_validation(self) -> None:
        with self.assertRaises(ValueError):
            extract("ignored.pdf", lang="bad lang!")
        with self.assertRaises(ValueError):
            extract("ignored.pdf", engine="unknown")  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            extract("ignored.pdf", min_chars=0)
        with self.assertRaises(ValueError):
            extract("ignored.pdf", ocr=False, correct=True)
        with self.assertRaises(ValueError):
            extract("ignored.pdf", workers=0)
        with self.assertRaises(ValueError):
            extract("ignored.pdf", backend="mupdf")  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            extract("ignored.pdf", ocr=True, correct="maybe")  # type: ignore[arg-type]
        with self.assertRaises(ValueError):  # spelling repair exists for pl/en only
            extract("ignored.pdf", ocr=True, correct=True, lang="de")
        with self.assertRaises(ValueError):
            extract("ignored.pdf", preprocess="sharpen")

    def test_native_extraction_preserves_page_numbers(self) -> None:
        with TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "native.pdf"
            pdf_path.write_bytes(_build_pdf([
                "Pierwsza strona ma pelna warstwe tekstowa z kilkoma slowami.",
                None,
            ]))
            doc = extract(pdf_path)
            self.assertIsInstance(doc, Document)
            self.assertEqual(len(doc.pages), 2)
            self.assertEqual(doc.pages[0].number, 1)
            self.assertEqual(doc.pages[0].source, "pdf")
            self.assertIn("Pierwsza strona", doc.pages[0].text)
            self.assertEqual(doc.pages[0].raw_text, doc.pages[0].text)
            self.assertEqual(doc.pages[1], Page(2, "pdf", "", ""))
            self.assertEqual(doc.text, f"{doc.pages[0].text}\n")

    def test_ocr_routing_lang_and_empty_fallback(self) -> None:
        calls: list[tuple] = []

        def fake_recognize(path, indices, options, executor=None, workers=1):
            calls.append((path, indices, options.engine, options.correct, options.spell_langs))
            return {1: OcrPage("raw ocr", "corrected ocr"), 2: OcrPage("   ", "   ")}

        fake_mod = types.ModuleType("czytajpdf._ocr")
        fake_mod.recognize = fake_recognize  # type: ignore[attr-defined]

        with TemporaryDirectory() as tmp, patch.dict(sys.modules, {"czytajpdf._ocr": fake_mod}):
            pdf_path = Path(tmp) / "mixed.pdf"
            pdf_path.write_bytes(_build_pdf([
                "This page has well over forty characters in its text layer.",
                None,
                "short",
            ]))
            doc = extract(pdf_path, ocr=True, correct=True, engine="tesseract", lang="en")
            self.assertEqual(calls, [(pdf_path, [1, 2], "tesseract", True, ("en",))])
            self.assertEqual(doc.pages[0].source, "pdf")
            self.assertEqual(doc.pages[1], Page(2, "tesseract", "raw ocr", "corrected ocr"))
            self.assertEqual(doc.pages[2], Page(3, "pdf", "short", "short"))

    def test_garbled_text_layer_triggers_ocr_even_above_min_chars(self) -> None:
        self.assertTrue(is_garbled("(cid:12)(cid:45)(cid:78)(cid:99)(cid:104)(cid:112) " * 3))
        self.assertTrue(is_garbled("A\ufffdB\ufffdC\ufffd " + "tekst " * 10))
        self.assertTrue(is_garbled("\ue001\ue002\ue003\ue004\ue005" * 12))
        self.assertTrue(is_garbled("!@#$%^&*()_+-=[]{}|;:',.<>?/~`!@#$%^&*()_+-=[]{}"))
        self.assertTrue(is_garbled(" ".join("abcdefghijklmnopqrstuvwxyz" * 2)))
        self.assertTrue(is_garbled("xkcd qzmp wvtr plkm nbgf hjkd fdsa trwq mnbv cxzl"))

        # Valid text layers (including accentless Polish, bullet PUA markers, and numeric tables) stay PDF.
        self.assertFalse(is_garbled("Pierwsza strona ma pelna warstwe tekstowa bez polskich znakow ale czytelna."))
        self.assertFalse(is_garbled("\uf0b7 Pierwszy punkt dokumentu\n\uf0b7 Drugi punkt dokumentu z trescia"))
        self.assertFalse(is_garbled("FV/2026/01/001 1234.50 PLN; FV/2026/01/002 5678.90 PLN; KRS 0000123456"))

        def fake_recognize(path, indices, options, executor=None, workers=1):
            return {i: OcrPage("czysty odczyt OCR", "czysty odczyt OCR") for i in indices}

        fake_mod = types.ModuleType("czytajpdf._ocr")
        fake_mod.recognize = fake_recognize  # type: ignore[attr-defined]

        with TemporaryDirectory() as tmp, patch.dict(sys.modules, {"czytajpdf._ocr": fake_mod}):
            pdf_path = Path(tmp) / "garbled.pdf"
            pdf_path.write_bytes(_build_pdf([
                "Pierwsza strona ma pelna warstwe tekstowa bez uszkodzen kodowania.",
                "(cid:11)(cid:22)(cid:33)(cid:44)(cid:55)(cid:66)(cid:77)(cid:88)(cid:99)(cid:100)(cid:101)",
                "xkcd qzmp wvtr plkm nbgf hjkd fdsa trwq mnbv cxzl kjhg",
            ]))
            doc = extract(pdf_path, ocr=True, lang="pl")
            self.assertEqual(doc.pages[0].source, "pdf")
            self.assertEqual(doc.pages[1], Page(2, "tesseract", "czysty odczyt OCR", "czysty odczyt OCR"))
            self.assertEqual(doc.pages[2], Page(3, "tesseract", "czysty odczyt OCR", "czysty odczyt OCR"))

    def test_bytes_and_binary_stream_inputs(self) -> None:
        pdf_bytes = _build_pdf([
            "Pierwsza strona z bufora bajtow ma poprawna warstwe tekstowa.",
            None,
        ])
        doc_bytes = extract(pdf_bytes)
        self.assertEqual(len(doc_bytes.pages), 2)
        self.assertIn("bufora bajtow", doc_bytes.pages[0].text)

        doc_stream = extract(io.BytesIO(pdf_bytes))
        self.assertEqual(doc_stream, doc_bytes)

        with self.assertRaises(TypeError):
            extract(io.StringIO("not bytes"))  # type: ignore[arg-type]

        seen_sources: list[object] = []

        def fake_recognize(source, indices, options, executor=None, workers=1):
            seen_sources.append(source)
            return {1: OcrPage("ocr from bytes", "ocr from bytes")}

        fake_mod = types.ModuleType("czytajpdf._ocr")
        fake_mod.recognize = fake_recognize  # type: ignore[attr-defined]
        with patch.dict(sys.modules, {"czytajpdf._ocr": fake_mod}):
            doc_ocr = extract(pdf_bytes, ocr=True, lang="en")
        self.assertEqual(seen_sources, [pdf_bytes])
        self.assertEqual(doc_ocr.pages[1], Page(2, "tesseract", "ocr from bytes", "ocr from bytes"))

    def test_cli_text_json_stdin_and_errors(self) -> None:
        pdf_bytes = _build_pdf(["Tekst strony testowej dla wywolania z wiersza polecen."])
        with TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "cli.pdf"
            pdf_path.write_bytes(pdf_bytes)

            out = io.StringIO()
            with redirect_stdout(out):
                status = cli_main([str(pdf_path)])
            self.assertEqual(status, 0)
            self.assertIn("Tekst strony testowej", out.getvalue())

            out_json = io.StringIO()
            with redirect_stdout(out_json):
                status = cli_main([str(pdf_path), "--json"])
            self.assertEqual(status, 0)
            parsed = json.loads(out_json.getvalue())
            self.assertEqual(parsed["pages"][0]["source"], "pdf")
            self.assertIn("Tekst strony testowej", parsed["text"])

        stdin_buf = io.BytesIO(pdf_bytes)
        fake_stdin = types.SimpleNamespace(buffer=stdin_buf)
        out_stdin = io.StringIO()
        with patch("sys.stdin", fake_stdin), redirect_stdout(out_stdin):
            status = cli_main(["-", "--json"])
        self.assertEqual(status, 0)
        self.assertIn("Tekst strony testowej", json.loads(out_stdin.getvalue())["text"])

        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as exc:
            cli_main(["doc.pdf", "--correct"])
        self.assertEqual(exc.exception.code, 2)

        err = io.StringIO()
        with redirect_stderr(err):
            missing_status = cli_main(["/nonexistent/file.pdf"])
        self.assertEqual(missing_status, 1)
        self.assertIn("error:", err.getvalue())

        defaults = dict(
            ocr=False, correct=False, min_chars=40, engine="tesseract", pages=None, backend="pypdf",
            password=None, workers=1, preprocess=False, cache=False, tessdata_dir=None, offline=None,
        )
        with patch("czytajpdf._cli.extract_iter", side_effect=lambda *a, **k: iter([Page(1, "pdf", "ok", "ok")])) as mock:
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main_pl(["a.pdf"]), 0)
            mock.assert_called_with("a.pdf", lang="pl", **defaults)
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main_en(["a.pdf"]), 0)
            mock.assert_called_with("a.pdf", lang="en", **defaults)


@unittest.skipUnless(HAS_OCR, "czytajpdf[ocr] is not installed")
class OcrBytesTests(unittest.TestCase):
    def test_recognize_accepts_pdf_bytes(self) -> None:
        from czytajpdf._ocr import recognize
        from czytajpdf._tesseract import TessResult
        from czytajpdf._types import OcrOptions, Word

        pdf_bytes = _build_pdf([None])
        options = OcrOptions("tesseract", False, ("eng",), ("en",))
        scan = TessResult("ocr text", (Word("ocr", (0, 0, 1, 1), 90.0),), 90.0)
        with patch("czytajpdf._models.resolve", return_value=Path(".")), patch(
            "czytajpdf._tesseract.open_engine"
        ) as mock_open, patch("czytajpdf._tesseract.read_page", return_value=scan):
            mock_open.return_value.__enter__.return_value = object()
            result = recognize(pdf_bytes, [0], options)
        page = result[0]
        self.assertEqual((page.raw, page.corrected, page.confidence, page.lang), ("ocr text", "ocr text", 90.0, "en"))
        self.assertEqual(page.words, scan.words)


@unittest.skipUnless(HAS_ENGLISH, "czytajpdf[english] is not installed")
class LexiconGarbledTests(unittest.TestCase):
    def test_shifted_latin_cmap_is_caught_with_lexicon(self) -> None:
        shifted = "Uijt jt b csplfo qeg ufyu mbzfs xjui nboz xpset uibu nblf op tfotf bu bmm"
        self.assertTrue(needs_ocr(shifted, min_chars=40, lang="en"))
        self.assertFalse(
            needs_ocr("This is a completely readable English text layer with plenty of words.", min_chars=40, lang="en")
        )


@unittest.skipUnless(HAS_WRAPPERS, "readpdf-pl and readpdf-en are not installed")
class WrapperTests(unittest.TestCase):
    def test_wrapper_default_languages(self) -> None:
        import readpdf_en
        import readpdf_pl

        with TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "scan.pdf"
            pdf_path.write_bytes(_build_pdf([None]))
            stub = Document((Page(1, "pdf", "", ""),))
            with patch.object(readpdf_pl, "_extract", return_value=stub) as mock_pl:
                readpdf_pl.extract(pdf_path, ocr=True)
                mock_pl.assert_called_once_with(
                    pdf_path, ocr=True, lang="pl"
                )
            with patch.object(readpdf_en, "_extract", return_value=stub) as mock_en:
                readpdf_en.extract(pdf_path, ocr=True, correct=True)
                mock_en.assert_called_once_with(
                    pdf_path, ocr=True, correct=True, lang="en"
                )


@unittest.skipUnless(HAS_ENGLISH, "czytajpdf[english] is not installed")
class EnglishSpellingTests(unittest.TestCase):
    def test_correct_text_repairs_english_ocr_confusions_only(self) -> None:
        from czytajpdf._spell import correct_text, ensure_dependencies, needs_second_read, reconcile_words

        ensure_dependencies("en")
        source = (
            "The Amendfnent bars eriminal govern-\nment bans on proseribe "
            "statutorv rules; Hallford testified."
        )
        repaired = correct_text(source, lang="en")
        self.assertIn("Amendment", repaired)
        self.assertIn("criminal", repaired)
        self.assertIn("govern-\nment", repaired)
        self.assertIn("proscribe", repaired)
        self.assertIn("statutory", repaired)
        self.assertIn("Hallford", repaired)

        first = "The Court dgnied relief."
        second = "The Court denied relief."
        self.assertTrue(needs_second_read(first, "en"))
        self.assertFalse(needs_second_read(second, "en"))
        self.assertEqual(reconcile_words(first, second, "en"), second)


@unittest.skipUnless(HAS_POLISH, "czytajpdf[polish] is not installed")
class PolishSpellingTests(unittest.TestCase):
    def test_correct_text_preserves_line_break_hyphenation(self) -> None:
        from czytajpdf._spell import correct_text

        source = "Umowa z Repub-\nliką Włoską oraz zalacznik."
        repaired = correct_text(source, lang="pl")
        self.assertIn("Repub-\nliką", repaired)
        self.assertIn("załącznik.", repaired)

    def test_reconcile_words_and_needs_second_read(self) -> None:
        from czytajpdf._spell import needs_second_read, reconcile_words

        first = "100 KOZPORZĄDZENIE w sprawie skiadu."
        second = "100 ROZPORZĄDZENIE w sprawie składu."
        self.assertTrue(needs_second_read(first, "pl"))
        self.assertFalse(needs_second_read(second, "pl"))
        self.assertEqual(reconcile_words(first, second, "pl"), second)

        unchanged = reconcile_words("100 ABZPORZĄDZENIE xyzq.", "100 ROZPORZĄDZENIE xwzp.", "pl")
        self.assertEqual(unchanged, "100 ABZPORZĄDZENIE xyzq.")


if __name__ == "__main__":
    unittest.main()
