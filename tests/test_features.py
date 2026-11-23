"""Tests for batch CLI, page selection, languages, caching, chunking, models, and OCR extras."""

from __future__ import annotations

import importlib.util
import io
import json
import os
import sys
import types
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from czytajpdf import (
    Document, InvalidPDFError, ModelNotFoundError, Page, PasswordRequiredError, extract, extract_iter,
)
from czytajpdf._cli import main as cli_main
from czytajpdf._langs import parse_lang
from czytajpdf._pages import parse_pages
from czytajpdf._types import Correction, OcrPage, Word

from test_czytajpdf import HAS_ENGLISH, HAS_OCR, HAS_POLISH, _build_pdf

TEXT = "Pierwsza strona ma pelna warstwe tekstowa z kilkoma slowami."
HAS_CRYPTO = importlib.util.find_spec("cryptography") is not None
INTEGRATION = os.environ.get("CZYTAJPDF_INTEGRATION") == "1"


def _fake_ocr(handler):
    module = types.ModuleType("czytajpdf._ocr")
    module.recognize = handler
    return patch.dict(sys.modules, {"czytajpdf._ocr": module})


class PageSelectionTests(unittest.TestCase):
    def test_parse_pages(self) -> None:
        self.assertEqual(parse_pages(None, 4), [0, 1, 2, 3])
        self.assertEqual(parse_pages("2-3", 5), [1, 2])
        self.assertEqual(parse_pages("1,3-", 5), [0, 2, 3, 4])
        self.assertEqual(parse_pages("4-99", 5), [3, 4])
        self.assertEqual(parse_pages(2, 5), [1])
        self.assertEqual(parse_pages([3, 1, 3], 5), [0, 2])
        for bad in ("0", "6", "3-1", "x", "", [9]):
            with self.assertRaises(ValueError, msg=bad):
                parse_pages(bad, 5)

    def test_extract_pages_keeps_original_numbers(self) -> None:
        pdf = _build_pdf([TEXT, "druga strona dokumentu z trescia tekstowa", "trzecia strona dokumentu z trescia"])
        doc = extract(pdf, pages="2-3")
        self.assertEqual([p.number for p in doc.pages], [2, 3])


class LanguageTests(unittest.TestCase):
    def test_parse_lang(self) -> None:
        self.assertEqual(parse_lang("pl").tess, ("pol",))
        self.assertEqual(parse_lang("pl+en").spell, ("pl", "en"))
        self.assertEqual(parse_lang("auto").tess, ("pol", "eng"))
        german = parse_lang("de")
        self.assertEqual((german.tess, german.spell), (("deu",), ()))
        self.assertEqual(parse_lang("deu").tess, ("deu",))
        for bad in ("", "pl,en", "P L", "x"):
            with self.assertRaises(ValueError, msg=bad):
                parse_lang(bad)


