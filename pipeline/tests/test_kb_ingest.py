"""Task 3 proof: async ingest of an uploaded doc into a dedicated .lancedb_kb,
matter-scoped, with the Parsing->Ready/Needs-review/Failed lifecycle, and END-TO-END
answerability (an uploaded synthetic doc becomes answerable with a span-verified
citation). Writes ONLY to a temp .lancedb_kb here — never the eval stores."""

import sys
import tempfile
import unittest
from pathlib import Path

import fitz

PIPELINE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPELINE_DIR))
import catalog  # noqa: E402
import kb_ingest  # noqa: E402
from answering import answer, REFUSAL  # noqa: E402


class TestIngestDocument(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.cat = self.tmp / "cat.db"
        self.kb = self.tmp / ".lancedb_kb"
        self.m = catalog.create_matter("Test Matter", db_path=self.cat)
        self.slug = self.m["slug"]

    def _add(self, path):
        return catalog.add_document(self.slug, path, db_path=self.cat)

    def test_txt_ingests_ready_and_is_answerable(self):
        p = self.tmp / "retainer_memo.txt"
        p.write_text("SYNTHETIC — NOT REAL.\nThe retainer fee is $5,000, due on signing.",
                     encoding="utf-8")
        doc = self._add(p)
        status = kb_ingest.ingest_document(doc["id"], p, self.slug,
                                           db_path=self.kb, catalog_db=self.cat)
        self.assertEqual(status, "ready")
        # catalog row reflects ready
        row = catalog.get_document(doc["id"], db_path=self.cat)
        self.assertEqual(row["status"], "ready")
        # ANSWERABLE end-to-end: scoped to this matter, against the temp KB
        res = answer("What is the retainer fee?", matter=self.slug, db_path=str(self.kb))
        self.assertEqual(res["rejected_claims"], [])
        self.assertTrue(res["citations"], f"no citation; answer={res['answer_text']!r}")
        self.assertEqual(res["citations"][0]["filename"], "retainer_memo.txt")
        self.assertIn("5,000", res["answer_text"])

    def test_blank_scan_pdf_marks_needs_review(self):
        p = self.tmp / "blank_scan.pdf"
        with fitz.open() as d:
            pg = d.new_page(width=612, height=792)
            pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 1000, 1294))
            pix.clear_with(255)
            pg.insert_image(fitz.Rect(0, 0, 612, 792), stream=pix.tobytes("png"))
            d.save(p)
        doc = self._add(p)
        status = kb_ingest.ingest_document(doc["id"], p, self.slug,
                                           db_path=self.kb, catalog_db=self.cat)
        self.assertEqual(status, "needs_review")

    def test_reingest_is_idempotent_not_duplicated(self):
        p = self.tmp / "note.txt"
        p.write_text("SYNTHETIC. The deposit is $9,400.", encoding="utf-8")
        doc = self._add(p)
        kb_ingest.ingest_document(doc["id"], p, self.slug, db_path=self.kb, catalog_db=self.cat)
        from embed_store import open_table
        n1 = open_table(str(self.kb)).count_rows()
        kb_ingest.ingest_document(doc["id"], p, self.slug, db_path=self.kb, catalog_db=self.cat)
        n2 = open_table(str(self.kb)).count_rows()
        self.assertEqual(n1, n2, "re-ingest duplicated chunks")


if __name__ == "__main__":
    unittest.main(verbosity=2)
