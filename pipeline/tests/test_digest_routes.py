"""M-2 overview API: grouped verified facts + review state; confirm/dismiss flow;
matter fence (404 on unknown matter); date format validation."""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

PIPELINE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPELINE_DIR))
import catalog  # noqa: E402
import digest  # noqa: E402
import api  # noqa: E402

client = TestClient(api.app)


def _fact(key, ftype="date_event", value=None, page=1):
    return {"fact_type": ftype,
            "value": value or {"kind": "deadline", "label": "Answer due",
                               "date_text": "within 30 days", "date_iso": None,
                               "date_kind": "relative", "anchor": "service"},
            "page": page, "char_start": 0, "char_end": 14,
            "span": "within 30 days", "fact_key": key}


class TestOverviewRoutes(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._cat, catalog.DEFAULT_DB = catalog.DEFAULT_DB, self.tmp / "cat.db"
        catalog.create_matter("Nimbus Dispute")
        self.pdf_path = self.tmp / "msa.pdf"
        self.pdf_path.write_text("dummy content")
        self.doc = catalog.add_document("nimbus-dispute", self.pdf_path, status="ready")
        catalog.replace_facts(self.doc["id"], "nimbus-dispute", [
            _fact("dl"),                                                     # deadline
            _fact("ev", value={"kind": "event", "label": "MSA executed",
                               "date_text": "March 1, 2026", "date_iso": "2026-03-01",
                               "date_kind": "explicit", "anchor": None}),
            _fact("pt", ftype="party", value={"name": "Nimbus Analytics LLC",
                                              "role": "provider", "org_form": "LLC"}),
        ], "v1")

    def tearDown(self):
        catalog.DEFAULT_DB = self._cat

    def test_overview_groups_and_review_join(self):
        # "v1" predates the real EXTRACTOR_VERSION and nothing is queued to redo it
        # -> stuck, not building, but only once the backfill sweep has completed.
        with mock.patch.object(digest, "status",
                               return_value={"queue_depth": 0, "current": None,
                                             "backfill_done": True}):
            r = client.get("/matters/nimbus-dispute/overview")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual([i["fact_key"] for i in body["deadlines"]], ["dl"])
        self.assertEqual(sorted(i["fact_key"] for i in body["timeline"]), ["dl", "ev"])
        self.assertEqual(body["parties"][0]["value"]["name"], "Nimbus Analytics LLC")
        self.assertEqual(body["deadlines"][0]["filename"], "msa.pdf")
        self.assertIsNone(body["deadlines"][0]["review"])
        self.assertEqual(body["building"], {"done": 0, "total": 1, "stuck": 1})

    def test_unknown_matter_404(self):
        self.assertEqual(client.get("/matters/nope/overview").status_code, 404)

    def test_confirm_with_date_then_undo(self):
        r = client.post("/matters/nimbus-dispute/facts/dl/review",
                        json={"status": "confirmed", "confirmed_date": "2026-07-24"})
        self.assertEqual(r.status_code, 200)
        body = client.get("/matters/nimbus-dispute/overview").json()
        self.assertEqual(body["deadlines"][0]["review"],
                         {"status": "confirmed", "confirmed_date": "2026-07-24"})
        client.post("/matters/nimbus-dispute/facts/dl/review", json={"status": None})
        body = client.get("/matters/nimbus-dispute/overview").json()
        self.assertIsNone(body["deadlines"][0]["review"])

    def test_dismissed_leaves_lists_and_counts(self):
        client.post("/matters/nimbus-dispute/facts/ev/review",
                    json={"status": "dismissed"})
        body = client.get("/matters/nimbus-dispute/overview").json()
        self.assertEqual([i["fact_key"] for i in body["timeline"]], ["dl"])
        self.assertEqual(body["dismissed_count"], 1)

    def test_deadline_sort_order(self):
        # Comparator in routes_digest.overview: unconfirmed before confirmed; within
        # unconfirmed, dated (by date) before dateless; confirmed last, by date.
        catalog.replace_facts(self.doc["id"], "nimbus-dispute", [
            _fact("confirmed_dated", value={"kind": "deadline", "label": "Confirmed",
                                            "date_text": "March 1, 2026", "date_iso": "2026-03-01",
                                            "date_kind": "explicit", "anchor": None}),
            _fact("unconfirmed_dated", value={"kind": "deadline", "label": "Unconfirmed dated",
                                              "date_text": "April 1, 2026", "date_iso": "2026-04-01",
                                              "date_kind": "explicit", "anchor": None}),
            _fact("unconfirmed_dateless", value={"kind": "deadline", "label": "Unconfirmed dateless",
                                                 "date_text": "within 10 days", "date_iso": None,
                                                 "date_kind": "relative", "anchor": "service"}),
        ], "v1")
        client.post("/matters/nimbus-dispute/facts/confirmed_dated/review",
                    json={"status": "confirmed", "confirmed_date": "2026-03-01"})
        body = client.get("/matters/nimbus-dispute/overview").json()
        self.assertEqual([i["fact_key"] for i in body["deadlines"]],
                         ["unconfirmed_dated", "unconfirmed_dateless", "confirmed_dated"])

    def test_bad_status_and_bad_date_rejected(self):
        r = client.post("/matters/nimbus-dispute/facts/dl/review",
                        json={"status": "approved"})
        self.assertEqual(r.status_code, 422)
        r = client.post("/matters/nimbus-dispute/facts/dl/review",
                        json={"status": "confirmed", "confirmed_date": "July 24"})
        self.assertEqual(r.status_code, 422)


class TestDigestStuckSignal(unittest.TestCase):
    """Trust fix (gaps-audit digest empty-state honesty): a ready doc that never gets
    a current digest_version stamp looks identical to "still building" unless the
    overview also knows whether the digest worker is idle. building.stuck must be 0
    while something is still queued/in-flight, and equal to the pending count once
    the worker has genuinely given up (nothing left to try)."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._cat, catalog.DEFAULT_DB = catalog.DEFAULT_DB, self.tmp / "cat.db"
        catalog.create_matter("Stuck Matter")
        path = self.tmp / "doc.pdf"
        path.write_text("dummy content")
        self.doc = catalog.add_document("stuck-matter", path, status="ready")

    def tearDown(self):
        catalog.DEFAULT_DB = self._cat

    def test_not_stuck_while_digest_worker_is_busy(self):
        with mock.patch.object(digest, "status",
                               return_value={"queue_depth": 0, "current": self.doc["id"],
                                             "backfill_done": True}):
            body = client.get("/matters/stuck-matter/overview").json()
        self.assertEqual(body["building"], {"done": 0, "total": 1, "stuck": 0})

    def test_not_stuck_while_something_is_queued(self):
        with mock.patch.object(digest, "status",
                               return_value={"queue_depth": 1, "current": None,
                                             "backfill_done": True}):
            body = client.get("/matters/stuck-matter/overview").json()
        self.assertEqual(body["building"], {"done": 0, "total": 1, "stuck": 0})

    def test_stuck_when_worker_idle_and_undigested(self):
        with mock.patch.object(digest, "status",
                               return_value={"queue_depth": 0, "current": None,
                                             "backfill_done": True}):
            body = client.get("/matters/stuck-matter/overview").json()
        self.assertEqual(body["building"], {"done": 0, "total": 1, "stuck": 1})

    def test_no_stuck_once_fully_digested(self):
        catalog.replace_facts(self.doc["id"], "stuck-matter", [], digest.EXTRACTOR_VERSION)
        with mock.patch.object(digest, "status",
                               return_value={"queue_depth": 0, "current": None,
                                             "backfill_done": True}):
            body = client.get("/matters/stuck-matter/overview").json()
        self.assertEqual(body["building"], {"done": 1, "total": 1, "stuck": 0})

    def test_not_stuck_when_backfill_sweep_has_not_completed(self):
        # Root-cause fix (sample-matter false stuck positive): idle + undigested is
        # NOT enough — a process that hasn't finished its one-shot startup backfill
        # sweep yet must not accuse docs that simply haven't been enqueued.
        with mock.patch.object(digest, "status",
                               return_value={"queue_depth": 0, "current": None,
                                             "backfill_done": False}):
            body = client.get("/matters/stuck-matter/overview").json()
        self.assertEqual(body["building"], {"done": 0, "total": 1, "stuck": 0})

    def test_stuck_once_backfill_sweep_has_completed(self):
        with mock.patch.object(digest, "status",
                               return_value={"queue_depth": 0, "current": None,
                                             "backfill_done": True}):
            body = client.get("/matters/stuck-matter/overview").json()
        self.assertEqual(body["building"], {"done": 0, "total": 1, "stuck": 1})


if __name__ == "__main__":
    unittest.main(verbosity=2)
