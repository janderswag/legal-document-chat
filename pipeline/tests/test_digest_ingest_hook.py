"""Ingest hook: a successful ingest triggers digest extraction; a failed one does
not; a digest crash never fails the ingest. Backfill finds stale docs."""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PIPELINE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPELINE_DIR))
import catalog  # noqa: E402
import digest  # noqa: E402
import ingest_worker  # noqa: E402


class TestIngestHook(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._cat, catalog.DEFAULT_DB = catalog.DEFAULT_DB, self.tmp / "cat.db"
        catalog.create_matter("M")
        self.a_path = self.tmp / "a.txt"
        self.a_path.write_text("dummy content")
        self.doc = catalog.add_document("m", self.a_path, status="queued")

    def tearDown(self):
        catalog.DEFAULT_DB = self._cat

    def _run(self, ingest_result):
        with mock.patch.object(ingest_worker.kb_ingest, "ingest_document",
                               return_value=ingest_result), \
             mock.patch.object(ingest_worker, "digest") as dg:
            ingest_worker._run(self.doc["id"], str(self.a_path), "m",
                               str(self.tmp / "kb"), None)
        return dg

    def test_ready_triggers_digest(self):
        dg = self._run("ready")
        dg.extract_for_document.assert_called_once_with(
            self.doc["id"], str(self.tmp / "kb"), catalog_db=None)

    def test_needs_review_triggers_digest(self):
        dg = self._run("needs_review")
        dg.extract_for_document.assert_called_once_with(
            self.doc["id"], str(self.tmp / "kb"), catalog_db=None)

    def test_failed_does_not_trigger(self):
        dg = self._run("failed")
        dg.extract_for_document.assert_not_called()

    def test_digest_crash_never_fails_ingest(self):
        with mock.patch.object(ingest_worker.kb_ingest, "ingest_document",
                               return_value="ready"), \
             mock.patch.object(ingest_worker.digest, "extract_for_document",
                               side_effect=RuntimeError("boom")):
            ingest_worker._run(self.doc["id"], str(self.a_path), "m",
                               str(self.tmp / "kb"), None)   # must not raise
        # _run stamps "parsing" before calling (mocked) kb_ingest.ingest_document,
        # which here never touches the catalog again; the point is the digest
        # crash leaves that status alone rather than overwriting it to 'failed'.
        self.assertEqual(catalog.get_document(self.doc["id"])["status"], "parsing")


class TestBackfill(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._cat, catalog.DEFAULT_DB = catalog.DEFAULT_DB, self.tmp / "cat.db"
        catalog.create_matter("M")

    def tearDown(self):
        catalog.DEFAULT_DB = self._cat

    def _doc(self, name, status):
        path = self.tmp / name
        path.write_text("dummy content")
        return catalog.add_document("m", path, status=status)

    def test_backfill_digests_only_stale_ready_docs(self):
        d1 = self._doc("stale.pdf", "ready")
        d2 = self._doc("fresh.pdf", "ready")
        catalog.replace_facts(d2["id"], "m", [], digest.EXTRACTOR_VERSION)  # already done
        self._doc("broken.pdf", "failed")
        seen = []
        with mock.patch.object(digest, "extract_for_document",
                               side_effect=lambda i, *a, **k: seen.append(i)), \
             mock.patch.object(digest, "_yield_to_chat"):
            t = digest.backfill_async(self.tmp / "kb", initial_delay=0)
            t.join(timeout=10)
        self.assertEqual(seen, [d1["id"]])


if __name__ == "__main__":
    unittest.main(verbosity=2)
