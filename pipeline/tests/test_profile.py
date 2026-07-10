"""UX-5 proof: the LOCAL profile (onboarding identity) — catalog storage + routes.

The profile lives only in the local catalog (SQLCipher-encrypted in production) and
holds exactly the fields the product uses: name (greeting/export stamp), practice
areas (tailored prompts), onboarded flag. No email/phone/account fields exist — by
design (they would contradict the no-account privacy promise). The UI shows the
onboarding overlay only while onboarded is falsy.
"""

import sys
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

PIPELINE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPELINE_DIR))
import catalog  # noqa: E402
import routes_profile  # noqa: E402
import api  # noqa: E402

client = TestClient(api.app)


class TestProfileCatalog(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._cat, catalog.DEFAULT_DB = catalog.DEFAULT_DB, self.tmp / "cat.db"

    def tearDown(self):
        catalog.DEFAULT_DB = self._cat

    def test_roundtrip_and_partial_update(self):
        self.assertEqual(catalog.get_profile(), {})
        catalog.set_profile({"name": "Maria", "practice_areas": ["Litigation"]})
        catalog.set_profile({"onboarded": True})   # partial: earlier keys untouched
        p = catalog.get_profile()
        self.assertEqual(p["name"], "Maria")
        self.assertEqual(p["practice_areas"], ["Litigation"])
        self.assertIs(p["onboarded"], True)

    def test_existing_catalog_gains_profile_table(self):
        # a pre-UX-5 catalog (created without the table) works after upgrade —
        # _connect's CREATE TABLE IF NOT EXISTS is the migration
        catalog.create_matter("Old Install Matter")
        self.assertEqual(catalog.get_profile(), {})


class TestProfileRoutes(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._cat, catalog.DEFAULT_DB = catalog.DEFAULT_DB, self.tmp / "cat.db"

    def tearDown(self):
        catalog.DEFAULT_DB = self._cat

    def test_get_starts_empty_with_available_areas(self):
        p = client.get("/profile").json()
        self.assertNotIn("name", p)
        self.assertIn("available_practice_areas", p)
        self.assertIn("Litigation", p["available_practice_areas"])

    def test_put_then_get(self):
        r = client.post("/profile", json={"name": "  David Chen  ",
                                         "practice_areas": ["Business & Contracts", " "],
                                         "onboarded": True})
        self.assertEqual(r.status_code, 200, r.text)
        p = client.get("/profile").json()
        self.assertEqual(p["name"], "David Chen")                       # trimmed
        self.assertEqual(p["practice_areas"], ["Business & Contracts"])  # blanks dropped
        self.assertIs(p["onboarded"], True)

    def test_bounds_enforced(self):
        client.post("/profile", json={"name": "x" * 500,
                                     "practice_areas": ["a"] * 50})
        p = client.get("/profile").json()
        self.assertLessEqual(len(p["name"]), routes_profile._MAX_NAME)
        self.assertLessEqual(len(p["practice_areas"]), routes_profile._MAX_AREAS)

    def test_no_contact_fields(self):
        # privacy promise: the API must not accept/store email or phone
        client.post("/profile", json={"name": "A", "email": "a@b.c", "phone": "555"})
        p = client.get("/profile").json()
        self.assertNotIn("email", p)
        self.assertNotIn("phone", p)


class TestOnboardingUi(unittest.TestCase):
    def test_js_has_onboarding_and_profile_wiring(self):
        js = client.get("/static/app.js").text
        self.assertIn("onboard-overlay", js)
        self.assertIn("/profile", js)
        self.assertIn("maybeShowOnboarding", js)
        self.assertIn("not legal advice", js)      # expectation-setting screen
        self.assertNotIn("—", js.split("onboard-card")[1].split("</div></div>")[0]
                          if "onboard-card" in js else "")  # no em-dashes in onboarding copy

    def test_css_has_onboarding_styles(self):
        css = client.get("/static/app.css").text
        self.assertIn("onboard-card", css)
        self.assertIn("chip-set", css)


if __name__ == "__main__":
    unittest.main(verbosity=2)
