"""Council 2026-07-11 Move 3 — email that tells the truth.

F1: Gmail's per-pass cap bounds one pass's WORK, never the reachable mailbox —
already-imported UIDs are excluded before the cap, so repeated passes walk a
label of any size. F2: an email's attachments become their own searchable
documents (same _ALLOWED gate as uploads), provenance-linked to the parent
message. F4: adapters that accept `since`/`exclude_ids` receive them from the
sync engine; older two-arg adapters keep working. Owner decision #4: imports
ALWAYS land in Unfiled; a configured matter survives only as the suggestion.

Same no-network idiom as test_e2e_connector_flow: scripted FakeIMAP, scratch
catalog/KB per test."""

import base64
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

PIPELINE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPELINE_DIR))
import catalog  # noqa: E402
import connsync  # noqa: E402
import ingest_worker  # noqa: E402
import routes_kb  # noqa: E402
import api  # noqa: E402
from connectors import gmail  # noqa: E402

from tests.test_adapters_email_files import RAW_MSG_1, RAW_MSG_2, FakeIMAP  # noqa: E402

client = TestClient(api.app)

CREDS = {"email": "jake@gmail.example", "app_password": "abcd abcd abcd abcd",
         "label": "docuchat"}

_PDF = base64.b64encode(b"%PDF-1.4 exhibit A contents")
RAW_WITH_ATTACHMENTS = (
    b"Subject: Exhibits for filing\r\n"
    b"From: Ana Torres <ana@firm.example>\r\n"
    b"To: jake@firm.example\r\n"
    b"Date: Thu, 03 Jul 2026 08:00:00 +0000\r\n"
    b"Message-ID: <m3@mail.gmail.example>\r\n"
    b"MIME-Version: 1.0\r\n"
    b"Content-Type: multipart/mixed; boundary=BNDRY\r\n"
    b"\r\n"
    b"--BNDRY\r\n"
    b"Content-Type: text/plain\r\n"
    b"\r\n"
    b"Exhibit A attached; installer attached by mistake.\r\n"
    b"--BNDRY\r\n"
    b"Content-Type: application/pdf; name=\"exhibit_a.pdf\"\r\n"
    b"Content-Disposition: attachment; filename=\"exhibit_a.pdf\"\r\n"
    b"Content-Transfer-Encoding: base64\r\n"
    b"\r\n" + _PDF + b"\r\n"
    b"--BNDRY\r\n"
    b"Content-Type: application/octet-stream; name=\"setup.exe\"\r\n"
    b"Content-Disposition: attachment; filename=\"setup.exe\"\r\n"
    b"\r\n"
    b"MZfake\r\n"
    b"--BNDRY--\r\n")


class EmailTruthBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._cat, catalog.DEFAULT_DB = catalog.DEFAULT_DB, self.tmp / "cat.db"
        self._docs, routes_kb.KB_DOCS = routes_kb.KB_DOCS, self.tmp / "kb"
        self._kdb, routes_kb.KB_DB = routes_kb.KB_DB, self.tmp / ".lancedb_kb"
        catalog.create_matter("Target Matter")
        self._enq, ingest_worker.enqueue = ingest_worker.enqueue, \
            lambda *a, **k: 1
        connsync._jobs.clear()

    def tearDown(self):
        catalog.DEFAULT_DB = self._cat
        routes_kb.KB_DOCS = self._docs
        routes_kb.KB_DB = self._kdb
        ingest_worker.enqueue = self._enq

    def _connect(self, fake, matter="unfiled", service="gmail"):
        with mock.patch("connectors.gmail.imaplib.IMAP4_SSL", fake):
            r = client.post("/connections", json={
                "service": service, "credentials": CREDS,
                "matter": matter, "sync": False})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def _import(self, fake, conn_id):
        with mock.patch("connectors.gmail.imaplib.IMAP4_SSL", fake):
            r = client.post("/connections/import", json={"id": conn_id})
            self.assertEqual(r.status_code, 200, r.text)
            for _ in range(300):
                job = client.get(
                    f"/connections/import/status?id={conn_id}").json()["job"]
                if job and job.get("state") in ("done", "error"):
                    return job
                time.sleep(0.02)
        self.fail("import never finished")


