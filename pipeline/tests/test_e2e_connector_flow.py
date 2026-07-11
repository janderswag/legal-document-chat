"""Sprint 2 E2E proof (2026-07-11): connect -> import -> Unfiled with
provenance -> move-to-matter, driven through the REAL production routes
(POST /connections, POST /connections/import, POST /kb/documents/move) for
the top three key-based adapters by solo-attorney value
(docs/council/2026-07-10-reports/connectors-audit.md value ranking: Gmail #1,
Zoom #4, Fireflies #7).

This is deliberately NOT the fake-adapter framework contract test
(test_connections.py, which proves the D-81 contract every adapter inherits
against a synthetic in-memory vendor). This suite exercises the actual
adapter modules (connectors/gmail.py, connectors/zoom.py,
connectors/fireflies.py) with each vendor's real REQUEST/RESPONSE shape
mocked exactly as its own unit test mocks it (FakeIMAP from
test_adapters_email_files, MockVendor from test_adapters) -- no network, no
real credentials, a scratch catalog/KB dir per test (never the owner's
app/data).
"""

import json
import sys
import tempfile
import time
import unittest
from datetime import date
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

from tests.test_adapters import FakeResponse, MockVendor  # noqa: E402
from tests.test_adapters_email_files import FakeIMAP  # noqa: E402

client = TestClient(api.app)


class E2EConnectorFlowBase(unittest.TestCase):
    """Scratch catalog + KB dirs per test (never the owner's real data dir)."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._cat, catalog.DEFAULT_DB = catalog.DEFAULT_DB, self.tmp / "cat.db"
        self._docs, routes_kb.KB_DOCS = routes_kb.KB_DOCS, self.tmp / "kb"
        self._kdb, routes_kb.KB_DB = routes_kb.KB_DB, self.tmp / ".lancedb_kb"
        catalog.create_matter("Target Matter")
        self._enq, ingest_worker.enqueue = ingest_worker.enqueue, \
            lambda *a, **k: self.enqueued.append(a) or 1
        self.enqueued = []
        connsync._jobs.clear()

    def tearDown(self):
        catalog.DEFAULT_DB = self._cat
        routes_kb.KB_DOCS = self._docs
        routes_kb.KB_DB = self._kdb
        ingest_worker.enqueue = self._enq

    def _connect_import_and_verify(self, service, credentials):
        """POST /connections -> POST /connections/import -> poll to done ->
        assert every imported doc landed in Unfiled with source_json
        provenance -> POST /kb/documents/move re-files the first one into a
        real matter. Returns the Unfiled docs (pre-move)."""
        r = client.post("/connections", json={
            "service": service, "credentials": credentials,
            "matter": "unfiled", "sync": False})
        self.assertEqual(r.status_code, 200, r.text)
        conn = r.json()

        r2 = client.post("/connections/import", json={"id": conn["id"]})
        self.assertEqual(r2.status_code, 200, r2.text)
        job = None
        for _ in range(200):
            job = client.get(
                f"/connections/import/status?id={conn['id']}").json()["job"]
            if job and job.get("state") in ("done", "error"):
                break
            time.sleep(0.02)
        self.assertEqual(job["state"], "done", job)
        self.assertGreater(job["imported"], 0, job)

        docs = catalog.list_documents("unfiled")
        self.assertTrue(docs)
        for d in docs:
            self.assertTrue(d.get("source_json"), f"{d['filename']} has no provenance")
            prov = json.loads(d["source_json"])
            self.assertEqual(prov["service"], service)
            self.assertIn("source_id", prov)
            self.assertTrue(Path(d["stored_path"]).exists())

        moved = docs[0]
        r3 = client.post("/kb/documents/move",
                         json={"doc_id": moved["id"], "matter": "target-matter"})
        self.assertEqual(r3.status_code, 200, r3.text)
        self.assertEqual(r3.json()["matter"], "target-matter")
        row = catalog.get_document(moved["id"])
        self.assertEqual(row["matter_slug"], "target-matter")
        self.assertTrue(Path(row["stored_path"]).is_file())
        return docs


class TestGmailEndToEnd(E2EConnectorFlowBase):
    """#1 in the audit's value ranking. Real IMAP protocol, scripted server."""

    CREDS = {"email": "jake@gmail.example",
             "app_password": "abcd abcd abcd abcd",
             "label": "docuchat"}

    def test_connect_import_unfiled_move(self):
        fake = FakeIMAP()
        with mock.patch("connectors.gmail.imaplib.IMAP4_SSL", fake):
            docs = self._connect_import_and_verify("gmail", self.CREDS)
        names = sorted(d["filename"] for d in docs)
        self.assertEqual(len(names), 2)
        self.assertTrue(all(n.endswith(".eml") for n in names))
        self.assertTrue(fake.logged_out)


