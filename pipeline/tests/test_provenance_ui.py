"""Council 2026-07-11 Move 3, F3 + decision #4 — the UI wears provenance.

Imported documents show a source badge (service + date, attachment lineage) on
the Unfiled tray and the matter ledger; a connection's configured matter is a
SUGGESTION chip ("File to ...") the attorney confirms, never an auto-file; the
connect form says so. Static assertions on the served JS/CSS, matching the
repo idiom (test_clauses_ui / test_digest_ui)."""

import sys
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

PIPELINE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPELINE_DIR))
import api  # noqa: E402

client = TestClient(api.app)


class TestProvenanceUi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.js = client.get("/static/app.js").text
        cls.css = client.get("/static/app.css").text

    def test_source_badge_rendered_from_source_json(self):
        self.assertIn("function sourceBadgeHtml", self.js)
        self.assertIn("source_json", self.js)
        self.assertIn("attachment_of", self.js)
        # badge appears on BOTH the unfiled tray and the matter ledger
        for fn in ("refreshUnfiled", "refreshMatterDocs"):
            i = self.js.index("function " + fn)
            self.assertIn("sourceBadgeHtml", self.js[i:i + 2600], fn)

    def test_badge_styles_exist(self):
        self.assertIn(".src-badge", self.css)

    def test_suggested_matter_is_confirm_only(self):
        self.assertIn("suggested_matter", self.js)
        self.assertIn("File to ", self.js)
        self.assertIn("data-file-doc", self.js)

    def test_connect_form_says_unfiled_first(self):
        self.assertIn("Suggest a matter for imports", self.js)
        self.assertIn("Everything imports into", self.js)


if __name__ == "__main__":
    unittest.main(verbosity=2)
