"""A4 — live grid matrix (real loopback Ollama) over a 2-document matter.

Builds a self-contained temp KB (Pemberton MSA prose + the fee-schedule exhibit), runs a
small clause subset as a real (doc × clause) matrix, and proves end-to-end: cells are
span-verified (found requires a real citation), absent clauses are potentially_missing with
zero citations, and no citation ever names a document other than its own row (no leak).
Writes only a temp store; eval baselines untouched.
"""

import sys
import tempfile
import unittest
from pathlib import Path

PIPELINE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPELINE_DIR))
import build_table_corpus as btc  # noqa: E402
import catalog  # noqa: E402
import grid  # noqa: E402
import kb_ingest  # noqa: E402

MSA_SRC = PIPELINE_DIR.parent / "documents" / "synthetic_corpus" / "pdf" / "nimbus_pemberton_msa.pdf"


@unittest.skipUnless(MSA_SRC.exists(), "synthetic MSA corpus not present")
class TestGridLive(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls._cat, catalog.DEFAULT_DB = catalog.DEFAULT_DB, cls.tmp / "cat.db"
        cls.kb = cls.tmp / ".lancedb_kb"
        catalog.create_matter("Grid Live")  # slug -> grid-live
        msa = cls.tmp / "nimbus_pemberton_msa.pdf"; msa.write_bytes(MSA_SRC.read_bytes())
        exhibit = btc.build_fee_schedule_exhibit(cls.tmp / "exhibit.pdf")
        cls.docs = []
        for p in (msa, exhibit):
            d = catalog.add_document("grid-live", p, status="parsing")
            kb_ingest.ingest_document(d["id"], p, "grid-live", db_path=cls.kb,
                                      catalog_db=catalog.DEFAULT_DB)
            cls.docs.append({"doc_id": d["id"], "filename": p.name})
        cols = grid.resolve_columns(clause_ids=["governing_law", "indemnification", "non_compete"])
        cls.cells = list(grid.run_grid("grid-live", cls.docs, cols,
                                       db_path=str(cls.kb), max_workers=3))

    @classmethod
    def tearDownClass(cls):
        catalog.DEFAULT_DB = cls._cat

    def _cell(self, filename, col):
        for c in self.cells:
            if c["filename"] == filename and c["column_id"] == col:
                return c
        self.fail(f"cell ({filename}, {col}) missing")

    def test_full_matrix_present(self):
        self.assertEqual(len(self.cells), 6)  # 2 docs x 3 columns

    def test_governing_law_found_on_msa_with_citation(self):
        c = self._cell("nimbus_pemberton_msa.pdf", "governing_law")
        self.assertEqual(c["status"], "found", c["value"])
        self.assertTrue(c["citations"])
        self.assertEqual(c["citations"][0]["filename"], "nimbus_pemberton_msa.pdf")

    def test_noncompete_potentially_missing_zero_citations(self):
        for fn in ("nimbus_pemberton_msa.pdf", "exhibit.pdf"):
            c = self._cell(fn, "non_compete")
            self.assertIn(c["status"], ("potentially_missing", "not_confirmed"))
            self.assertEqual(c["citations"], [], f"{fn} non_compete fabricated a citation")

    def test_no_cross_document_citation_leak(self):
        for c in self.cells:
            for cite in c["citations"]:
                self.assertEqual(cite["filename"], c["filename"],
                                 f"leak: {c['column_id']} on {c['filename']} cited {cite['filename']}")

    def test_never_found_without_a_verified_citation(self):
        for c in self.cells:
            if c["status"] == "found":
                self.assertTrue(c["citations"], f"found w/o citation: {c['column_id']}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
