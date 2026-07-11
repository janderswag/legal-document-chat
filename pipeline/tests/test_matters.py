"""Task 2 proof: SQLite matters catalog + /matters routes (the D-18 spine).

Slugs are path-safe/validated (no injection); duplicates and empty names rejected;
list_matters carries doc_count. Catalog DB is overridable for tests (temp DB)."""

import sys
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

PIPELINE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPELINE_DIR))
import catalog  # noqa: E402
import api  # noqa: E402

client = TestClient(api.app)


class TestCatalogMatters(unittest.TestCase):
    def setUp(self):
        self.db = Path(tempfile.mkdtemp()) / "cat.db"

    def test_create_matter_returns_path_safe_slug(self):
        m = catalog.create_matter("Pemberton Logistics", db_path=self.db)
        self.assertEqual(m["slug"], "pemberton-logistics")
        self.assertNotIn("/", m["slug"])
        self.assertNotIn("..", m["slug"])
        self.assertNotIn(" ", m["slug"])

    def test_slug_strips_unsafe_characters(self):
        m = catalog.create_matter("../../etc/passwd & Co.", db_path=self.db)
        self.assertNotIn("/", m["slug"])
        self.assertNotIn("..", m["slug"])
        self.assertNotIn("\\", m["slug"])
        self.assertTrue(m["slug"])

    def test_duplicate_display_name_rejected(self):
        catalog.create_matter("Acme Corp", db_path=self.db)
        with self.assertRaises(ValueError):
            catalog.create_matter("Acme Corp", db_path=self.db)

    def test_empty_name_rejected(self):
        with self.assertRaises(ValueError):
            catalog.create_matter("   ", db_path=self.db)
        with self.assertRaises(ValueError):
            catalog.create_matter("///", db_path=self.db)  # slugs to empty

    def test_list_matters_includes_doc_count_zero(self):
        catalog.create_matter("Beta Case", db_path=self.db)
        ms = catalog.list_matters(db_path=self.db)
        self.assertTrue(any(m["slug"] == "beta-case" and m["doc_count"] == 0 for m in ms))

    def test_pending_count_zero_when_no_documents(self):
        catalog.create_matter("Delta Case", db_path=self.db)
        ms = catalog.list_matters(db_path=self.db)
        self.assertEqual(next(m for m in ms if m["slug"] == "delta-case")["pending_count"], 0)

    def test_pending_count_tracks_queued_and_parsing_docs_only(self):
        # Trust fix (gaps-audit first-run race): pending_count is the UI's signal that
        # a matter's suggested questions can't be trusted yet — it must count only
        # docs still short of a terminal ingest status (queued/parsing), never
        # ready/needs_review/failed docs, which are done trying either way.
        catalog.create_matter("Epsilon Case", db_path=self.db)
        pdf = Path(tempfile.mkdtemp()) / "a.pdf"
        pdf.write_text("x")
        catalog.add_document("epsilon-case", pdf, db_path=self.db, status="queued")
        d2 = catalog.add_document("epsilon-case", pdf, db_path=self.db, status="parsing")
        catalog.add_document("epsilon-case", pdf, db_path=self.db, status="ready")
        catalog.add_document("epsilon-case", pdf, db_path=self.db, status="failed")
        ms = catalog.list_matters(db_path=self.db)
        self.assertEqual(next(m for m in ms if m["slug"] == "epsilon-case")["pending_count"], 2)
        catalog.update_document(d2["id"], "ready", db_path=self.db)
        ms = catalog.list_matters(db_path=self.db)
        self.assertEqual(next(m for m in ms if m["slug"] == "epsilon-case")["pending_count"], 1)

    def test_get_matter_by_slug(self):
        catalog.create_matter("Gamma Holdings", db_path=self.db)
        self.assertIsNotNone(catalog.get_matter("gamma-holdings", db_path=self.db))
        self.assertIsNone(catalog.get_matter("no-such-matter", db_path=self.db))


