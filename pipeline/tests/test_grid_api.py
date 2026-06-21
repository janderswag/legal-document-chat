"""A1/A4 — the /grid loopback SSE route.

POST /grid streams one SSE event per matrix cell (live), after a meta event and before a
done event. The matter is allowlist-validated (400 on unknown); the route is read-only (no
action verbs -> 405). grid.run_grid is monkeypatched so the HTTP/SSE contract is exercised
fast + deterministically; the real LLM matrix is proven in test_grid_live.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

PIPELINE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPELINE_DIR))
import catalog  # noqa: E402
import grid  # noqa: E402
import routes_grid  # noqa: E402
import api  # noqa: E402

client = TestClient(api.app)


def _parse_sse(text):
    events = []
    for block in text.strip().split("\n\n"):
        ev, data = None, None
        for line in block.splitlines():
            if line.startswith("event:"):
                ev = line[6:].strip()
            elif line.startswith("data:"):
                data = json.loads(line[5:].strip())
        if ev:
            events.append((ev, data))
    return events


class TestGridRoute(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls._cat, catalog.DEFAULT_DB = catalog.DEFAULT_DB, cls.tmp / "cat.db"
        catalog.create_matter("Grid Demo")  # slug -> grid-demo
        p = cls.tmp / "d1.pdf"
        p.write_bytes(b"%PDF-1.4 synthetic")
        cls.doc = catalog.add_document("grid-demo", p, status="ready")

    @classmethod
    def tearDownClass(cls):
        catalog.DEFAULT_DB = cls._cat

    def setUp(self):
        self._orig = grid.answer

    def tearDown(self):
        grid.answer = self._orig

    def _fake_answer(self, status="found"):
        def fake(question, matter=None, top_k=5, db_path=None):
            if status == "found":
                return {"answer_text": "yes", "citations": [
                    {"filename": "d1.pdf", "page": 2, "chunk_id": "C1", "span": "x",
                     "char_start": 0, "char_end": 1}], "rejected_claims": [],
                    "grounding_chunks": []}
            from answering import REFUSAL
            return {"answer_text": REFUSAL, "citations": [], "rejected_claims": [],
                    "grounding_chunks": []}
        grid.answer = fake

    def test_streams_meta_cells_done(self):
        self._fake_answer("found")
        r = client.post("/grid", json={"matter": "grid-demo",
                                       "clause_ids": ["governing_law", "indemnification"]})
        self.assertEqual(r.status_code, 200)
        self.assertIn("text/event-stream", r.headers["content-type"])
        events = _parse_sse(r.text)
        kinds = [e for e, _ in events]
        self.assertEqual(kinds[0], "meta")
        self.assertEqual(kinds[-1], "done")
        cells = [d for e, d in events if e == "cell"]
        self.assertEqual(len(cells), 2)  # 1 doc x 2 columns
        for cell in cells:
            self.assertEqual(cell["doc_id"], self.doc["id"])
            self.assertEqual(cell["status"], "found")
            self.assertEqual(cell["citations"][0]["doc_id"], self.doc["id"])

    def test_meta_lists_rows_and_columns(self):
        self._fake_answer("missing")
        r = client.post("/grid", json={"matter": "grid-demo",
                                       "questions": ["custom q one?", "custom q two?"]})
        meta = _parse_sse(r.text)[0][1]
        self.assertEqual(len(meta["docs"]), 1)
        self.assertEqual(len(meta["columns"]), 2)
        self.assertEqual(meta["columns"][0]["question"], "custom q one?")

    def test_unknown_matter_400(self):
        r = client.post("/grid", json={"matter": "no-such"})
        self.assertEqual(r.status_code, 400)

    def test_no_action_verbs(self):
        for verb in ("put", "patch", "delete"):
            self.assertEqual(getattr(client, verb)("/grid").status_code, 405)


if __name__ == "__main__":
    unittest.main(verbosity=2)