class IterationAndOcrRoutingTests(unittest.TestCase):
    def test_extract_iter_streams_in_batches(self) -> None:
        batches: list[list[int]] = []

        def fake(source, indices, options, executor=None, workers=1):
            batches.append(list(indices))
            return {i: OcrPage(f"ocr {i}", f"ocr {i}", 88.0, "pl") for i in indices}

        pdf = _build_pdf([None] * 5)
        with _fake_ocr(fake):
            iterator = extract_iter(pdf, ocr=True, batch_size=2)
            self.assertEqual(next(iterator).text, "ocr 0")
            self.assertEqual(batches, [[0, 1]])  # later batches are not processed yet
            rest = list(iterator)
        self.assertEqual(batches, [[0, 1], [2, 3], [4]])
        self.assertEqual([p.number for p in rest], [2, 3, 4, 5])

    def test_extract_runs_one_ocr_batch(self) -> None:
        batches: list[list[int]] = []

        def fake(source, indices, options, executor=None, workers=1):
            batches.append(list(indices))
            return {i: OcrPage("x", "x") for i in indices}

        with _fake_ocr(fake):
            extract(_build_pdf([None] * 20), ocr=True)
        self.assertEqual(len(batches), 1)

    def test_suggest_keeps_raw_text_and_lists_corrections(self) -> None:
        fix = (Correction("skiadu", "składu", 4),)

        def fake(source, indices, options, executor=None, workers=1):
            self.assertTrue(options.correct)
            return {i: OcrPage("w skiadu", "w składu", 91.0, "pl", corrections=fix) for i in indices}

        pdf = _build_pdf([None])
        with _fake_ocr(fake):
            suggested = extract(pdf, ocr=True, correct="suggest")
            applied = extract(pdf, ocr=True, correct=True)
        self.assertEqual(suggested.pages[0].text, "w skiadu")
        self.assertEqual(suggested.pages[0].corrections, fix)
        self.assertEqual(applied.pages[0].text, "w składu")
        self.assertEqual(suggested.corrections, ((1, fix[0]),))

    def test_options_forwarded_and_pool_used_only_with_workers(self) -> None:
        seen = {}

        def fake(source, indices, options, executor=None, workers=1):
            seen.update(options=options, executor=executor, workers=workers)
            return {i: OcrPage("x", "x") for i in indices}

        with _fake_ocr(fake):
            extract(_build_pdf([None]), ocr=True, lang="pl+en", preprocess="rotate,denoise", tessdata_dir="/m")
        options = seen["options"]
        self.assertEqual(options.tess_langs, ("pol", "eng"))
        self.assertEqual(options.preprocess, ("rotate", "denoise"))
        self.assertEqual(options.tessdata_dir, "/m")
        self.assertIsNone(seen["executor"])

    def test_cache_skips_repeated_ocr(self) -> None:
        calls: list[list[int]] = []

        def fake(source, indices, options, executor=None, workers=1):
            calls.append(list(indices))
            return {i: OcrPage(f"raw{i}", f"fixed{i}", 77.5, "pl", 100.0, 200.0,
                               (Word("raw", (1, 2, 3, 4), 90.0),), (Correction("a", "b", 0),)) for i in indices}

        pdf = _build_pdf([None, None])
        with TemporaryDirectory() as tmp, _fake_ocr(fake):
            first = extract(pdf, ocr=True, cache=tmp)
            second = extract(pdf, ocr=True, cache=tmp)
            third = extract(pdf, ocr=True, cache=tmp, preprocess=True)  # different options -> miss
            partial = extract(_build_pdf([None, None, None]), ocr=True, cache=tmp)  # different file -> miss
        self.assertEqual(calls, [[0, 1], [0, 1], [0, 1, 2]])
        self.assertEqual(first, second)
        self.assertEqual(second.pages[0].words[0], Word("raw", (1, 2, 3, 4), 90.0))
        self.assertEqual(len(third.pages) + len(partial.pages), 5)


class BackendAndErrorTests(unittest.TestCase):
    @unittest.skipUnless(HAS_OCR, "pypdfium2 is not installed")
    def test_pdfium_backend(self) -> None:
        doc = extract(_build_pdf([TEXT, None]), backend="pdfium")
        self.assertEqual(doc.pages[0].text.strip(), TEXT)
        self.assertEqual(doc.pages[1].text, "")

    def test_invalid_pdf(self) -> None:
        with self.assertRaises(InvalidPDFError):
            extract(b"definitely not a pdf")

    @unittest.skipUnless(HAS_CRYPTO, "cryptography is not installed")
    def test_password(self) -> None:
        from pypdf import PdfReader, PdfWriter

        writer = PdfWriter(clone_from=PdfReader(io.BytesIO(_build_pdf([TEXT]))))
        writer.encrypt("sekret")
        buffer = io.BytesIO()
        writer.write(buffer)
        with self.assertRaises(PasswordRequiredError):
            extract(buffer.getvalue())
        with self.assertRaises(PasswordRequiredError):
            extract(buffer.getvalue(), password="zle")
        self.assertIn("Pierwsza", extract(buffer.getvalue(), password="sekret").text)

    def test_missing_ocr_extra_is_reported(self) -> None:
        from czytajpdf import MissingDependencyError

        with patch.dict(sys.modules, {"czytajpdf._ocr": None}):
            with self.assertRaises(MissingDependencyError):
                extract(_build_pdf([None]), ocr=True)
        with patch.dict(sys.modules, {"czytajpdf._ocr": None}):
            with self.assertRaises(ImportError):  # backwards-compatible base class
                extract(_build_pdf([None]), ocr=True)


class DocumentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.doc = Document((
            Page(1, "pdf", "Akapit pierwszy.\n\nAkapit drugi jest dluzszy od pierwszego.", "Akapit pierwszy.\n\nAkapit drugi jest dluzszy od pierwszego."),
            Page(2, "tesseract", "ra w", "raw", confidence=55.0, lang="pl", words=(Word("ra", (0, 0, 1, 1), 50.0),),
                 corrections=(Correction("ra", "raw", 0),)),
            Page(3, "pdf", "", ""),
        ))

    def test_chunks_respect_pages_and_limits(self) -> None:
        by_page = self.doc.chunks()
        self.assertEqual([c.metadata["page"] for c in by_page], [1, 2])
        self.assertEqual(by_page[1].metadata["confidence"], 55.0)
        self.assertTrue(by_page[1].metadata["corrected"])
        small = self.doc.chunks(max_chars=30, overlap=5)
        self.assertTrue(all(len(c.text) <= 30 for c in small))
        self.assertEqual({c.metadata["page"] for c in small}, {1, 2})
        self.assertGreater(len(small), len(by_page))
        for kwargs in ({"max_chars": 0}, {"max_chars": 10, "overlap": 9}, {"overlap": -1}):
            with self.assertRaises(ValueError):
                self.doc.chunks(**kwargs)

    def test_long_paragraph_is_split_without_losing_words(self) -> None:
        text = " ".join(f"slowo{i}" for i in range(200))
        chunks = Document((Page(1, "pdf", text, text),)).chunks(max_chars=100, overlap=20)
        self.assertTrue(all(len(c.text) <= 100 for c in chunks))
        joined = " ".join(c.text for c in chunks)
        for i in range(200):
            self.assertIn(f"slowo{i}", joined)

    def test_exports_and_low_confidence(self) -> None:
        self.assertEqual([p.number for p in self.doc.low_confidence_pages(60)], [2])
        plain = json.loads(self.doc.to_json())
        self.assertNotIn("words", plain["pages"][1])
        self.assertEqual(plain["pages"][1]["corrections"][0]["fixed"], "raw")
        self.assertIn("words", json.loads(self.doc.to_json(words=True))["pages"][1])
        markdown = self.doc.to_markdown("Akta")
        self.assertIn("# Akta", markdown)
        self.assertIn("## Page 2 (tesseract, confidence 55)", markdown)

    def test_framework_adapters_need_their_packages(self) -> None:
        from czytajpdf import MissingDependencyError

        with patch.dict(sys.modules, {"langchain_core": None, "langchain_core.documents": None,
                                      "llama_index": None, "llama_index.core": None}):
            with self.assertRaises(MissingDependencyError):
                self.doc.to_langchain()
            with self.assertRaises(MissingDependencyError):
                self.doc.to_llamaindex()

        fake_documents = types.SimpleNamespace(Document=lambda page_content, metadata: (page_content, metadata))
        with patch.dict(sys.modules, {"langchain_core": types.ModuleType("langchain_core"),
                                      "langchain_core.documents": fake_documents}):
            converted = self.doc.to_langchain()
        self.assertEqual(converted[0][1]["page"], 1)


class ModelResolutionTests(unittest.TestCase):
    def test_local_directory_never_downloads(self) -> None:
        from czytajpdf import _models

        with TemporaryDirectory() as tmp:
            with self.assertRaises(ModelNotFoundError):
                _models.resolve(["pol"], tmp)
            (Path(tmp) / "pol.traineddata").write_bytes(b"x")
            self.assertEqual(_models.resolve(["pol"], tmp), Path(tmp))
            with patch.dict(os.environ, {"CZYTAJPDF_TESSDATA": tmp}):
                self.assertEqual(_models.resolve(["pol"]), Path(tmp))
                with self.assertRaises(ModelNotFoundError):
                    _models.resolve(["eng"])

    @unittest.skipUnless(HAS_OCR, "czytajpdf[ocr] is not installed")
    def test_offline_mode_and_unknown_language(self) -> None:
        from czytajpdf import _models

        with TemporaryDirectory() as tmp, patch.object(_models, "cache_directory", return_value=Path(tmp)):
            with self.assertRaises(ModelNotFoundError):
                _models.resolve(["pol"], offline=True)
            with patch.dict(os.environ, {"CZYTAJPDF_OFFLINE": "1"}):
                with self.assertRaises(ModelNotFoundError):
                    _models.resolve(["eng"])
            with self.assertRaises(ModelNotFoundError):
                _models.resolve(["zzz"])


