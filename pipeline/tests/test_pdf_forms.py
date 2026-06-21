"""D1 — bankruptcy-parser techniques reimplemented on PyMuPDF (M6-readiness prep).

Deterministic technique tests on a synthetic court form (rule-line geometry, crop-above-
line entered-value extraction, font/size input-vs-label filtering, checkbox normalization),
plus a smoke pass over the real PUBLIC PACER court-PDF fixtures (skipped if absent). No new
dependency; synthetic/public docs only.
"""

import sys
import tempfile
import unittest
from pathlib import Path

import fitz

PIPELINE_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = PIPELINE_DIR.parent
sys.path.insert(0, str(PIPELINE_DIR))
import build_form_corpus as bfc  # noqa: E402
import pdf_forms  # noqa: E402

COURT_FIXTURES = REPO_ROOT / "documents" / "fixtures" / "court"


class TestRuleLineTechniques(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.pdf = bfc.build_court_form(cls.tmp / "form.pdf")
        cls.doc = fitz.open(cls.pdf)
        cls.page = cls.doc[0]

    @classmethod
    def tearDownClass(cls):
        cls.doc.close()

    def test_finds_horizontal_rule_lines(self):
        lines = pdf_forms.horizontal_rule_lines(self.page)
        self.assertGreaterEqual(len(lines), 2, "did not find the two form rule lines")

    def test_extracts_entered_value_above_the_rule_line(self):
        fields = pdf_forms.extract_form_fields(self.page)
        values = " | ".join(f["value"] for f in fields)
        self.assertIn(bfc.ENTERED["debtor"], values)
        self.assertIn(bfc.ENTERED["case_no"], values)

    def test_input_vs_label_font_size_filtering(self):
        spans = list(pdf_forms.iter_spans(self.page))
        inputs = [s["text"] for s in spans if pdf_forms.is_input_span(s)]
        labels = [s["text"] for s in spans if not pdf_forms.is_input_span(s)]
        joined_inputs = " ".join(inputs)
        self.assertIn(bfc.ENTERED["debtor"], joined_inputs)        # entered data kept
        self.assertTrue(any("Debtor Name" in l for l in labels))   # label excluded


class TestCheckboxNormalization(unittest.TestCase):
    def test_checked_glyph(self):
        self.assertEqual(pdf_forms.normalize_checkbox("Wingdings", "ü"), "[√]")
        self.assertEqual(pdf_forms.normalize_checkbox("Wingdings", "cid:132"), "[√]")

    def test_unchecked_glyph(self):
        self.assertEqual(pdf_forms.normalize_checkbox("Wingdings", "o"), "[ ]")
        self.assertEqual(pdf_forms.normalize_checkbox("Wingdings", "cid:134"), "[ ]")

    def test_non_symbol_font_is_not_a_checkbox(self):
        self.assertIsNone(pdf_forms.normalize_checkbox("ArialMT", "x"))
        self.assertIsNone(pdf_forms.normalize_checkbox("Wingdings", "z"))


@unittest.skipUnless(COURT_FIXTURES.is_dir() and any(COURT_FIXTURES.glob("*.pdf")),
                     "public PACER court fixtures not present")
class TestRealCourtFixtures(unittest.TestCase):
    """Smoke pass over the real PUBLIC court PDFs — techniques run without error and find
    real structure (rule lines and/or spans). Public records only; no real client data."""

    def test_techniques_run_on_real_fixtures(self):
        any_lines = any_spans = False
        for pdf in sorted(COURT_FIXTURES.glob("*.pdf")):
            with fitz.open(pdf) as doc:
                page = doc[0]
                lines = pdf_forms.horizontal_rule_lines(page)
                spans = list(pdf_forms.iter_spans(page))
                any_lines = any_lines or bool(lines)
                any_spans = any_spans or bool(spans)
                # checkbox normalization must never crash on real spans
                for s in spans[:200]:
                    pdf_forms.normalize_checkbox(s["font"], s["text"][:8])
        self.assertTrue(any_spans, "no spans extracted from any real fixture")
        self.assertTrue(any_lines, "no rule lines found in any real fixture")


if __name__ == "__main__":
    unittest.main(verbosity=2)
