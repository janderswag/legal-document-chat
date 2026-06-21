"""A3/A4 — the Review Grid UI surface (served-asset assertions, test_api_ui style).

The SAM-style app exposes a "Review Grid" nav wired to a view that streams /grid over SSE
(fetch + ReadableStream), renders a sticky document × clause matrix with live skeleton
cells, a found cell's citation chip reusing /kb/highlight, CSV export, and esc()
escape-before-render. No remote asset is referenced (air-gap).
"""

import re
import sys
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

PIPELINE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPELINE_DIR))
import api  # noqa: E402

client = TestClient(api.app)
_EXTERNAL = re.compile(r"""(?:src|href)\s*=\s*["']https?://""", re.IGNORECASE)


class TestGridNav(unittest.TestCase):
    def test_app_shell_has_review_grid_nav(self):
        r = client.get("/app")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Review Grid", r.text)
        self.assertIn('data-view="grid"', r.text)


class TestGridJs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.js = client.get("/static/app.js").text

    def test_registers_grid_view_hook(self):
        self.assertIn("viewHooks.grid", self.js)

    def test_streams_grid_over_sse(self):
        self.assertIn("/grid", self.js)
        self.assertIn("getReader", self.js)        # fetch streaming (POST SSE)
        self.assertIn("parseSseBlock", self.js)

    def test_renders_skeleton_cells(self):
        self.assertIn("skeleton", self.js)
        self.assertIn("buildGridSkeleton", self.js)

    def test_found_cell_reuses_highlight_surface(self):
        self.assertIn("/kb/highlight/", self.js)   # via highlightUrl

    def test_csv_export_present(self):
        self.assertIn("gridToCsv", self.js)
        self.assertIn("review-grid.csv", self.js)

    def test_escapes_model_text(self):
        self.assertRegex(self.js, r"fillGridCell")
        self.assertIn("esc(", self.js)

    def test_no_external_asset_url(self):
        self.assertIsNone(_EXTERNAL.search(self.js))


class TestGridCss(unittest.TestCase):
    def test_sticky_header_and_first_column(self):
        css = client.get("/static/app.css").text
        self.assertIn("grid-table", css)
        self.assertIn("grid-corner", css)
        self.assertIn("position:sticky", css)


if __name__ == "__main__":
    unittest.main(verbosity=2)
