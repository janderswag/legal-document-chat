"""B5 — non-gating fuzzy span fallback (difflib).

When the MECHANICAL verifier finds no exact normalized overlap for an asserted span, this
fallback may surface a "probable source (unverified)" UI hint to help the attorney locate a
near-match. It is STRICTLY NON-GATING (D-19/D-38): a fuzzy hint is flagged verified=False,
is never a citation, and never enters the verified set. The keystone test: a span that only
FUZZY-matches (an altered digit) produces a hint but ZERO verified citations.
"""

import sys
import unittest
from pathlib import Path

PIPELINE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPELINE_DIR))
import fuzzy_fallback  # noqa: E402
from verifier import verify_answer  # noqa: E402


def _grounding():
    text = "The Net Amount due to Provider is $1,234.56 payable monthly in advance."
    return [{"chunk_id": "C1", "source_filename": "fee.pdf", "page_number": 2,
             "char_start": 0, "char_end": len(text), "text": text}]


class TestFuzzyFallback(unittest.TestCase):
    def test_fuzzy_only_span_yields_zero_verified_citations(self):
        # altered digit: $1,234.50 (real is $1,234.56) -> verifier MUST reject.
        ans = ('The net amount is $1,234.50 monthly '
               '[document: fee.pdf, page: 2, chunk: C1, span: "$1,234.50 payable monthly"].')
        verdict = verify_answer(ans, _grounding())
        self.assertEqual(verdict["citations"], [], "fuzzy-close span became a verified citation!")
        # the fallback may still offer an UNVERIFIED hint
        hints = fuzzy_fallback.probable_sources(ans, _grounding())
        self.assertTrue(hints, "expected a probable (unverified) hint")
        for h in hints:
            self.assertFalse(h["verified"], "fuzzy hint claims verified=True")
            self.assertNotIn("char_start", h)  # not shaped like a verified citation

    def test_hint_carries_no_verified_flag_or_offsets(self):
        ans = ('amount $1,234.50 monthly '
               '[document: fee.pdf, page: 2, chunk: C1, span: "$1,234.50 payable monthly"].')
        h = fuzzy_fallback.probable_sources(ans, _grounding())[0]
        self.assertEqual(h["filename"], "fee.pdf")
        self.assertEqual(h["page"], 2)
        self.assertIn("ratio", h)
        self.assertFalse(h["verified"])

    def test_exact_span_is_not_offered_as_a_fuzzy_hint(self):
        # an EXACTLY-verifiable span is handled by the verifier; the fallback skips it
        ans = ('amount $1,234.56 '
               '[document: fee.pdf, page: 2, chunk: C1, span: "$1,234.56 payable monthly"].')
        self.assertEqual(fuzzy_fallback.probable_sources(ans, _grounding()), [])
        self.assertEqual(len(verify_answer(ans, _grounding())["citations"]), 1)

    def test_far_span_yields_no_hint(self):
        ans = ('the governing law is California '
               '[document: fee.pdf, page: 2, chunk: C1, span: "governed by the laws of California"].')
        self.assertEqual(fuzzy_fallback.probable_sources(ans, _grounding()), [])

    def test_refusal_yields_no_hint(self):
        from answering import REFUSAL
        self.assertEqual(fuzzy_fallback.probable_sources(REFUSAL, _grounding()), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