class TestZoomEndToEnd(E2EConnectorFlowBase):
    """#4 in the audit's value ranking. Server-to-Server OAuth, real transcript."""

    CREDS = {"account_id": "acct_9", "client_id": "cid_1", "client_secret": "cs_1"}
    TOKEN = FakeResponse(json_data={"access_token": "zt-abc",
                                    "token_type": "bearer", "expires_in": 3600})
    MEETING = {
        "id": 123456, "uuid": "uu==1", "topic": "Pemberton status call",
        "start_time": "2026-07-01T16:00:00Z",
        "host_email": "jake@firm.example",
        "share_url": "https://zoom.us/rec/share/x",
        "recording_files": [
            {"id": "file_tr", "file_type": "TRANSCRIPT", "file_extension": "VTT",
             "download_url": "https://zoom.us/rec/download/tr"},
        ],
    }

    def test_connect_import_unfiled_move(self):
        vtt = b"WEBVTT\n\n00:00:00.000 --> 00:00:02.000\n<v Jake>Hello.\n"
        today = date.today().isoformat()

        def recordings(call):
            # only the newest (first) 30-day window has anything to return
            if call["params"]["to"] == today:
                return FakeResponse(json_data={"meetings": [self.MEETING],
                                               "next_page_token": ""})
            return FakeResponse(json_data={"meetings": [], "next_page_token": ""})

        with MockVendor([
            # more specific prefix first -- MockVendor matches by startswith(),
            # so "/users/me/recordings" must be checked before "/users/me" or
            # the whoami route swallows every recordings call too
            ("POST", "https://zoom.us/oauth/token", self.TOKEN),
            ("GET", "https://api.zoom.us/v2/users/me/recordings", recordings),
            ("GET", "https://api.zoom.us/v2/users/me",
             FakeResponse(json_data={"email": "jake@firm.example"})),
            ("GET", "https://zoom.us/rec/download/tr", FakeResponse(content=vtt)),
        ]):
            docs = self._connect_import_and_verify("zoom", self.CREDS)
        self.assertEqual(len(docs), 1)
        self.assertTrue(docs[0]["filename"].endswith(".vtt"))


class TestFirefliesEndToEnd(E2EConnectorFlowBase):
    """#7 in the audit's value ranking (tied w/ Fathom) -- the "notes service"
    leg of the sprint brief's Gmail/Zoom/notes-or-file trio."""

    CREDS = {"api_key": "ff-test"}
    GQL = "https://api.fireflies.ai/graphql"
    ROW = {"id": "tr_1", "title": "Pemberton kickoff",
           "date": 1782900000000, "duration": 1800,
           "host_email": "jake@firm.example",
           "organizer_email": "jake@firm.example",
           "meeting_link": "https://meet.example/x"}
    DETAIL = dict(
        ROW,
        transcript_url="https://app.fireflies.ai/view/tr_1",
        meeting_attendees=[{"displayName": "Jake", "email": "jake@firm.example"}],
        speakers=[{"name": "Jake"}, {"name": "Ana"}],
        sentences=[
            {"index": 0, "speaker_name": "Jake", "text": "Good morning.",
             "start_time": 0, "end_time": 2.5},
            {"index": 1, "speaker_name": "Ana", "text": "Morning, let's begin.",
             "start_time": 2.5, "end_time": 5.0},
        ],
        summary={"overview": "Kickoff overview.", "action_items": "Send the MSA."})

    def test_connect_import_unfiled_move(self):
        whoami = FakeResponse(json_data={"data": {"user": {
            "user_id": "u1", "name": "Jake", "email": "jake@firm.example"}}})
        listing = FakeResponse(json_data={"data": {"transcripts": [self.ROW]}})
        empty_page = FakeResponse(json_data={"data": {"transcripts": []}})
        detail = FakeResponse(json_data={"data": {"transcript": self.DETAIL}})

        def route(call):
            query = call["json_body"]["query"]
            if "transcript(id" in query:
                return detail
            if "transcripts(" in query:
                skip = call["json_body"]["variables"].get("skip", 0)
                return listing if skip == 0 else empty_page
            return whoami

        with MockVendor([("POST", self.GQL, route)]):
            docs = self._connect_import_and_verify("fireflies", self.CREDS)
        self.assertEqual(len(docs), 1)
        self.assertTrue(docs[0]["filename"].endswith(".vtt"))
        prov = json.loads(docs[0]["source_json"])
        self.assertEqual(prov["author"], "jake@firm.example")


if __name__ == "__main__":
    unittest.main(verbosity=2)
