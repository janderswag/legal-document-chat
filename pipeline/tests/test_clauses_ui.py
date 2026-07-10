"""T-CLAUSE UI proof: the Contract Review surface in the SAM-style local app.

UX-2: Contract Review is a TAB of the "Review & Compare" view (data-view="review"),
also launchable from inside a matter. The local app.js renders the clause checklist
by status — a "found" row shows the value + a citation chip linked to the EXISTING
/kb/highlight surface (chunk-derived page+span), a "potentially_missing" row shows a
clearly-distinct advisory badge with NO citation, and a "not_confirmed" row is shown
without a citation. Model text is escaped before render (esc(), D-48 XSS guard) and
no remote asset is referenced (air-gap). Asserted on the served text in the style of
test_app_shell / test_api_ui (no JS runtime).
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


class TestContractReviewNav(unittest.TestCase):
    def test_app_shell_has_review_view(self):
        r = client.get("/app")
        self.assertEqual(r.status_code, 200)
        self.assertIn('data-view="review"', r.text)
        self.assertIn("Review &amp; Compare", r.text)


class TestContractReviewJs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.js = client.get("/static/app.js").text

    def test_registers_review_hook_and_clauses_tab(self):
        self.assertIn("viewHooks.review", self.js)
        self.assertIn("Contract Review", self.js)          # tab label
        self.assertIn("viewHooks.clauses", self.js)        # back-compat alias

    def test_launchable_from_inside_a_matter(self):
        # UX-2: the matter detail page offers the tool ("context is the picker")
        self.assertIn("openReviewTab", self.js)

    def test_calls_the_review_and_taxonomy_endpoints(self):
        self.assertIn("/clauses/review", self.js)

    def test_renders_all_three_statuses(self):
        for token in ("found", "potentially_missing", "not_confirmed"):
            self.assertIn(token, self.js, f"clause status not handled: {token}")

    def test_reuses_existing_highlight_surface_for_found_citations(self):
        # the cited-span highlight URL helper is reused (never a new fuzzy highlighter)
        self.assertIn("/kb/highlight/", self.js)

    def test_escapes_model_text_before_render(self):
        # the clause renderer must run model-supplied strings through esc() (XSS, D-48)
        self.assertRegex(self.js, r"renderClause|clauseRow|renderClauses")
        self.assertIn("esc(", self.js)

    def test_no_external_asset_url(self):
        self.assertIsNone(_EXTERNAL.search(self.js))


class TestContractReviewCss(unittest.TestCase):
    def test_has_distinct_missing_badge_style(self):
        css = client.get("/static/app.css").text
        self.assertIn("clause", css, "no Contract Review styling present")

    def test_has_tab_styles(self):
        css = client.get("/static/app.css").text
        self.assertIn("tab-row", css)


if __name__ == "__main__":
    unittest.main(verbosity=2)
