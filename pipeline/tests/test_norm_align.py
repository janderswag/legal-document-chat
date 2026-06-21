"""B1 — align answering._norm with the verifier normalization contract.

answering._extract_and_resolve maps a quoted span back to its chunk. Its local _norm did
NOT decode HTML entities or strip backslash-escaped quotes (the verifier does, M2-8a), so a
tag-less escaped span could false-REJECT (resolve to no chunk) even though it was truthful.
This aligns _norm (html.unescape + backslash-strip). It is precision-only and fails safe:
it only removes characters from the comparison — it can recover a truthful escaped span but
can never make a fabricated span resolve+verify (the mechanical verifier is the separate
display gate, unchanged).
"""

import sys
import unittest
from pathlib import Path

PIPELINE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPELINE_DIR))
import answering  # noqa: E402


def _grounding(text):
    return [{"chunk_id": "C1", "source_filename": "nda.pdf", "page_number": 1,
             "char_start": 0, "char_end": len(text), "text": text}]


class TestNormContract(unittest.TestCase):
    """_norm now matches the verifier contract: html.unescape + backslash-strip, then
    reflow/drop-quotes/lowercase. Precision-only — it only removes characters."""

    def test_decodes_html_entities(self):
        self.assertEqual(answering._norm("&quot;Confidential&quot;"), "confidential")
        self.assertEqual(answering._norm("Black &amp; White"), "black & white")

    def test_strips_backslash_escaped_quotes(self):
        self.assertEqual(answering._norm('\\"Landlord\\"'), "landlord")

    def test_plain_text_unchanged_apart_from_case_ws(self):
        self.assertEqual(answering._norm("Plain  Text here"), "plain text here")


class TestResolutionNoLongerFalseRejects(unittest.TestCase):
    def test_entity_in_quoted_span_now_resolves(self):
        # the chunk has a literal '&'; the model quoted it as the entity '&amp;'. Before
        # alignment _norm left '&amp;' != '&' -> false-reject; now it decodes and resolves.
        chunk = "This is the Black & White Master Agreement between the parties."
        ans = 'It is the "Black &amp; White Master Agreement" per the contract.'
        claims = answering._extract_and_resolve(ans, _grounding(chunk))
        self.assertTrue(any(c["target"] is not None for c in claims),
                        "truthful entity-bearing span still false-rejects")

    def test_fabricated_span_still_does_not_resolve(self):
        chunk = "This is the Black & White Master Agreement between the parties."
        ans = 'It is the "Trade Secret Formula Seven X" per the contract.'
        claims = answering._extract_and_resolve(ans, _grounding(chunk))
        self.assertFalse(any(c["target"] is not None for c in claims),
                         "fabricated span resolved to a chunk (false-accept risk)")


if __name__ == "__main__":
    unittest.main(verbosity=2)
