"""A3/A4 — the comparison-grid UI surface (served-asset assertions, test_api_ui style).

UX-2: Compare Documents is a TAB of the "Review & Compare" view, with an EXPLICIT
document picker (UX-4): checkboxes default to all documents; a subset posts doc_ids.
The view streams /grid over SSE (fetch + ReadableStream), renders a sticky document ×
clause matrix with live skeleton cells, a found cell's citation chip reusing
/kb/highlight, CSV export, and esc() escape-before-render. No remote asset (air-gap).
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
    def test_app_shell_has_review_view(self):
        r = client.get("/app")
        self.assertEqual(r.status_code, 200)
        self.assertIn('data-view="review"', r.text)

    def test_compare_documents_is_a_tab(self):
        js = client.get("/static/app.js").text
        self.assertIn("Compare Documents", js)         # tab label
        self.assertIn("viewHooks.grid", js)            # back-compat alias


class TestGridJs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.js = client.get("/static/app.js").text

    def test_has_explicit_document_picker(self):
        # UX-4: the user chooses which documents to compare; a subset posts doc_ids
        self.assertIn("grid-docs", self.js)
        self.assertIn("doc_ids", self.js)
        self.assertIn("refreshGridDocs", self.js)

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

    def test_doc_picker_styles(self):
        css = client.get("/static/app.css").text
        self.assertIn("doc-picker", css)


if __name__ == "__main__":
    unittest.main(verbosity=2)
