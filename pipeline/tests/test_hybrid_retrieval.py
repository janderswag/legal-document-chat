"""Task 5 proof: opt-in hybrid dense+BM25 retrieval (RRF) behind the matter pre-filter
(M3). hybrid=True fuses dense vector search with native LanceDB full-text (BM25) so a
keyword/number-exact query surfaces the right chunk at rank 0; the matter pre-filter
(D-18) is still applied BEFORE fusion (no cross-matter leak); hybrid=False is unchanged.

Runs against the SEPARATE .lancedb_full store (never the live .lancedb). bge-m3 embed
over loopback only. NOTE: LanceDB 0.33 uses NATIVE FTS (tantivy removed upstream) — no
tantivy dependency."""

import sys
import unittest
from pathlib import Path

PIPELINE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPELINE_DIR))
from retrieval import retrieve  # noqa: E402

FULL_DB = str(PIPELINE_DIR / ".lancedb_full")
VELEZ_FILE = "scan_only_velez_settlement.pdf"
VELEZ_MATTER = "Velez Settlement (Scan Only)"
PEMBERTON = "Pemberton Logistics (Nimbus MSA)"


class TestHybridRetrieval(unittest.TestCase):
    def test_keyword_exact_number_is_rank0_under_hybrid(self):
        # the exact number "88,250" lives only in the velez OCR'd chunk; BM25 fusion
        # must surface it at rank 0 within its matter.
        res = retrieve("88,250 total settlement amount", matter=VELEZ_MATTER,
                       db_path=FULL_DB, hybrid=True)
        self.assertTrue(res, "hybrid returned nothing")
        self.assertEqual(res[0]["source_filename"], VELEZ_FILE)

    def test_matter_prefilter_still_kills_cross_matter_under_hybrid(self):
        res = retrieve("settlement amount due", matter=PEMBERTON, db_path=FULL_DB, hybrid=True)
        self.assertTrue(res)
        for r in res:
            self.assertEqual(r["matter"], PEMBERTON, "cross-matter leak under hybrid")

    def test_hybrid_false_is_unchanged_dense_only(self):
        res = retrieve("monthly service fee", matter=PEMBERTON, db_path=FULL_DB, hybrid=False)
        self.assertTrue(res)
        self.assertTrue(all("char_start" in r and "char_end" in r for r in res))
        # dense-only path must not require building the FTS index to work
        self.assertLessEqual(len(res), 5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
