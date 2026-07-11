"""M-2 matter digest — catalog layer: span-pointered fact rows (pure machine output,
rebuildable), attorney review state that survives re-extraction, hard deletion
cascades (doc delete -> facts die; matter delete -> facts + reviews die)."""

import sys
import tempfile
import unittest
from pathlib import Path

PIPELINE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPELINE_DIR))
import catalog  # noqa: E402


def _fact(key="k1", ftype="date_event", page=1):
    return {"fact_type": ftype, "value": {"kind": "deadline", "label": "Answer due",
            "date_text": "within 30 days", "date_iso": None,
            "date_kind": "relative", "anchor": "service"},
            "page": page, "char_start": 10, "char_end": 25,
            "span": "within 30 days", "fact_key": key}


class TestDigestCatalog(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._cat, catalog.DEFAULT_DB = catalog.DEFAULT_DB, self.tmp / "cat.db"
        catalog.create_matter("Nimbus Dispute")
        # Create a temporary file for the test
        self.pdf_path = self.tmp / "msa.pdf"
        self.pdf_path.write_text("dummy content")
        self.doc = catalog.add_document("nimbus-dispute", self.pdf_path,
                                        status="ready")

    def tearDown(self):
        catalog.DEFAULT_DB = self._cat

    def test_replace_facts_is_idempotent_and_stamps_version(self):
        catalog.replace_facts(self.doc["id"], "nimbus-dispute", [_fact("a"), _fact("b")], "v1")
        catalog.replace_facts(self.doc["id"], "nimbus-dispute", [_fact("a")], "v2")
        rows = catalog.facts_for_matter("nimbus-dispute")
        self.assertEqual([r["fact_key"] for r in rows], ["a"])          # replaced, not appended
        self.assertEqual(rows[0]["extractor_version"], "v2")
        self.assertEqual(rows[0]["filename"], "msa.pdf")                # join works
        d = catalog.get_document(self.doc["id"])
        self.assertEqual(d["digest_version"], "v2")

    def test_facts_require_matter_slug(self):
        with self.assertRaises(ValueError):
            catalog.facts_for_matter("")

    def test_review_upsert_survives_reextraction_and_prunes_orphans(self):
        catalog.replace_facts(self.doc["id"], "nimbus-dispute", [_fact("a"), _fact("gone")], "v1")
        catalog.set_fact_review("nimbus-dispute", "a", "confirmed", "2026-07-24")
        catalog.set_fact_review("nimbus-dispute", "gone", "dismissed")
        # re-extraction: fact "gone" no longer produced
        catalog.replace_facts(self.doc["id"], "nimbus-dispute", [_fact("a")], "v1")
        pruned = catalog.prune_orphan_reviews("nimbus-dispute")
        self.assertEqual(pruned, 1)
        reviews = catalog.reviews_for_matter("nimbus-dispute")
        self.assertEqual(reviews["a"], {"status": "confirmed", "confirmed_date": "2026-07-24"})
        self.assertNotIn("gone", reviews)

    def test_review_status_validated_and_none_reverts(self):
        catalog.replace_facts(self.doc["id"], "nimbus-dispute", [_fact("a")], "v1")
        with self.assertRaises(ValueError):
            catalog.set_fact_review("nimbus-dispute", "a", "approved")
        catalog.set_fact_review("nimbus-dispute", "a", "dismissed")
        catalog.set_fact_review("nimbus-dispute", "a", None)   # undo -> proposed
        self.assertEqual(catalog.reviews_for_matter("nimbus-dispute"), {})

    def test_delete_document_cascades_facts(self):
        catalog.replace_facts(self.doc["id"], "nimbus-dispute", [_fact("a")], "v1")
        catalog.delete_document(self.doc["id"])
        self.assertEqual(catalog.facts_for_matter("nimbus-dispute"), [])

    def test_replace_facts_noop_after_doc_deleted(self):
        # A digest in flight can finish after the doc (or matter, via disposition) was
        # deleted; replace_facts must not resurrect facts for a doc that no longer exists.
        catalog.delete_document(self.doc["id"])
        catalog.replace_facts(self.doc["id"], "nimbus-dispute", [_fact("a")], "v1")
        self.assertEqual(catalog.facts_for_matter("nimbus-dispute"), [])

    def test_delete_matter_cascades_facts_and_reviews(self):
        catalog.replace_facts(self.doc["id"], "nimbus-dispute", [_fact("a")], "v1")
        catalog.set_fact_review("nimbus-dispute", "a", "confirmed", "2026-07-24")
        catalog.delete_matter("nimbus-dispute")
        conn = catalog._connect()
        try:
            for table in ("matter_facts", "fact_review"):
                n = conn.execute(f"SELECT COUNT(*) c FROM {table} WHERE matter_slug = ?",
                                 ("nimbus-dispute",)).fetchone()["c"]
                self.assertEqual(n, 0, table)
        finally:
            conn.close()

    def test_digest_progress(self):
        p = catalog.digest_progress("nimbus-dispute", "v1")
        self.assertEqual(p, {"done": 0, "total": 1})
        catalog.replace_facts(self.doc["id"], "nimbus-dispute", [], "v1")  # zero facts still counts done
        p = catalog.digest_progress("nimbus-dispute", "v1")
        self.assertEqual(p, {"done": 1, "total": 1})

    def test_replace_facts_requires_matter_slug(self):
        with self.assertRaises(ValueError):
            catalog.replace_facts(self.doc["id"], "", [_fact("a")], "v1")

    def test_connect_sets_busy_timeout(self):
        # Sprint 4-8: background ingest/digest workers write this catalog concurrently
        # with request handlers; without a busy timeout a momentary writer lock raises
        # immediately instead of waiting, which has aborted user-facing streams.
        conn = catalog._connect()
        try:
            self.assertEqual(conn.execute("PRAGMA busy_timeout").fetchone()[0], 5000)
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