@unittest.skipUnless(HAS_OCR, "czytajpdf[ocr] is not installed")
class PreprocessTests(unittest.TestCase):
    def test_steps_and_skew(self) -> None:
        from PIL import Image, ImageDraw

        from czytajpdf import _preprocess as pre

        self.assertEqual(pre.normalize_steps(False), ())
        self.assertEqual(pre.normalize_steps(True), ("rotate", "deskew"))
        self.assertEqual(pre.normalize_steps("denoise, rotate"), ("rotate", "denoise"))
        self.assertEqual(pre.normalize_steps("all"), pre.STEPS)
        with self.assertRaises(ValueError):
            pre.normalize_steps("blur")

        image = Image.new("RGB", (900, 600), "white")
        draw = ImageDraw.Draw(image)
        for row in range(10):
            draw.rectangle((60, 60 + row * 45, 840, 74 + row * 45), fill="black")
        skewed = image.rotate(3, fillcolor="white")
        angle = pre.estimate_skew(skewed)
        self.assertAlmostEqual(angle, -3, delta=0.6)
        self.assertAlmostEqual(pre.estimate_skew(image), 0, delta=0.3)
        straight = pre.apply(skewed, ("deskew",))
        self.assertAlmostEqual(pre.estimate_skew(straight), 0, delta=0.6)
        self.assertEqual(pre.apply(image, ("binarize",)).getextrema(), ((0, 255),) * 3)


class SpellDiffTests(unittest.TestCase):
    def test_diff_corrections(self) -> None:
        from czytajpdf._spell import diff_corrections

        raw = "Umowa z Repub-\nliką oraz skiadu."
        fixed = "Umowa z Repub-\nliką oraz składu."
        self.assertEqual(diff_corrections(raw, fixed), (("skiadu.", "składu.", raw.index("skiadu")),))
        self.assertEqual(diff_corrections(raw, raw), ())

    @unittest.skipUnless(HAS_POLISH and HAS_ENGLISH, "polish and english extras are not installed")
    def test_multilingual_repair_protects_other_language(self) -> None:
        from czytajpdf._spell import correct_text

        text = "Sąd cytuje: the Supreme Court decision oraz zalacznik."
        fixed = correct_text(text, lang="pl", protect=("en",))
        self.assertIn("the Supreme Court decision", fixed)
        self.assertIn("załącznik", fixed)


