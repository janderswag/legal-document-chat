"""Move 0b/0c (D-68) — the ingest worker runs jobs ONE AT A TIME off the request path,
walks the queued -> parsing -> terminal lifecycle, reports progress, and never lets one
crashing job kill the worker."""

import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

PIPELINE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPELINE_DIR))
import catalog  # noqa: E402
import ingest_worker  # noqa: E402
import kb_ingest  # noqa: E402


class TestIngestWorker(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.cat = self.tmp / "cat.db"
        catalog.create_matter("Worker Matter", db_path=self.cat)
        self.docs = []
        for i in range(5):
            p = self.tmp / f"doc{i}.txt"
            p.write_text(f"SYNTHETIC doc {i}", encoding="utf-8")
            self.docs.append(catalog.add_document("worker-matter", p, db_path=self.cat,
                                                  status="queued"))

    def _wait(self, cond, timeout=20):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if cond():
                return True
            time.sleep(0.05)
        return False

    def test_jobs_run_serially_in_order(self):
        seen, in_flight, max_in_flight = [], [0], [0]
        lock = threading.Lock()

        def fake_ingest(doc_id, file_path, matter_slug, db_path, catalog_db=None,
                        on_stage=None):
            with lock:
                in_flight[0] += 1
                max_in_flight[0] = max(max_in_flight[0], in_flight[0])
            time.sleep(0.05)
            seen.append(doc_id)
            with lock:
                in_flight[0] -= 1
            return "ready"

        with patch.object(kb_ingest, "ingest_document", side_effect=fake_ingest):
            for d in self.docs:
                ingest_worker.enqueue(d["id"], "x.txt", "worker-matter",
                                      self.tmp / "kb", self.cat)
            done = self._wait(lambda: len(seen) == 5)
        self.assertTrue(done, f"only {len(seen)}/5 jobs ran")
        self.assertEqual(seen, [d["id"] for d in self.docs], "order not preserved")
        self.assertEqual(max_in_flight[0], 1, "jobs ran concurrently — must be serialized")

    def test_crashing_job_does_not_kill_worker_and_marks_failed(self):
        calls = []

        def flaky(doc_id, *a, **k):
            calls.append(doc_id)
            if len(calls) == 1:
                raise RuntimeError("boom")
            return "ready"

        with patch.object(kb_ingest, "ingest_document", side_effect=flaky):
            ingest_worker.enqueue(self.docs[0]["id"], "x", "worker-matter",
                                  self.tmp / "kb", self.cat)
            ingest_worker.enqueue(self.docs[1]["id"], "x", "worker-matter",
                                  self.tmp / "kb", self.cat)
            self.assertTrue(self._wait(lambda: len(calls) == 2), "worker died after crash")
        self.assertTrue(self._wait(lambda: catalog.get_document(
            self.docs[0]["id"], db_path=self.cat)["status"] == "failed"))

    def test_deleted_while_queued_is_skipped(self):
        ran = []
        with patch.object(kb_ingest, "ingest_document",
                          side_effect=lambda *a, **k: ran.append(1) or "ready"):
            gone = catalog.add_document("worker-matter", self.tmp / "doc0.txt",
                                        db_path=self.cat, status="queued")
            catalog.delete_document(gone["id"], db_path=self.cat)
            ingest_worker.enqueue(gone["id"], "x", "worker-matter",
                                  self.tmp / "kb", self.cat)
            # follow with a real job to prove the queue advanced past the skip
            ingest_worker.enqueue(self.docs[2]["id"], "x", "worker-matter",
                                  self.tmp / "kb", self.cat)
            self.assertTrue(self._wait(lambda: len(ran) == 1))

    def test_status_shape(self):
        s = ingest_worker.status()
        self.assertIn("queue_depth", s)
        self.assertIn("current", s)
        self.assertIn("processed", s)


if __name__ == "__main__":
    unittest.main(verbosity=2)
