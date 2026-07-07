"""Move 4 (D-72) — retention acceptance, per the design doc §5: hold blocks disposal ->
release -> export carries natives + threads + manifests -> dispose removes everything
and emits an HONEST certificate (method=Clear, caveats stated) -> the hash-chained
audit log records it all and detects tampering. Temp stores only."""

import io
import json
import sqlite3
import sys
import tempfile
import time
import unittest
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

PIPELINE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPELINE_DIR))
import catalog  # noqa: E402
import routes_kb  # noqa: E402
import api  # noqa: E402

client = TestClient(api.app)


class TestRetentionLifecycle(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls._cat, catalog.DEFAULT_DB = catalog.DEFAULT_DB, cls.tmp / "cat.db"
        cls._db, routes_kb.KB_DB = routes_kb.KB_DB, cls.tmp / ".lancedb_kb"
        cls._docs, routes_kb.KB_DOCS = routes_kb.KB_DOCS, cls.tmp / "kb"
        catalog.create_matter("Retention Matter")
        cls.slug = "retention-matter"
        r = client.post(f"/kb/upload?matter={cls.slug}&filename=engagement.txt",
                        content=b"SYNTHETIC. The retainer for this engagement is $9,000.")
        cls.doc = r.json()
        deadline = time.time() + 120
        while time.time() < deadline:
            row = catalog.get_document(cls.doc["id"])
            if row and row["status"] in ("ready", "needs_review", "failed"):
                break
            time.sleep(0.2)
        # a chat thread so export has history
        client.post("/chat", json={"question": "What is the retainer amount?",
                                   "matter": cls.slug})

    @classmethod
    def tearDownClass(cls):
        catalog.DEFAULT_DB = cls._cat
        routes_kb.KB_DB = cls._db
        routes_kb.KB_DOCS = cls._docs

    def test_lifecycle_in_order(self):
        slug = self.slug
        # 1) hold blocks disposition AND single-doc deletes
        r = client.post(f"/retention/{slug}/hold", json={"reason": "Anticipated litigation"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(client.post(f"/retention/{slug}/dispose?confirm=true").status_code, 409)
        self.assertEqual(client.delete(f"/kb/documents/{self.doc['id']}").status_code, 409)

        # 2) release
        r = client.post(f"/retention/{slug}/release", json={"reason": "Matter settled"})
        self.assertEqual(r.status_code, 200)

        # 3) export carries natives + threads + manifests + audit slice
        r = client.get(f"/retention/{slug}/export")
        self.assertEqual(r.status_code, 200)
        z = zipfile.ZipFile(io.BytesIO(r.content))
        names = z.namelist()
        self.assertIn("documents/engagement.txt", names)
        self.assertIn("chats/threads.json", names)
        self.assertIn("manifest/documents.json", names)
        threads = json.loads(z.read("chats/threads.json"))
        self.assertTrue(threads and threads[0]["messages"], "chat history missing")
        self.assertIn(b"9,000", z.read("documents/engagement.txt"))

        # 4) dispose without confirm refused; with confirm -> honest certificate
        self.assertEqual(client.post(f"/retention/{slug}/dispose").status_code, 400)
        r = client.post(f"/retention/{slug}/dispose?confirm=true")
        self.assertEqual(r.status_code, 200, r.text)
        cert = r.json()
        self.assertIn("Clear", cert["method"])
        self.assertNotIn("Purge", cert["method"])          # never overclaim
        self.assertTrue(any("snapshots" in c for c in cert["caveats"]))
        self.assertEqual(cert["documents"][0]["filename"], "engagement.txt")
        self.assertTrue(cert["audit_chain_head"])

        # 5) everything is gone
        self.assertIsNone(catalog.get_matter(slug))
        self.assertEqual(catalog.list_documents(slug), [])
        self.assertEqual(catalog.threads_for_matter(slug), [])
        stored = Path(self.doc["stored_path"]) if "stored_path" in self.doc else None
        row_path = self.tmp / "kb" / slug / "engagement.txt"
        self.assertFalse(row_path.exists(), "managed copy survived disposition")
        from embed_store import open_table
        table = open_table(str(routes_kb.KB_DB))
        n = table.count_rows()
        if n:
            rows = table.search().select(["matter"]).limit(n).to_arrow().to_pylist()
            self.assertTrue(all(r["matter"] != slug for r in rows), "chunks survived")

        # 6) audit chain verifies, then tampering breaks it
        v = client.get("/retention/audit/verify").json()
        self.assertTrue(v["ok"], v)
        self.assertGreaterEqual(v["entries"], 4)  # hold, release, export, disposition
        conn = sqlite3.connect(str(catalog.DEFAULT_DB))
        conn.execute("UPDATE audit_log SET detail = 'tampered' WHERE event = 'export'")
        conn.commit()
        conn.close()
        v2 = client.get("/retention/audit/verify").json()
        self.assertFalse(v2["ok"], "audit chain did not detect tampering")


if __name__ == "__main__":
    unittest.main(verbosity=2)
