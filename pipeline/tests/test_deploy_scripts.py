"""Task 7 proof: scripted redeploy + restore (SC-7), compose-only loopback (D-43a).

Static guards (the live drill is run separately, egress-monitored): the deploy scripts
exist and are executable; NO script publishes 0.0.0.0 or uses a bare `docker run -p`
(compose-only); docker-compose.yml still binds 127.0.0.1:8000:8000 (never 0.0.0.0)."""

import os
import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEPLOY = REPO_ROOT / "deploy"
COMPOSE = REPO_ROOT / "docker-compose.yml"
SCRIPTS = ["up.sh", "down.sh", "restore.sh"]


class TestDeployScripts(unittest.TestCase):
    def test_scripts_exist_and_executable(self):
        for s in SCRIPTS:
            p = DEPLOY / s
            self.assertTrue(p.is_file(), f"missing {s}")
            self.assertTrue(os.access(p, os.X_OK), f"{s} not executable")
        self.assertTrue((DEPLOY / "README.md").is_file(), "missing deploy/README.md")

    def test_no_script_publishes_0_0_0_0(self):
        for s in SCRIPTS:
            text = (DEPLOY / s).read_text()
            self.assertNotIn("0.0.0.0", text, f"{s} references 0.0.0.0")

    def test_no_script_uses_bare_docker_run_p(self):
        # compose-only (D-43a): a `docker run -p ...` would bypass the loopback bind.
        pat = re.compile(r"docker\s+run\b[^\n]*\s-p\b")
        for s in SCRIPTS:
            text = (DEPLOY / s).read_text()
            self.assertIsNone(pat.search(text), f"{s} uses `docker run -p` (must be compose-only)")

    def test_no_script_sets_ollama_host(self):
        for s in SCRIPTS:
            self.assertNotIn("OLLAMA_HOST", (DEPLOY / s).read_text(), f"{s} sets OLLAMA_HOST")

    def test_compose_binds_loopback_only(self):
        text = COMPOSE.read_text()
        self.assertIn("127.0.0.1:8000:8000", text)
        # a published 0.0.0.0 bind would be on an operative (non-comment) line; an
        # explanatory comment naming the rule is fine.
        operative = "\n".join(l for l in text.splitlines() if not l.strip().startswith("#"))
        self.assertNotIn("0.0.0.0", operative)


if __name__ == "__main__":
    unittest.main(verbosity=2)
