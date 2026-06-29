"""D-58 v1 — in-app first-run wizard backend (/setup).

/setup/status detects whether the local Ollama is reachable on 127.0.0.1:11434 and whether
the pinned models (qwen3:14b, bge-m3) are present, returning a structured readiness object
the wizard renders. The Ollama probe is monkeypatchable so BOTH states are testable
(reachable+models present -> ready; not found -> guided). Loopback-only; no telemetry.
"""

import sys
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

PIPELINE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPELINE_DIR))
import routes_setup  # noqa: E402  (module under test)
import api  # noqa: E402

client = TestClient(api.app)


class TestModelMatch(unittest.TestCase):
    def test_exact_and_latest_and_base(self):
        self.assertTrue(routes_setup._model_present("qwen3:14b", ["qwen3:14b"]))
        self.assertTrue(routes_setup._model_present("qwen3:14b", ["qwen3:14b:latest"]))
        self.assertTrue(routes_setup._model_present("bge-m3", ["bge-m3:latest"]))
        self.assertTrue(routes_setup._model_present("bge-m3", ["bge-m3"]))

    def test_absent_and_near_miss(self):
        self.assertFalse(routes_setup._model_present("qwen3:14b", ["qwen3:8b", "llama3"]))
        self.assertFalse(routes_setup._model_present("bge-m3", []))


class TestSetupStatus(unittest.TestCase):
    def setUp(self):
        self._orig = routes_setup._ollama_tags

    def tearDown(self):
        routes_setup._ollama_tags = self._orig

    def test_ready_when_reachable_and_models_present(self):
        routes_setup._ollama_tags = lambda *a, **k: ["qwen3:14b", "bge-m3:latest", "llama3"]
        s = client.get("/setup/status").json()
        self.assertTrue(s["ollama_reachable"])
        self.assertTrue(s["ready"])
        self.assertTrue(s["models"]["qwen3:14b"])
        self.assertTrue(s["models"]["bge-m3"])
        self.assertEqual(s["missing"], [])

    def test_not_ready_when_a_model_is_missing(self):
        routes_setup._ollama_tags = lambda *a, **k: ["qwen3:14b"]  # bge-m3 missing
        s = client.get("/setup/status").json()
        self.assertTrue(s["ollama_reachable"])
        self.assertFalse(s["ready"])
        self.assertIn("bge-m3", s["missing"])

    def test_not_reachable_simulated(self):
        def boom(*a, **k):
            raise OSError("connection refused")
        routes_setup._ollama_tags = boom
        s = client.get("/setup/status").json()
        self.assertFalse(s["ollama_reachable"])
        self.assertFalse(s["ready"])
        self.assertEqual(set(s["missing"]), {"qwen3:14b", "bge-m3"})
        # the exact pull commands are surfaced for the guide
        self.assertIn("ollama pull qwen3:14b", " ".join(s["pull_commands"]))


class TestSetupPage(unittest.TestCase):
    def test_setup_page_served_locally(self):
        r = client.get("/setup")
        self.assertEqual(r.status_code, 200)
        self.assertIn("text/html", r.headers["content-type"])
        self.assertIn("/setup/status", r.text + client.get("/static/setup.js").text)

    def test_no_external_asset_urls(self):
        for body in (client.get("/setup").text, client.get("/static/setup.js").text):
            self.assertNotRegex(body, r"""(?:src|href)\s*=\s*["']https?://""")


if __name__ == "__main__":
    unittest.main(verbosity=2)
