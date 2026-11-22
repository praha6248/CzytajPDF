"""Offline unit tests for czytajpdf extraction and spelling repair."""

from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from czytajpdf import Document, Page, extract

HAS_POLISH = all(importlib.util.find_spec(pkg) is not None for pkg in ("morfeusz2", "wordfreq"))


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
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] >>".encode("ascii")
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
            extract("ignored.pdf", engine="unknown")  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            extract("ignored.pdf", min_chars=0)
        with self.assertRaises(ValueError):
            extract("ignored.pdf", ocr=False, correct=True)

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

    def test_ocr_routing_and_empty_fallback(self) -> None:
        calls: list[tuple[Path, list[int], str, bool]] = []

        def fake_recognize(path: Path, indices: list[int], engine: str, correct: bool) -> dict[int, tuple[str, str]]:
            calls.append((path, indices, engine, correct))
            return {1: ("raw ocr", "corrected ocr"), 2: ("   ", "   ")}

        fake_mod = types.ModuleType("czytajpdf._ocr")
        fake_mod.recognize = fake_recognize  # type: ignore[attr-defined]

        with TemporaryDirectory() as tmp, patch.dict(sys.modules, {"czytajpdf._ocr": fake_mod}):
            pdf_path = Path(tmp) / "mixed.pdf"
            pdf_path.write_bytes(_build_pdf([
                "Ta strona posiada ponad czterdziesci znakow w warstwie tekstowej.",
                None,
                "krotki",
            ]))
            doc = extract(pdf_path, ocr=True, correct=True, engine="tesseract")
            self.assertEqual(calls, [(pdf_path, [1, 2], "tesseract", True)])
            self.assertEqual(doc.pages[0].source, "pdf")
            self.assertEqual(doc.pages[1], Page(2, "tesseract", "raw ocr", "corrected ocr"))
            self.assertEqual(doc.pages[2], Page(3, "pdf", "krotki", "krotki"))


@unittest.skipUnless(HAS_POLISH, "czytajpdf[polish] is not installed")
class PolishSpellingTests(unittest.TestCase):
    def test_correct_text_preserves_line_break_hyphenation(self) -> None:
        from czytajpdf._spell import correct_text

        source = "Umowa z Repub-\nliką Włoską oraz zalacznik."
        repaired = correct_text(source)
        self.assertIn("Repub-\nliką", repaired)
        self.assertIn("załącznik.", repaired)

    def test_reconcile_words_and_needs_second_read(self) -> None:
        from czytajpdf._spell import needs_second_read, reconcile_words

        first = "100 KOZPORZĄDZENIE w sprawie skiadu."
        second = "100 ROZPORZĄDZENIE w sprawie składu."
        self.assertTrue(needs_second_read(first))
        self.assertFalse(needs_second_read(second))
        self.assertEqual(reconcile_words(first, second), second)

        # Multi-character differences or replacements that are not known words stay untouched.
        unchanged = reconcile_words("100 ABZPORZĄDZENIE xyzq.", "100 ROZPORZĄDZENIE xwzp.")
        self.assertEqual(unchanged, "100 ABZPORZĄDZENIE xyzq.")


if __name__ == "__main__":
    unittest.main()