class TestMattersRoutes(unittest.TestCase):
    def setUp(self):
        self._saved = catalog.DEFAULT_DB
        catalog.DEFAULT_DB = Path(tempfile.mkdtemp()) / "routes_cat.db"

    def tearDown(self):
        catalog.DEFAULT_DB = self._saved

    def test_post_then_get_reflects_matter(self):
        r = client.post("/matters", json={"display_name": "Route Test Matter"})
        self.assertEqual(r.status_code, 200, r.text)
        slug = r.json()["slug"]
        g = client.get("/matters")
        self.assertEqual(g.status_code, 200)
        self.assertTrue(any(m["slug"] == slug for m in g.json()["matters"]))

    def test_empty_name_returns_400(self):
        self.assertEqual(client.post("/matters", json={"display_name": ""}).status_code, 400)

    def test_duplicate_returns_400(self):
        client.post("/matters", json={"display_name": "Dup Matter"})
        self.assertEqual(client.post("/matters", json={"display_name": "Dup Matter"}).status_code, 400)

    def test_matters_route_carries_pending_count(self):
        r = client.post("/matters", json={"display_name": "Pending Route Matter"})
        slug = r.json()["slug"]
        pdf = Path(tempfile.mkdtemp()) / "a.pdf"
        pdf.write_text("x")
        catalog.add_document(slug, pdf, status="queued")
        m = next(m for m in client.get("/matters").json()["matters"] if m["slug"] == slug)
        self.assertEqual(m["pending_count"], 1)


APP_JS = (PIPELINE_DIR / "static" / "app.js").read_text()


class TestChatGuideFirstRunRace(unittest.TestCase):
    """Trust fix (gaps-audit first-run race): the seeded sample matter's suggested
    question buttons must not be clickable while its documents are still
    queued/parsing (they'd 400/refuse — the KB chunks table isn't ready yet).
    Manual typing must stay unaffected. Static assertions only; behavior is
    smoke-tested in the app."""

    def test_guide_q_disabled_while_pending(self):
        guide = APP_JS[APP_JS.index("function renderChatGuide"):
                       APP_JS.index("function sendChat")]
        self.assertIn("pending_count", guide)
        self.assertIn("disabled", guide)
        self.assertIn("Preparing your sample matter", guide)

    def test_polling_reuses_fillMatterPickers(self):
        guide = APP_JS[APP_JS.index("function renderChatGuide"):
                       APP_JS.index("function sendChat")]
        self.assertIn("fillMatterPickers", guide)
        self.assertIn("setTimeout", guide)

    def test_manual_typing_path_untouched(self):
        # sendChat() has no pending_count/disabled gate of its own — only the
        # canned suggestion buttons are ever disabled.
        send_chat = APP_JS[APP_JS.index("async function sendChat"):
                           APP_JS.index("async function sendChat") + 400]
        self.assertNotIn("pending_count", send_chat)


class TestChatGuidePollGuards(unittest.TestCase):
    """Important fix: the 2s suggestion poll must not keep fetching /matters while
    the chat pane isn't the active view, and must not run forever if a doc wedges in
    queued/parsing. Static assertions only; behavior is smoke-tested in the app."""

    def test_poll_callback_skips_fetch_when_chat_pane_hidden(self):
        guide = APP_JS[APP_JS.index("function chatGuideVisible"):
                       APP_JS.index("function sendChat")]
        self.assertIn("chatGuideVisible", guide)
        self.assertIn("view-chat", guide)
        self.assertIn("classList.contains(\"active\")", guide)
        # the visibility check must guard the fetch, not just exist somewhere nearby
        poll_cb = guide[guide.index("chatGuidePoll = setTimeout"):]
        self.assertLess(poll_cb.index("chatGuideVisible"), poll_cb.index("fillMatterPickers"))

    def test_poll_has_a_max_age_stop(self):
        guide = APP_JS[APP_JS.index("function renderChatGuide"):
                       APP_JS.index("function sendChat")]
        self.assertIn("30 * 60 * 1000", guide)
        self.assertIn("Date.now()", guide)


if __name__ == "__main__":
    unittest.main(verbosity=2)
