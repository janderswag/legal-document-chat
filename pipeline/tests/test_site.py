"""D-58 v1 / D-61 — landing page content guards (site/, static).

The public landing page must clearly present the setup story (Ollama -> models -> app),
a macOS download CTA + "Windows coming soon", the privacy framing, and the live demo embed.
These guards keep that messaging from silently regressing. (Web fonts / outbound download
links are intentional here — this is the PUBLIC page, not the air-gapped app.)

Updated for D-61: the landing was redesigned to embed the animated demo (`demo.html`) instead
of a static `demo.png` + video-slot, and replaced raw `ollama pull` commands with first-run
wizard copy; the Pages workflow is now `pages.yml` (auto-deploys site/ on push), superseding the
manual `deploy-site.yml`. Brand/security/deploy specifics live in test_site_brand.py.
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
        # Setup story = Ollama (engine) -> the two models -> the app. The redesigned landing
        # surfaces the models in the stack diagram + wizard copy rather than raw pull commands.
        low = self.html.lower()
        self.assertIn("ollama", low)                       # 1) engine
        self.assertIn("qwen3", low)                        # 2) models (in the stack diagram)
        self.assertIn("bge-m3", low)
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

    def test_live_demo_embed_present(self):
        # The hero product shot is the animated demo (demo.html) embedded in an iframe.
        self.assertIn('src="demo.html"', self.html)
        self.assertTrue((SITE / "demo.html").is_file(), "site/demo.html missing (self-contained)")
        self.assertTrue((SITE / "demo.js").is_file(), "site/demo.js missing (CSP: external script)")

    def test_demo_embed_is_not_interactive(self):
        # The embedded demo must be a non-interactive product shot (taken out of the tab order),
        # not something a visitor clicks into.
        figure = self.html[self.html.index('class="hero-shot'):]
        figure = figure[:figure.index("</figure>")]
        self.assertIn('tabindex="-1"', figure, "demo iframe must be non-interactive (tabindex=-1)")

    def test_audience_copy_is_general_not_solo_exclusive(self):
        low = self.html.lower()
        self.assertNotIn("solo attorney", low)              # broadened
        self.assertIn("attorneys", low)

    def test_pages_wiring_present(self):
        self.assertTrue((SITE / ".nojekyll").exists())
        # D-61: pages.yml auto-deploys site/ on push (supersedes the manual deploy-site.yml).
        wf = (SITE.parent / ".github" / "workflows" / "pages.yml").read_text()
        self.assertIn("deploy-pages", wf)                  # the Pages deploy action
        self.assertIn("push", wf)                          # auto-deploys on push

    def test_static_assets_exist(self):
        for f in ("styles.css", "script.js", "favicon.svg"):
            self.assertTrue((SITE / f).is_file(), f"missing site/{f}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