class TestF1GmailUncap(EmailTruthBase):
    def test_repeated_passes_walk_past_the_cap(self):
        # Four messages, cap of 2: pass 1 imports the oldest two, pass 2 the
        # NEXT two — the old behavior re-listed the same oldest two forever.
        msgs = {b"11": RAW_MSG_1, b"12": RAW_MSG_2,
                b"13": RAW_MSG_1.replace(b"<m1@", b"<m4@"),
                b"14": RAW_MSG_2.replace(b"<m2@", b"<m5@")}
        fake = FakeIMAP(messages=msgs)
        conn = self._connect(fake)
        with mock.patch.object(gmail, "MAX_MESSAGES", 2):
            job1 = self._import(fake, conn["id"])
            self.assertEqual(job1["imported"], 2, job1)
            job2 = self._import(fake, conn["id"])
            self.assertEqual(job2["imported"], 2, job2)
            job3 = self._import(fake, conn["id"])
            self.assertEqual(job3["imported"], 0, job3)   # drained, stays drained
        self.assertEqual(len(catalog.list_documents("unfiled")), 4)


class TestF2Attachments(EmailTruthBase):
    def test_allowed_attachment_becomes_child_document(self):
        fake = FakeIMAP(messages={b"21": RAW_WITH_ATTACHMENTS})
        conn = self._connect(fake)
        job = self._import(fake, conn["id"])
        self.assertEqual(job["state"], "done", job)
        self.assertEqual(job.get("attachments"), 1, job)  # the pdf, not the exe

        docs = {d["filename"]: d for d in catalog.list_documents("unfiled")}
        self.assertEqual(len(docs), 2, sorted(docs))      # .eml + exhibit_a.pdf
        att = docs["exhibit_a.pdf"]
        prov = json.loads(att["source_json"])
        self.assertEqual(prov["service"], "gmail")
        self.assertTrue(prov["attachment_of"].endswith(".eml"))
        self.assertNotIn("setup.exe", docs)               # _ALLOWED gate held
        # stored bytes are the DECODED pdf, not base64 text
        stored = Path(att["stored_path"]).read_bytes()
        self.assertIn(b"%PDF-1.4 exhibit A contents", stored)


class TestDecision4UnfiledAlways(EmailTruthBase):
    def test_bound_matter_becomes_a_suggestion_only(self):
        fake = FakeIMAP()
        conn = self._connect(fake, matter="target-matter")
        job = self._import(fake, conn["id"])
        self.assertEqual(job["state"], "done", job)

        self.assertEqual(catalog.list_documents("target-matter"), [],
                         "import auto-filed into a matter (decision #4 violated)")
        unfiled = catalog.list_documents("unfiled")
        self.assertEqual(len(unfiled), 2)
        for d in unfiled:
            prov = json.loads(d["source_json"])
            self.assertEqual(prov["suggested_matter"], "target-matter")


RAW_TRAVERSAL_ATT = (
    b"Subject: sneaky\r\n"
    b"From: x@evil.example\r\n"
    b"Date: Thu, 03 Jul 2026 09:00:00 +0000\r\n"
    b"Message-ID: <m9@mail.gmail.example>\r\n"
    b"MIME-Version: 1.0\r\n"
    b"Content-Type: multipart/mixed; boundary=BB\r\n"
    b"\r\n"
    b"--BB\r\n"
    b"Content-Type: text/plain\r\n"
    b"\r\n"
    b"hi\r\n"
    b"--BB\r\n"
    b"Content-Type: application/octet-stream\r\n"
    b"Content-Disposition: attachment; filename=\"../../evil.exe\"\r\n"
    b"\r\n"
    b"MZbad\r\n"
    b"--BB--\r\n")


