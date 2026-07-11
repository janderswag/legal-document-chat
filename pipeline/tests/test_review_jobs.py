"""Council 2026-07-11 Move 2 — the review-as-a-job HTTP contract.

POST /clauses/review-jobs queues on the D-90 runner (matter validated, in-flight
dedupe); GET /jobs/{id}/events streams meta -> clause... -> done and replays
identically for a late subscriber; POST /jobs/{id}/cancel stops between clauses;
GET /clauses/runs reopens the last finished review with honest staleness. answer()
is monkeypatched (fast + deterministic); the real LLM path is proven in
test_clauses.TestIntegrationAgainstBaseline."""

import sys
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

PIPELINE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPELINE_DIR))
import catalog  # noqa: E402
import clauses  # noqa: E402
import jobs  # noqa: E402
import review_job  # noqa: E402
import api  # noqa: E402

client = TestClient(api.app)

FOUND = {"answer_text": "The parties are Nimbus and Pemberton "
                        "[document: demo_msa.pdf, page: 2]",
         "citations": [{"filename": "demo_msa.pdf", "page": 2, "chunk_id": "C1",
                        "span": "Nimbus and Pemberton", "char_start": 10,
                        "char_end": 30}],
         "rejected_claims": [], "grounding_chunks": ["C1"]}


def parse_sse(text):
    events = []
    for block in text.split("\n\n"):
        lines = [ln for ln in block.split("\n") if ln and not ln.startswith(":")]
        if not lines:
            continue
        name = data = None
        for ln in lines:
            if ln.startswith("event: "):
                name = ln[7:]
            elif ln.startswith("data: "):
                data = ln[6:]
        if name:
            import json
            events.append((name, json.loads(data) if data else None))
    return events


class ReviewJobsBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls._cat, catalog.DEFAULT_DB = catalog.DEFAULT_DB, cls.tmp / "cat.db"
        catalog.create_matter("Demo Matter")
        p = cls.tmp / "demo_msa.pdf"
        p.write_bytes(b"%PDF-1.4 synthetic")
        cls.doc = catalog.add_document("demo-matter", p, status="ready")

    @classmethod
    def tearDownClass(cls):
        catalog.DEFAULT_DB = cls._cat

    def setUp(self):
        jobs._reset_for_tests()
        self._answer = clauses.answer
        clauses.answer = lambda q, matter=None, top_k=5, db_path=None, source_filename=None: dict(FOUND)

    def tearDown(self):
        clauses.answer = self._answer
        jobs._reset_for_tests()

    def submit(self, **body):
        return client.post("/clauses/review-jobs",
                           json={"matter": "demo-matter", **body})


class TestSubmitAndStream(ReviewJobsBase):
    def test_full_run_streams_meta_clauses_done_and_persists(self):
        r = self.submit()
        self.assertEqual(r.status_code, 200, r.text)
        job = r.json()
        self.assertFalse(job["existing"])
        self.assertTrue(jobs.wait(job["id"], timeout=30))

        ev = parse_sse(client.get(f"/jobs/{job['id']}/events").text)
        names = [n for n, _ in ev]
        self.assertEqual(names[0], "started")
        self.assertEqual(names[1], "meta")
        self.assertEqual(names[-1], "done")
        n_clauses = len(clauses.load_taxonomy())
        self.assertEqual(names.count("clause"), n_clauses)

        meta = ev[1][1]
        self.assertEqual(len(meta["clauses"]), n_clauses)      # skeleton source
        done = ev[-1][1]
        self.assertEqual(done["summary"]["found"], n_clauses)
        # citations enriched with catalog doc_id for /kb/highlight
        self.assertEqual(done["results"][0]["citations"][0]["doc_id"], self.doc["id"])
        # clause events arrive in taxonomy order
        clause_ids = [d["id"] for n, d in ev if n == "clause"]
        self.assertEqual(clause_ids, [c["id"] for c in clauses.load_taxonomy()])

    def test_unknown_matter_400_and_alien_doc_400(self):
        self.assertEqual(self.submit(matter="nope").status_code, 400)
        self.assertEqual(self.submit(doc_id=99999).status_code, 400)

    def test_inflight_dedupe_returns_existing_job(self):
        import threading
        gate = threading.Event()
        orig = clauses.answer

        def slow_answer(q, matter=None, top_k=5, db_path=None, source_filename=None):
            gate.wait(10)
            return dict(FOUND)
        clauses.answer = slow_answer
        try:
            first = self.submit().json()
            second = self.submit().json()
            self.assertEqual(second["id"], first["id"])
            self.assertTrue(second["existing"])
        finally:
            gate.set()
            clauses.answer = orig
        self.assertTrue(jobs.wait(first["id"], timeout=30))

    def test_doc_types_filter_and_custom_question(self):
        r = self.submit(doc_types=["nda"], questions=["Is there a pilot period?"])
        job = r.json()
        self.assertTrue(jobs.wait(job["id"], timeout=30))
        result = catalog.job_get(job["id"])["result"]
        planned = clauses.plan_clauses(doc_types=["nda"],
                                       extra_questions=["Is there a pilot period?"])
        self.assertEqual([row["id"] for row in result["results"]],
                         [c["id"] for c in planned])
        self.assertLess(len(planned), len(clauses.load_taxonomy()) + 1)  # filter bit
        self.assertEqual(result["results"][-1]["category"], "Custom")


