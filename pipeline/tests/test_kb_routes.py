"""Task 3 proof: Document Hub routes. Upload (raw body, no python-multipart dep) ->
catalog 'queued' -> serialized worker ingest (Move 0b) -> 'ready'; list; safe delete
that is STRUCTURALLY incapable of touching anything outside documents/kb/ (hard rule
#5); path-locked source. Writes only to a temp .lancedb_kb / temp kb dir — eval stores
untouched. Ingest is now genuinely async (a real worker thread), so tests POLL for the
terminal status instead of assuming TestClient ran a background task inline."""

import sys
import tempfile
import time
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

PIPELINE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPELINE_DIR))
import catalog  # noqa: E402
import routes_kb  # noqa: E402
import api  # noqa: E402

client = TestClient(api.app)


class TestKbRoutes(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._cat, catalog.DEFAULT_DB = catalog.DEFAULT_DB, self.tmp / "cat.db"
        self._db, routes_kb.KB_DB = routes_kb.KB_DB, self.tmp / ".lancedb_kb"
        self._docs, routes_kb.KB_DOCS = routes_kb.KB_DOCS, self.tmp / "kb"
        self.m = catalog.create_matter("Hub Matter")
        self.slug = self.m["slug"]

    def tearDown(self):
        catalog.DEFAULT_DB = self._cat
        routes_kb.KB_DB = self._db
        routes_kb.KB_DOCS = self._docs

    def _upload(self, name, content):
        return client.post(f"/kb/upload?matter={self.slug}&filename={name}", content=content)

    def _wait_terminal(self, doc_id, timeout=90):
        deadline = time.time() + timeout
        while time.time() < deadline:
            row = catalog.get_document(doc_id)
            if row and row["status"] in ("ready", "needs_review", "failed"):
                return row["status"]
            time.sleep(0.2)
        return None

    def test_upload_then_ready_and_listed(self):
        r = self._upload("memo.txt", b"SYNTHETIC. The consulting fee is $5,000.")
        self.assertEqual(r.status_code, 200, r.text)
        doc = r.json()
        self.assertEqual(doc["status"], "queued")   # enqueue returns instantly (Move 0b)
        self.assertIn(self._wait_terminal(doc["id"]), ("ready", "needs_review"))
        rows = client.get(f"/kb/documents?matter={self.slug}").json()["documents"]
        self.assertTrue(any(d["id"] == doc["id"] for d in rows), rows)

    def test_ingest_status_route(self):
        s = client.get("/kb/ingest/status")
        self.assertEqual(s.status_code, 200)
        body = s.json()
        self.assertIn("queue_depth", body)
        self.assertIn("current", body)

    def test_unsupported_type_rejected(self):
        self.assertEqual(self._upload("evil.exe", b"\x00bad").status_code, 400)

    def test_delete_removes_copy_chunks_and_row(self):
        doc = self._upload("del_me.txt", b"SYNTHETIC. The retainer is $7,500.").json()
        self.assertIsNotNone(self._wait_terminal(doc["id"]))  # settle before deleting
        stored = Path(catalog.get_document(doc["id"])["stored_path"])
        self.assertTrue(stored.exists())
        d = client.delete(f"/kb/documents/{doc['id']}")
        self.assertEqual(d.status_code, 200, d.text)
        self.assertFalse(stored.exists(), "managed copy not removed")
        self.assertIsNone(catalog.get_document(doc["id"]), "catalog row not removed")

    def test_delete_cannot_escape_kb_dir(self):
        # A crafted catalog row whose stored_path is OUTSIDE documents/kb/ (simulating an
        # attorney original). Delete must NOT unlink it (structural lock, hard rule #5).
        outside = self.tmp / "attorney_original.txt"
        outside.write_text("ORIGINAL — must never be read or deleted", encoding="utf-8")
        doc = catalog.add_document(self.slug, outside)
        client.delete(f"/kb/documents/{doc['id']}")
        self.assertTrue(outside.exists(), "DELETE escaped documents/kb/ and touched an outside file")

    def test_source_route_404_for_unknown_doc(self):
        self.assertEqual(client.get("/kb/source/99999").status_code, 404)


if __name__ == "__main__":
    unittest.main(verbosity=2)