class TestAttachmentHardening(EmailTruthBase):
    def test_unsafe_attachment_name_is_skipped_not_defaulted(self):
        # Review blocker #2: a traversal-named attachment must be SKIPPED — the
        # old fallback stored its un-gated bytes as "import.txt".
        fake = FakeIMAP(messages={b"31": RAW_TRAVERSAL_ATT})
        conn = self._connect(fake)
        job = self._import(fake, conn["id"])
        self.assertEqual(job["state"], "done", job)
        self.assertEqual(job.get("attachments"), 0, job)
        names = sorted(d["filename"] for d in catalog.list_documents("unfiled"))
        self.assertEqual(len(names), 1, names)            # just the .eml
        self.assertNotIn("import.txt", names)

    def test_same_attachment_in_two_emails_is_one_document(self):
        # Review finding #5: content identity — one stored file, one catalog
        # row, even when the same exhibit rides two messages.
        second = RAW_WITH_ATTACHMENTS.replace(b"<m3@", b"<m8@")
        fake = FakeIMAP(messages={b"21": RAW_WITH_ATTACHMENTS, b"22": second})
        conn = self._connect(fake)
        job = self._import(fake, conn["id"])
        self.assertEqual(job["state"], "done", job)
        docs = [d for d in catalog.list_documents("unfiled")
                if d["filename"].endswith(".pdf")]
        self.assertEqual(len(docs), 1, [d["filename"] for d in docs])


class TestStartImportNeverWedges(unittest.TestCase):
    def test_prelude_failure_becomes_error_and_next_start_spawns(self):
        # Review blocker #1: a failure BEFORE run_import's try (unknown
        # connection) must not leave the synchronously-reset "listing" status
        # wedged, or the Import button dies until app restart.
        connsync._jobs.clear()
        connsync.start_import(999999)
        for _ in range(200):
            job = connsync.job_status(999999)
            if job and job.get("state") == "error":
                break
            time.sleep(0.02)
        self.assertEqual(connsync.job_status(999999).get("state"), "error")
        # and a fresh start is allowed to spawn again (state resets to listing)
        snap = connsync.start_import(999999)
        self.assertIn(snap.get("state"), ("listing", "error", "starting"))
        connsync._jobs.clear()


class TestF4SincePassthrough(unittest.TestCase):
    def _stub(self, fn):
        return type("Adapter", (), {"list_items": staticmethod(fn)})

    def test_since_and_exclude_reach_an_allowlisted_adapter(self):
        got = {}

        def full(creds, since=None, exclude_ids=None):
            got.update(since=since, exclude_ids=exclude_ids)
            return []
        connsync._list_items(self._stub(full), {"k": "v"}, "2026-07-01T00:00:00",
                             {"a:1"}, service="fireflies")
        self.assertEqual(got, {"since": "2026-07-01T00:00:00",
                               "exclude_ids": {"a:1"}})

    def test_since_withheld_from_unverified_services(self):
        # Review finding #3: most adapters implement since as a client-side
        # modified-time filter (old item newly in scope -> permanently
        # invisible), and Slack's ts_from wants an epoch. Only allowlisted
        # services receive since; exclude_ids still flows.
        got = {}

        def full(creds, since=None, exclude_ids=None):
            got.update(since=since, exclude_ids=exclude_ids)
            return []
        connsync._list_items(self._stub(full), {}, "2026-07-01", {"x"},
                             service="slack")
        self.assertEqual(got, {"since": None, "exclude_ids": {"x"}})

    def test_legacy_creds_only_adapter_untouched(self):
        def legacy(creds):
            return ["ok"]
        out = connsync._list_items(self._stub(legacy), {}, "2026-07-01", {"x"})
        self.assertEqual(out, ["ok"])

    def test_no_last_sync_passes_nothing(self):
        def full(creds, since=None, exclude_ids=None):
            assert since is None
            return []
        connsync._list_items(self._stub(full), {}, None, set())


if __name__ == "__main__":
    unittest.main(verbosity=2)
