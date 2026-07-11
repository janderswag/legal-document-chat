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


class TestReviewJobSurface(unittest.TestCase):
    """Council 2026-07-11 Move 2: review runs as a streamed background job."""

    @classmethod
    def setUpClass(cls):
        cls.js = client.get("/static/app.js").text
        cls.css = client.get("/static/app.css").text

    def test_submits_a_job_and_streams_its_events(self):
        self.assertIn("/clauses/review-jobs", self.js)
        self.assertIn("/events", self.js)
        self.assertIn("buildReviewSkeleton", self.js)      # meta -> instant skeleton
        self.assertIn("fillReviewRow", self.js)            # clause -> live fill

    def test_cancel_and_inflight_guard_wiring(self):
        self.assertIn("clause-cancel", self.js)
        self.assertIn("/cancel", self.js)
        self.assertIn("if (reviewJob.running) return;", self.js)  # no double submit

    def test_persisted_run_reopens(self):
        self.assertIn("/clauses/runs", self.js)
        self.assertIn("active_job_id", self.js)            # resume a live run
        self.assertIn("documents changed since this review", self.js)  # staleness

    def test_exports_present_with_sams_caveat(self):
        for token in ("clause-copy", "clause-md", "clause-word",
                      "/clauses/review.docx", "reviewMarkdown", "reviewPlainText"):
            self.assertIn(token, self.js)
        # Sam's rider: the scope caveat rides the UI foot and every export builder
        self.assertIn("most relevant", self.js)
        self.assertIn("REVIEW_CAVEAT", self.js)
        for builder in ("reviewPlainText", "reviewMarkdown"):
            i = self.js.index("function " + builder)
            self.assertIn("REVIEW_CAVEAT", self.js[i:i + 900], builder)
        # per-clause verification status on exports
        self.assertIn("Found (span-verified)", self.js)

    def test_scope_type_and_custom_question_controls(self):
        for token in ("clause-scope", "Whole matter", "clause-type",
                      "services_agreement", "clause-custom", "Add your own question"):
            self.assertIn(token, self.js)

    def test_skeleton_styles_exist(self):
        self.assertIn(".clause-badge.pending", self.css)
        self.assertIn(".clause-badge.stale", self.css)
        self.assertIn(".clause-controls", self.css)

    def test_stale_stream_guard(self):
        # Review finding #1: matter A's clauses must never render under matter
        # B's picker — streams are epoch-tagged and the matter switch resets.
        self.assertIn("reviewJob.epoch", self.js)
        self.assertIn("resetReviewView", self.js)
        self.assertIn("myEpoch !== reviewJob.epoch", self.js)

    def test_markdown_red_flags_sort_first(self):
        # Review finding #2: ranks start at 1 so `|| 4` can never swallow the
        # potentially_missing rank (0 was falsy and sorted red flags LAST).
        i = self.js.index("function reviewMarkdown")
        seg = self.js[i:i + 1400]
        self.assertIn("potentially_missing: 1", seg)
        self.assertNotIn("potentially_missing: 0", seg)


class TestContractReviewCss(unittest.TestCase):
    def test_has_distinct_missing_badge_style(self):
        css = client.get("/static/app.css").text
        self.assertIn("clause", css, "no Contract Review styling present")

    def test_has_tab_styles(self):
        css = client.get("/static/app.css").text
        self.assertIn("tab-row", css)


if __name__ == "__main__":
    unittest.main(verbosity=2)