class TestScopeAndStaleness(ReviewJobsBase):
    def test_different_scope_queues_its_own_job(self):
        # Review finding #4: a submit with different settings must never be
        # handed an in-flight job with the wrong scope.
        import threading
        gate = threading.Event()
        orig = clauses.answer

        def slow_answer(q, matter=None, top_k=5, db_path=None, source_filename=None):
            gate.wait(10)
            return dict(FOUND)
        clauses.answer = slow_answer
        try:
            whole = self.submit().json()
            nda = self.submit(doc_types=["nda"]).json()
            self.assertNotEqual(nda["id"], whole["id"])
            self.assertFalse(nda["existing"])
        finally:
            gate.set()
            clauses.answer = orig
        self.assertTrue(jobs.wait(whole["id"], timeout=30))
        self.assertTrue(jobs.wait(nda["id"], timeout=30))

    def test_doc_added_mid_run_flags_stale(self):
        # Review finding #3: docs_key is hashed BEFORE the run; a document that
        # arrives mid-review was never seen, so the run must read as stale.
        state = {"added": False}
        orig = clauses.answer

        def answer_and_sneak_a_doc(q, matter=None, top_k=5, db_path=None, source_filename=None):
            if not state["added"]:
                state["added"] = True
                p = self.tmp / "midrun_addendum.pdf"
                p.write_bytes(b"%PDF-1.4 midrun")
                catalog.add_document("demo-matter", p, status="ready")
            return dict(FOUND)
        clauses.answer = answer_and_sneak_a_doc
        try:
            job = self.submit().json()
            self.assertTrue(jobs.wait(job["id"], timeout=30))
        finally:
            clauses.answer = orig
        run = client.get("/clauses/runs",
                         params={"matter": "demo-matter"}).json()["run"]
        self.assertEqual(run["job_id"], job["id"])
        self.assertTrue(run["stale"])


class TestCancel(ReviewJobsBase):
    def test_cancel_stops_between_clauses(self):
        import threading
        first_clause = threading.Event()
        release = threading.Event()

        def slow_answer(q, matter=None, top_k=5, db_path=None, source_filename=None):
            first_clause.set()
            release.wait(10)
            return dict(FOUND)
        clauses.answer = slow_answer

        job = self.submit().json()
        self.assertTrue(first_clause.wait(10))
        r = client.post(f"/jobs/{job['id']}/cancel")
        self.assertEqual(r.status_code, 200)
        release.set()
        self.assertTrue(jobs.wait(job["id"], timeout=30))

        row = catalog.job_get(job["id"])
        self.assertEqual(row["status"], "cancelled")
        n_clause_events = sum(1 for e in row["events"] if e["event"] == "clause")
        self.assertLessEqual(n_clause_events, 2)  # stopped near the cancel point


class TestRuns(ReviewJobsBase):
    def test_latest_run_reopens_with_staleness(self):
        job = self.submit().json()
        self.assertTrue(jobs.wait(job["id"], timeout=30))

        r = client.get("/clauses/runs", params={"matter": "demo-matter"})
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertIsNone(body["active_job_id"])
        run = body["run"]
        self.assertEqual(run["job_id"], job["id"])
        self.assertFalse(run["stale"])
        self.assertEqual(run["summary"]["total"], len(clauses.load_taxonomy()))

        # a new document flips the staleness flag honestly
        p = self.tmp / "late_addendum.pdf"
        p.write_bytes(b"%PDF-1.4 more")
        catalog.add_document("demo-matter", p, status="ready")
        run2 = client.get("/clauses/runs",
                          params={"matter": "demo-matter"}).json()["run"]
        self.assertTrue(run2["stale"])

    def test_unknown_matter_400(self):
        r = client.get("/clauses/runs", params={"matter": "nope"})
        self.assertEqual(r.status_code, 400)


class TestJobsSurface(ReviewJobsBase):
    def test_unknown_job_404s(self):
        self.assertEqual(client.get("/jobs/99999").status_code, 404)
        self.assertEqual(client.get("/jobs/99999/events").status_code, 404)
        self.assertEqual(client.post("/jobs/99999/cancel").status_code, 404)

    def test_no_action_verbs_on_events(self):
        for verb in ("put", "patch", "delete"):
            r = getattr(client, verb)("/jobs/1/events")
            self.assertEqual(r.status_code, 405)


if __name__ == "__main__":
    unittest.main(verbosity=2)
