"""P0.2 — warm, right-sized production inference path (owner-approved 2026-07-06).

The production Ollama calls (_post_chat and _stream_tokens) must send keep_alive
(model stays warm between questions — no ~5.5s cold reload after a short idle) and an
explicit options.num_ctx (KV cache sized to the real 5-chunk prompt, not the Ollama
default). preload_model() loads weights with NO messages and NO document data, never
raises, and reports success/failure. None of this touches the verifier or retrieval.
"""

import io
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

PIPELINE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPELINE_DIR))
import answering  # noqa: E402


def _capture_urlopen(captured, lines=None, payload=None):
    """A fake urllib.request.urlopen that records the request body."""
    class _Resp(io.BytesIO):
        def __init__(self):
            super().__init__(b"\n".join(lines) if lines else json.dumps(payload).encode())
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False

    def fake(req, timeout=None):
        captured.append(json.loads(req.data.decode("utf-8")))
        return _Resp()
    return fake


MSGS = [{"role": "system", "content": "s"}, {"role": "user", "content": "q"}]


class TestWarmInferencePath(unittest.TestCase):
    def test_post_chat_sends_keep_alive_and_num_ctx(self):
        captured = []
        fake = _capture_urlopen(captured, payload={"message": {"content": "ok"}})
        with patch.object(answering.urllib.request, "urlopen", fake):
            answering._post_chat(MSGS)
        body = captured[0]
        self.assertEqual(body["keep_alive"], answering.KEEP_ALIVE)
        self.assertEqual(body["options"]["num_ctx"], answering.NUM_CTX)
        self.assertEqual(body["options"]["temperature"], 0)  # parity preserved
        self.assertFalse(body["think"])

    def test_stream_tokens_sends_keep_alive_and_num_ctx(self):
        captured = []
        lines = [json.dumps({"message": {"content": "hi"}}).encode(),
                 json.dumps({"message": {"content": ""}, "done": True}).encode()]
        fake = _capture_urlopen(captured, lines=lines)
        with patch.object(answering.urllib.request, "urlopen", fake):
            list(answering._stream_tokens(MSGS))
        body = captured[0]
        self.assertEqual(body["keep_alive"], answering.KEEP_ALIVE)
        self.assertEqual(body["options"]["num_ctx"], answering.NUM_CTX)

    def test_preload_sends_no_messages_and_no_document_data(self):
        captured = []
        fake = _capture_urlopen(captured, payload={"done": True})
        with patch.object(answering.urllib.request, "urlopen", fake):
            self.assertTrue(answering.preload_model())
        body = captured[0]
        self.assertEqual(body["messages"], [])  # weights only — no prompt, no documents
        self.assertEqual(body["keep_alive"], answering.KEEP_ALIVE)

    def test_preload_never_raises_when_ollama_is_down(self):
        def boom(req, timeout=None):
            raise OSError("connection refused")
        with patch.object(answering.urllib.request, "urlopen", boom):
            self.assertFalse(answering.preload_model())


if __name__ == "__main__":
    unittest.main(verbosity=2)
