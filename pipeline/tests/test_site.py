"""D-58 v1 — landing page content guards (site/, static).

The public landing page must clearly present the three downloads (Ollama -> models -> app),
a macOS download CTA + "Windows coming soon", the privacy framing, and a demo placeholder.
These guards keep that messaging from silently regressing. (Web fonts / outbound download
links are intentional here — this is the PUBLIC page, not the air-gapped app.)
"""

import unittest
from pathlib import Path

SITE = Path(__file__).resolve().parent.parent.parent / "site"


class TestLandingPage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (SITE / "index.html").read_text(encoding="utf-8")
        cls.css = (SITE / "styles.css").read_text(encoding="utf-8")

    def test_three_downloads_present(self):
        low = self.html.lower()
        self.assertIn("ollama", low)                       # 1) engine
        self.assertIn("ollama pull qwen3:14b", self.html)  # 2) models
        self.assertIn("ollama pull bge-m3", self.html)
        self.assertIn("download for macos", low)           # 3) the app

    def test_macos_cta_points_at_releases(self):
        self.assertRegex(self.html, r"github\.com/[\w.-]+/[\w.-]+/releases")

    def test_windows_coming_soon(self):
        self.assertIn("coming soon", self.html.lower())

    def test_privacy_framing(self):
        low = self.html.lower()
        self.assertIn("100% local", low)
        self.assertIn("no telemetry", low)
        self.assertIn("downloads the models from the internet", low)

    def test_demo_placeholder_present(self):
        self.assertIn("demo-placeholder", self.html)
        self.assertIn("Demo recording", self.html)

    def test_pages_wiring_present(self):
        self.assertTrue((SITE / ".nojekyll").exists())
        wf = (SITE.parent / ".github" / "workflows" / "deploy-site.yml").read_text()
        self.assertIn("workflow_dispatch", wf)             # manual only — never auto-deploys

    def test_static_assets_exist(self):
        for f in ("styles.css", "script.js", "favicon.svg"):
            self.assertTrue((SITE / f).is_file(), f"missing site/{f}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
