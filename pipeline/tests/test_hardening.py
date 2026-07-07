"""Move 3a/3b (D-71) — loopback is not a boundary: DNS-rebinding and cross-site
request shapes must be rejected; the app's own requests must be unaffected; the
launcher must refuse to start a known-vulnerable Ollama and must set the
browser-origin allowlist on the one it starts."""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

PIPELINE_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = PIPELINE_DIR.parent
sys.path.insert(0, str(PIPELINE_DIR))
sys.path.insert(0, str(REPO_ROOT / "desktop"))
import api  # noqa: E402
import launcher  # noqa: E402

client = TestClient(api.app)


class TestOriginGuard(unittest.TestCase):
    def test_cross_origin_post_rejected(self):
        # a malicious page fetch()ing the local API cross-origin
        r = client.post("/matters", json={"display_name": "x"},
                        headers={"Origin": "https://evil.example.com"})
        self.assertEqual(r.status_code, 403)

    def test_cross_origin_delete_rejected(self):
        r = client.delete("/kb/documents/1", headers={"Origin": "http://evil.test"})
        self.assertEqual(r.status_code, 403)

    def test_local_origin_posts_pass_the_guard(self):
        # same-origin browser POSTs carry a local Origin; must NOT be 403
        r = client.post("/chat", json={"question": "", "matter": "none"},
                        headers={"Origin": "http://127.0.0.1:8000"})
        self.assertNotEqual(r.status_code, 403)

    def test_no_origin_unaffected(self):
        r = client.post("/chat", json={"question": "", "matter": "none"})
        self.assertNotEqual(r.status_code, 403)   # fails on validation (400), not CSRF

    def test_gets_unaffected_by_origin(self):
        r = client.get("/health", headers={"Origin": "https://evil.example.com"})
        self.assertEqual(r.status_code, 200)


class TestTrustedHost(unittest.TestCase):
    def test_dns_rebinding_host_rejected(self):
        # rebinding: attacker's domain resolves to 127.0.0.1 -> Host header is theirs
        r = client.get("/health", headers={"Host": "attacker.example.com"})
        self.assertEqual(r.status_code, 400)

    def test_local_host_served(self):
        r = client.get("/health", headers={"Host": "127.0.0.1:8000"})
        self.assertEqual(r.status_code, 200)


class TestOllamaHardening(unittest.TestCase):
    def test_env_includes_origin_allowlist(self):
        self.assertEqual(launcher.OLLAMA_ENV["OLLAMA_ORIGINS"], "http://127.0.0.1:8000")

    def test_known_vulnerable_version_is_refused(self):
        with patch.object(launcher, "port_in_use", return_value=False), \
             patch.object(launcher, "find_ollama", return_value="/fake/ollama"), \
             patch.object(launcher, "ollama_version", return_value=(0, 16, 9)), \
             patch.object(launcher.subprocess, "Popen") as popen:
            self.assertIsNone(launcher.ensure_ollama())
            popen.assert_not_called()

    def test_current_version_starts(self):
        states = iter([False, True])
        with patch.object(launcher, "port_in_use",
                          side_effect=lambda *a, **k: next(states, True)), \
             patch.object(launcher, "find_ollama", return_value="/fake/ollama"), \
             patch.object(launcher, "ollama_version", return_value=(0, 18, 0)), \
             patch.object(launcher.subprocess, "Popen", return_value="PROC") as popen:
            self.assertEqual(launcher.ensure_ollama(), "PROC")
            popen.assert_called_once()

    def test_undeterminable_version_fails_open(self):
        states = iter([False, True])
        with patch.object(launcher, "port_in_use",
                          side_effect=lambda *a, **k: next(states, True)), \
             patch.object(launcher, "find_ollama", return_value="/fake/ollama"), \
             patch.object(launcher, "ollama_version", return_value=None), \
             patch.object(launcher.subprocess, "Popen", return_value="PROC"):
            self.assertEqual(launcher.ensure_ollama(), "PROC")


if __name__ == "__main__":
    unittest.main(verbosity=2)
