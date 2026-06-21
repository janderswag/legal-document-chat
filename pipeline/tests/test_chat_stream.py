"""B6 — streaming-token chat over SSE (perceived latency only).

POST /chat/stream streams the answer tokens live, then emits a final 'done' event whose
citations are the result of running the EXACT mechanical verifier on the COMPLETE answer
text — never on a partial. Streaming changes perceived latency only; it must not change
which citations are verified (never-false-accept, D-19/D-38). The token source + retrieval
are monkeypatched for a fast, deterministic contract test.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

PIPELINE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPELINE_DIR))
import answering  # noqa: E402
import catalog  # noqa: E402
import routes_kb  # noqa: E402
import api  # noqa: E402

client = TestClient(api.app)


def _parse_sse(text):
    out = []
    for block in text.strip().split("\n\n"):
        ev = data = None
        for line in block.splitlines():
            if line.startswith("event:"):
                ev = line[6:].strip()
            elif line.startswith("data:"):
                data = json.loads(line[5:].strip())
        if ev:
            out.append((ev, data))
    return out


class TestChatStream(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls._cat, catalog.DEFAULT_DB = catalog.DEFAULT_DB, cls.tmp / "cat.db"
        cls._db, routes_kb.KB_DB = routes_kb.KB_DB, cls.tmp / ".lancedb_kb"
        catalog.create_matter("Stream Demo")  # slug -> stream-demo

    @classmethod
    def tearDownClass(cls):
        catalog.DEFAULT_DB = cls._cat
        routes_kb.KB_DB = cls._db

    def setUp(self):
        self._retr, self._stream = answering.retrieve, answering._stream_tokens
        chunk = {"source_filename": "d.pdf", "matter": "stream-demo", "page_number": 1,
                 "section": "S", "char_start": 0, "char_end": 40,
                 "text": "The monthly fee is $1,234 per the terms."}
        answering.retrieve = lambda *a, **k: [chunk]

    def tearDown(self):
        answering.retrieve, answering._stream_tokens = self._retr, self._stream

    def _set_tokens(self, full):
        # stream the text in a few chunks (simulate token deltas)
        mid = len(full) // 2
        answering._stream_tokens = lambda *a, **k: iter([full[:mid], full[mid:]])

    def test_streams_tokens_then_verified_done(self):
        full = ('The monthly fee is $1,234 '
                '[document: d.pdf, page: 1, chunk: C1, span: "$1,234"].')
        self._set_tokens(full)
        r = client.post("/chat/stream", json={"question": "fee?", "matter": "stream-demo"})
        self.assertEqual(r.status_code, 200)
        self.assertIn("text/event-stream", r.headers["content-type"])
        events = _parse_sse(r.text)
        kinds = [e for e, _ in events]
        self.assertIn("token", kinds)
        self.assertEqual(kinds[-1], "done")
        done = events[-1][1]
        self.assertTrue(done["citations"])
        self.assertEqual(done["citations"][0]["filename"], "d.pdf")
        self.assertIsNotNone(done["thread_id"])

    def test_streamed_fabrication_is_not_verified(self):
        full = ('The monthly fee is $9,999 '
                '[document: d.pdf, page: 1, chunk: C1, span: "$9,999"].')
        self._set_tokens(full)
        r = client.post("/chat/stream", json={"question": "fee?", "matter": "stream-demo"})
        done = _parse_sse(r.text)[-1][1]
        self.assertEqual(done["citations"], [], "streamed fabrication was verified!")


if __name__ == "__main__":
    unittest.main(verbosity=2)
