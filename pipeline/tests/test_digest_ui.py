"""M-2 UI wiring: the overview container sits above the dropzone (layout B), the
renderer exists, every dynamic string passes esc(), and the confirm flow posts to
the review API. Static assertions only — behavior is smoke-tested in the app."""

import sys
import unittest
from pathlib import Path

PIPELINE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPELINE_DIR))

APP_JS = (PIPELINE_DIR / "static" / "app.js").read_text()
APP_CSS = (PIPELINE_DIR / "static" / "app.css").read_text()


class TestOverviewUI(unittest.TestCase):
    def test_container_above_dropzone(self):
        detail = APP_JS[APP_JS.index("function showMatterDetail"):]
        self.assertLess(detail.index("matter-overview"), detail.index("matter-dropzone"))

    def test_renderer_and_api_wiring(self):
        self.assertIn("function renderMatterOverview", APP_JS)
        self.assertIn("/overview", APP_JS)
        self.assertIn("/review", APP_JS)
        self.assertIn("needs your date", APP_JS)          # relative-deadline chip
        self.assertIn("confirmed by you", APP_JS)         # confirmed chip

    def test_deposition_digest_container_untouched(self):
        self.assertIn("matter-digest", APP_JS)            # transcript digest keeps its div

    def test_css_added(self):
        self.assertIn(".ov-due", APP_CSS)
        self.assertIn("#matter-dropzone.slim", APP_CSS)

    def test_overview_href_encodes_apostrophes(self):
        # encodeURIComponent leaves ' raw; srcLine must percent-encode it or a span
        # like "tenant's deposit" breaks out of the single-quoted href attribute
        self.assertIn('replace(/\'/g, "%27")', APP_JS)

    def test_timeline_rows_cite_source(self):
        # Spec: "every row cited to a verbatim source span and click-through" — the
        # timeline rows must not be the one uncited exception (F5).
        self.assertIn("function ovHref", APP_JS)
        tl = APP_JS[APP_JS.index("function tlRow"):APP_JS.index("function groupBy")]
        self.assertIn("ovHref", tl)
        self.assertIn("ov-cite", tl)


if __name__ == "__main__":
    unittest.main(verbosity=2)
