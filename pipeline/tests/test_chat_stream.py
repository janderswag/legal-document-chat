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
import routes_chat  # noqa: E402
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

    def test_sources_event_precedes_tokens(self):
        # P0.1: the retrieved (chunk-derived) passages stream FIRST so the UI can show
        # what the model is reading before the first token — candidates only, never
        # presented as verified citations (those still come only from 'done').
        full = ('The monthly fee is $1,234 '
                '[document: d.pdf, page: 1, chunk: C1, span: "$1,234"].')
        self._set_tokens(full)
        r = client.post("/chat/stream", json={"question": "fee?", "matter": "stream-demo"})
        events = _parse_sse(r.text)
        kinds = [e for e, _ in events]
        self.assertIn("sources", kinds)
        self.assertLess(kinds.index("sources"), kinds.index("token"))
        srcs = events[kinds.index("sources")][1]["sources"]
        self.assertEqual(srcs[0]["filename"], "d.pdf")
        self.assertEqual(srcs[0]["page"], 1)
        self.assertIn("snippet", srcs[0])
        self.assertNotIn("citations", events[kinds.index("sources")][1],
                         "sources event must not carry citations")

    def test_streamed_fabrication_is_not_verified(self):
        full = ('The monthly fee is $9,999 '
                '[document: d.pdf, page: 1, chunk: C1, span: "$9,999"].')
        self._set_tokens(full)
        r = client.post("/chat/stream", json={"question": "fee?", "matter": "stream-demo"})
        done = _parse_sse(r.text)[-1][1]
        self.assertEqual(done["citations"], [], "streamed fabrication was verified!")


class TestChatHistoryOneSession(unittest.TestCase):
    """Sprint 8 (owner bug, screenshot): consecutive sends in the same chat window must
    append to ONE Chat History thread, never spawn a new row per message.

    The client already carried thread_id correctly (state.threadId round-trips through
    the 'done' SSE event — verified by the first two tests below, which pass unchanged).
    The reproducible gap was server-side: citation enrichment (doc_id/line lookups) ran
    UNGUARDED after a fully successful generation, so a lookup failure there raised past
    chat_stream()'s only `except ValueError`, aborting the SSE stream before the 'done'
    event (and its thread_id) ever reached the client. The client then had no thread_id
    to send on the next message, so it started a brand-new thread — exactly the "one
    session became two/N Chat History rows" symptom. Fixed by routes_chat._enrich_citations
    (routes_chat.py), which never lets enrichment cost the client the done event."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls._cat, catalog.DEFAULT_DB = catalog.DEFAULT_DB, cls.tmp / "cat.db"
        cls._db, routes_kb.KB_DB = routes_kb.KB_DB, cls.tmp / ".lancedb_kb"

    @classmethod
    def tearDownClass(cls):
        catalog.DEFAULT_DB = cls._cat
        routes_kb.KB_DB = cls._db

    def setUp(self):
        # A fresh matter per test (named after the test method) keeps thread counts
        # exact and isolated between tests sharing the class-level tmp catalog.
        self.slug = catalog.create_matter("Session Demo " + self._testMethodName)["slug"]
        self._retr, self._stream = answering.retrieve, answering._stream_tokens
        self._enrich_doc_ids = routes_chat._enrich_doc_ids
        chunk = {"source_filename": "d.pdf", "matter": self.slug, "page_number": 1,
                 "section": "S", "char_start": 0, "char_end": 40,
                 "text": "The monthly fee is $1,234 per the terms."}
        answering.retrieve = lambda *a, **k: [chunk]
        full = ('The monthly fee is $1,234 '
                '[document: d.pdf, page: 1, chunk: C1, span: "$1,234"].')
        answering._stream_tokens = lambda *a, **k: iter([full])

    def tearDown(self):
        answering.retrieve, answering._stream_tokens = self._retr, self._stream
        routes_chat._enrich_doc_ids = self._enrich_doc_ids

    def _threads(self):
        return [t for t in catalog.list_threads() if t["matter_slug"] == self.slug]

    def test_two_posts_with_returned_thread_id_append_to_one_thread(self):
        r1 = client.post("/chat/stream",
                         json={"question": "tell me about this document", "matter": self.slug})
        tid = _parse_sse(r1.text)[-1][1]["thread_id"]
        self.assertIsNotNone(tid)

        r2 = client.post("/chat/stream", json={"question": "what was the hardware selection?",
                                                "matter": self.slug, "thread_id": tid})
        self.assertEqual(_parse_sse(r2.text)[-1][1]["thread_id"], tid)

        threads = self._threads()
        self.assertEqual(len(threads), 1, "two posts with the same thread_id must not fork")
        msgs = catalog.get_thread_messages(threads[0]["id"])
        self.assertEqual([m["role"] for m in msgs], ["user", "assistant", "user", "assistant"])

    def test_post_without_thread_id_starts_a_new_thread(self):
        r1 = client.post("/chat/stream", json={"question": "first question", "matter": self.slug})
        tid1 = _parse_sse(r1.text)[-1][1]["thread_id"]

        r2 = client.post("/chat/stream",
                         json={"question": "second, unrelated question", "matter": self.slug})
        tid2 = _parse_sse(r2.text)[-1][1]["thread_id"]

        self.assertNotEqual(tid1, tid2)
        self.assertEqual(len(self._threads()), 2)

    def test_enrichment_failure_still_delivers_thread_id_so_the_next_send_appends(self):
        # Reproduces the actual root cause: citation enrichment raises AFTER a fully
        # successful generation. Before the fix this aborted the SSE stream before the
        # 'done' event, so the client never learned the thread_id.
        def boom(*a, **k):
            raise RuntimeError("simulated catalog lookup failure")
        routes_chat._enrich_doc_ids = boom

        r1 = client.post("/chat/stream",
                         json={"question": "tell me about this document", "matter": self.slug})
        events1 = _parse_sse(r1.text)
        self.assertIn("done", [e for e, _ in events1],
                      "enrichment failure must not swallow the done event")
        done1 = events1[-1][1]
        tid = done1["thread_id"]
        self.assertIsNotNone(tid)
        self.assertTrue(done1["citations"], "the verified answer must survive enrichment failure")
        self.assertIsNone(done1["citations"][0].get("doc_id"),
                          "doc_id decoration is best-effort and absent here, not fabricated")

        routes_chat._enrich_doc_ids = self._enrich_doc_ids  # restore for the follow-up send
        r2 = client.post("/chat/stream", json={"question": "what was the hardware selection?",
                                                "matter": self.slug, "thread_id": tid})
        self.assertEqual(_parse_sse(r2.text)[-1][1]["thread_id"], tid)

        threads = self._threads()
        self.assertEqual(len(threads), 1)
        self.assertEqual(len(catalog.get_thread_messages(threads[0]["id"])), 4)


if __name__ == "__main__":
    unittest.main(verbosity=2)