class BatchCliTests(unittest.TestCase):
    def _run(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            status = cli_main([str(a) for a in argv])
        return status, out.getvalue(), err.getvalue()

    def test_output_directory_formats_and_pages(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "in").mkdir()
            (root / "in" / "a.pdf").write_bytes(_build_pdf([TEXT, "druga strona dokumentu z trescia tekstowa"]))
            (root / "in" / "b.pdf").write_bytes(_build_pdf(["Tresc dokumentu b ma wystarczajaco duzo znakow."]))
            (root / "broken.pdf").write_bytes(b"nope")
            status, _, err = self._run(root / "in", root / "broken.pdf", "-o", root / "out", "--pages", "1", "--progress")
            self.assertEqual(status, 1)  # one failure -> non-zero, others still processed
            self.assertIn("broken.pdf", err)
            self.assertIn("2 ok, 1 failed", err)
            self.assertEqual(sorted(p.name for p in (root / "out").iterdir()), ["a.txt", "b.txt"])
            self.assertIn("Pierwsza", (root / "out" / "a.txt").read_text(encoding="utf-8"))
            self.assertNotIn("druga", (root / "out" / "a.txt").read_text(encoding="utf-8"))

            status, _, _ = self._run(root / "in" / "*.pdf", "-o", root / "md", "--format", "md")
            self.assertEqual(status, 0)
            self.assertIn("## Page 1 (pdf)", (root / "md" / "a.md").read_text(encoding="utf-8"))

            (root / "out" / "a.txt").write_text("keep", encoding="utf-8")
            self._run(root / "in", "-o", root / "out", "--skip-existing")
            self.assertEqual((root / "out" / "a.txt").read_text(encoding="utf-8"), "keep")

    def test_multiple_inputs_to_stdout_use_json_lines(self) -> None:
        with TemporaryDirectory() as tmp:
            for name in ("x", "y"):
                (Path(tmp) / f"{name}.pdf").write_bytes(_build_pdf([TEXT]))
            status, out, _ = self._run(Path(tmp) / "x.pdf", Path(tmp) / "y.pdf", "--json")
            lines = out.strip().splitlines()
            self.assertEqual((status, len(lines)), (0, 2))
            self.assertTrue(json.loads(lines[0])["path"].endswith("x.pdf"))
            status, out, _ = self._run(Path(tmp) / "x.pdf", Path(tmp) / "y.pdf")
            self.assertIn("===== ", out)

    def test_usage_errors_and_no_match(self) -> None:
        for argv in (["a.pdf", "--correct"], ["a.pdf", "--ocr", "--correct", "--suggest"],
                     ["a.pdf", "--searchable", "--engine", "rapidocr", "--ocr"]):
            with self.assertRaises(SystemExit) as raised, redirect_stderr(io.StringIO()):
                cli_main(argv)
            self.assertEqual(raised.exception.code, 2)
        status, _, err = self._run("/nonexistent/*.pdf")
        self.assertEqual(status, 1)
        self.assertIn("no PDF files", err)

    def test_confidence_warning_and_suggest_flag(self) -> None:
        def fake(source, indices, options, executor=None, workers=1):
            return {i: OcrPage("zly odczyt", "zly odczyt", 40.0, "pl") for i in indices}

        with TemporaryDirectory() as tmp, _fake_ocr(fake):
            path = Path(tmp) / "scan.pdf"
            path.write_bytes(_build_pdf([None]))
            status, out, err = self._run(path, "--ocr", "--min-confidence", "60")
            self.assertEqual(status, 0)
            self.assertIn("confidence 40%", err)
            self.assertIn("zly odczyt", out)

    def test_download_models_subcommand(self) -> None:
        with patch("czytajpdf.download_models", return_value=Path("/models")) as mock:
            out = io.StringIO()
            with redirect_stdout(out):
                status = cli_main(["download-models", "--lang", "pl", "de", "--dir", "/models", "--osd"])
        self.assertEqual((status, out.getvalue().strip()), (0, "/models"))
        mock.assert_called_once_with(["pl", "de"], "/models", include_osd=True)


@unittest.skipUnless(INTEGRATION and HAS_OCR, "set CZYTAJPDF_INTEGRATION=1 (needs czytajpdf[ocr] and network/models)")
class RealOcrTests(unittest.TestCase):
    """Real Tesseract runs on a synthetic scan. Opt-in because models are downloaded on first use."""

    @staticmethod
    def _scan(angle: float = 0, quarter_turn: bool = False) -> bytes:
        from PIL import Image, ImageDraw, ImageFont

        font_path = next((p for p in ("/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
                                      "C:/Windows/Fonts/times.ttf") if Path(p).exists()), None)
        if font_path is None:
            raise unittest.SkipTest("no TrueType font available")
        font = ImageFont.truetype(font_path, 40)
        image = Image.new("RGB", (1654, 2339), "white")
        draw = ImageDraw.Draw(image)
        for row, line in enumerate(["ROZPORZĄDZENIE MINISTRA SPRAWIEDLIWOŚCI", "w sprawie składu komisji egzaminacyjnej"]):
            draw.text((150, 200 + row * 90), line, font=font, fill="black")
        if angle:
            image = image.rotate(angle, fillcolor="white", resample=Image.BICUBIC)
        if quarter_turn:
            image = image.rotate(90, expand=True)
        buffer = io.BytesIO()
        image.save(buffer, "PDF", resolution=200)
        return buffer.getvalue()

    def test_words_confidence_and_rotation(self) -> None:
        page, = extract(self._scan(), ocr=True).pages
        self.assertIn("ROZPORZĄDZENIE", page.text)
        self.assertGreater(page.confidence, 80)
        self.assertTrue(page.words and all(len(w.bbox) == 4 for w in page.words))
        self.assertAlmostEqual(page.width, 595.4, delta=1)
        rotated, = extract(self._scan(quarter_turn=True), ocr=True, preprocess=True).pages
        self.assertIn("MINISTRA", rotated.text)

    def test_workers_and_searchable(self) -> None:
        from pypdf import PdfReader, PdfWriter

        from czytajpdf import make_searchable

        with TemporaryDirectory() as tmp:
            single = Path(tmp) / "one.pdf"
            single.write_bytes(self._scan())
            writer = PdfWriter()
            for _ in range(3):
                writer.append(PdfReader(single))
            multi = Path(tmp) / "multi.pdf"
            writer.write(multi)
            doc = extract(multi, ocr=True, workers=2)
            self.assertEqual([p.number for p in doc.pages], [1, 2, 3])
            self.assertTrue(all("MINISTRA" in p.text for p in doc.pages))
            result = Path(tmp) / "searchable.pdf"
            self.assertEqual(make_searchable(multi, result), [1, 2, 3])
            self.assertIn("MINISTRA", PdfReader(result).pages[2].extract_text())


if __name__ == "__main__":
    unittest.main()
