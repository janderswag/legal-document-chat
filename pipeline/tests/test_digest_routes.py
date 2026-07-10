"""M-2 overview API: grouped verified facts + review state; confirm/dismiss flow;
matter fence (404 on unknown matter); date format validation."""

import sys
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

PIPELINE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPELINE_DIR))
import catalog  # noqa: E402
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
        r = client.get("/matters/nimbus-dispute/overview")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual([i["fact_key"] for i in body["deadlines"]], ["dl"])
        self.assertEqual(sorted(i["fact_key"] for i in body["timeline"]), ["dl", "ev"])
        self.assertEqual(body["parties"][0]["value"]["name"], "Nimbus Analytics LLC")
        self.assertEqual(body["deadlines"][0]["filename"], "msa.pdf")
        self.assertIsNone(body["deadlines"][0]["review"])
        self.assertEqual(body["building"], {"done": 0, "total": 1})

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

    def test_bad_status_and_bad_date_rejected(self):
        r = client.post("/matters/nimbus-dispute/facts/dl/review",
                        json={"status": "approved"})
        self.assertEqual(r.status_code, 422)
        r = client.post("/matters/nimbus-dispute/facts/dl/review",
                        json={"status": "confirmed", "confirmed_date": "July 24"})
        self.assertEqual(r.status_code, 422)


if __name__ == "__main__":
    unittest.main(verbosity=2)
