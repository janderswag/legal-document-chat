"""Task 3 proof: an OCR'd page is end-to-end SEARCHABLE (SC-2). G-SC2 proved OCR
extraction; this proves a scanned page is chunked, embedded into a SEPARATE store
(.lancedb_full, never the live .lancedb), and returned by answer() with a grounded,
span-verified, chunk-derived citation (D-38/D-19).

The proof uses a scan-ONLY synthetic doc with a unique matter (no born-digital twin),
so the OCR'd page is the SOLE possible source — the citation can only be the scanned
file. Hits real Ollama (bge-m3 embed + qwen3 answer) over loopback only.
"""

import sys
import unittest
from pathlib import Path

PIPELINE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPELINE_DIR))
import build_full_store  # noqa: E402
from answering import answer  # noqa: E402

FULL_DB = str(build_full_store.FULL_DB)
VELEZ_FILE = build_full_store.VELEZ_FILE
VELEZ_MATTER = build_full_store.VELEZ_MATTER
VELEZ_Q = "What is the total settlement amount payable to the claimant in the Velez matter?"


class TestOcrRetrievalE2E(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Build the full store (incl. the scan-only velez fixture) into .lancedb_full,
        # reusing it if a prior monitored build already created it.
        if not build_full_store.FULL_DB.exists():
            build_full_store.build()

    def test_ocr_page_is_answerable_with_verified_citation(self):
        res = answer(VELEZ_Q, matter=VELEZ_MATTER, db_path=FULL_DB)
        self.assertEqual(res["rejected_claims"], [], f"unexpected rejects: {res['rejected_claims']}")
        cits = res["citations"]
        self.assertTrue(cits, f"no verified citation; answer was: {res['answer_text']!r}")
        c = cits[0]
        # the cited source is the IMAGE-ONLY (OCR'd) doc, on its page, span-verified
        self.assertEqual(c["filename"], VELEZ_FILE)
        self.assertEqual(c["page"], 1)
        self.assertIn("char_start", c)
        self.assertIn("char_end", c)
        self.assertIn("88,250", res["answer_text"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
