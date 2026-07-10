"""UX-7 proof: Document Hub filing — POST /kb/documents/move re-files a document
into another matter: managed copy relocated, old-scope chunks removed, re-ingest
queued under the new scope. Blocked while the SOURCE matter is under an active
legal hold (moving out of a held matter would defeat preservation)."""

import sys
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

PIPELINE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPELINE_DIR))
import catalog  # noqa: E402
import ingest_worker  # noqa: E402
import routes_kb  # noqa: E402
import api  # noqa: E402

client = TestClient(api.app)


class TestMoveDocument(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._cat, catalog.DEFAULT_DB = catalog.DEFAULT_DB, self.tmp / "cat.db"
        self._docs, routes_kb.KB_DOCS = routes_kb.KB_DOCS, self.tmp / "kb"
        self._kdb, routes_kb.KB_DB = routes_kb.KB_DB, self.tmp / ".lancedb_kb"
        catalog.create_matter("Unfiled")
        catalog.create_matter("Target Matter")
        self.enqueued = []
        self._enq, ingest_worker.enqueue = ingest_worker.enqueue, \
            lambda *a, **k: self.enqueued.append(a) or 1
        # seed one doc into Unfiled via the normal upload route
        r = client.post("/kb/upload?matter=unfiled&filename=memo.txt",
                        content=b"SYNTHETIC memo body")
        self.doc_id = r.json()["id"]
        self.enqueued.clear()

    def tearDown(self):
        catalog.DEFAULT_DB = self._cat
        routes_kb.KB_DOCS = self._docs
        routes_kb.KB_DB = self._kdb
        ingest_worker.enqueue = self._enq

    def test_move_refiles_and_reingests(self):
        r = client.post("/kb/documents/move",
                        json={"doc_id": self.doc_id, "matter": "target-matter"})
        self.assertEqual(r.status_code, 200, r.text)
        row = catalog.get_document(self.doc_id)
        self.assertEqual(row["matter_slug"], "target-matter")
        self.assertEqual(row["status"], "queued")
        stored = Path(row["stored_path"])
        self.assertTrue(stored.is_file())
        self.assertIn("target-matter", stored.parts)
        # old managed copy gone; re-ingest queued under the new matter
        self.assertFalse((routes_kb.KB_DOCS / "unfiled" / "memo.txt").exists())
        self.assertEqual(len(self.enqueued), 1)
        self.assertEqual(self.enqueued[0][2], "target-matter")

    def test_move_blocked_by_source_hold(self):
        catalog.place_hold("unfiled", "preservation order")
        r = client.post("/kb/documents/move",
                        json={"doc_id": self.doc_id, "matter": "target-matter"})
        self.assertEqual(r.status_code, 409)
        self.assertEqual(catalog.get_document(self.doc_id)["matter_slug"], "unfiled")

    def test_move_to_same_matter_is_a_noop(self):
        r = client.post("/kb/documents/move",
                        json={"doc_id": self.doc_id, "matter": "unfiled"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json().get("unchanged"))
        self.assertEqual(self.enqueued, [])

    def test_move_to_unknown_matter_400(self):
        r = client.post("/kb/documents/move",
                        json={"doc_id": self.doc_id, "matter": "nope"})
        self.assertEqual(r.status_code, 400)


if __name__ == "__main__":
    unittest.main(verbosity=2)
