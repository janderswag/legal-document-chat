"""A0b — prune synthetic demo matters from the writable KB only (D-53).

Pruning removes a matter's chunks + catalog rows + managed copies, and leaves every other
matter intact. Temp catalog + temp KB store only; no baseline is touched.
"""

import sys
import tempfile
import unittest
from pathlib import Path

PIPELINE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPELINE_DIR))
import catalog  # noqa: E402
import kb_ingest  # noqa: E402
import kb_maintenance  # noqa: E402
from embed_store import open_table  # noqa: E402


class TestPruneMatters(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._cat, catalog.DEFAULT_DB = catalog.DEFAULT_DB, self.tmp / "cat.db"
        self.kb_db = self.tmp / ".lancedb_kb"
        self.kb_docs = self.tmp / "kb"
        for name in ("Demo One", "Keep Me"):
            catalog.create_matter(name)
        self._seed("demo-one", "a.txt", "SYNTHETIC. demo one fee is $111 monthly.")
        self._seed("keep-me", "b.txt", "SYNTHETIC. keep me code is KEEP-9 exactly.")

    def tearDown(self):
        catalog.DEFAULT_DB = self._cat

    def _seed(self, slug, name, text):
        d = (self.kb_docs / slug)
        d.mkdir(parents=True, exist_ok=True)
        p = d / name
        p.write_text(text, encoding="utf-8")
        doc = catalog.add_document(slug, p)
        kb_ingest.ingest_document(doc["id"], p, slug, db_path=self.kb_db,
                                  catalog_db=catalog.DEFAULT_DB)

    def test_prune_removes_only_named_matter(self):
        removed = kb_maintenance.prune_matter("demo-one", self.kb_db,
                                              catalog_db=catalog.DEFAULT_DB, kb_docs=self.kb_docs)
        self.assertEqual(removed, 1)
        slugs = {m["slug"] for m in catalog.list_matters()}
        self.assertNotIn("demo-one", slugs)
        self.assertIn("keep-me", slugs)              # other matter intact
        rows = open_table(str(self.kb_db)).to_arrow().to_pylist()
        matters = {r["matter"] for r in rows}
        self.assertNotIn("demo-one", matters)        # chunks gone
        self.assertIn("keep-me", matters)            # other chunks intact
        self.assertFalse((self.kb_docs / "demo-one").exists())   # managed copies gone
        self.assertTrue((self.kb_docs / "keep-me").exists())

    def test_prune_absent_matter_is_noop(self):
        self.assertEqual(
            kb_maintenance.prune_matter("nope", self.kb_db,
                                        catalog_db=catalog.DEFAULT_DB, kb_docs=self.kb_docs), 0)

    def test_prune_matters_bulk(self):
        out = kb_maintenance.prune_matters(["demo-one", "nope"], self.kb_db,
                                           catalog_db=catalog.DEFAULT_DB, kb_docs=self.kb_docs)
        self.assertEqual(out, {"demo-one": 1, "nope": 0})


if __name__ == "__main__":
    unittest.main(verbosity=2)
