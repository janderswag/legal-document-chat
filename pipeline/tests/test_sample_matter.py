"""P1.3 — first-run sample matter: a fresh install seeds a synthetic demo matter and a
brand-new user reaches a span-verified cited answer with zero setup. Writes ONLY to temp
stores here — never the real catalog/KB. The end-to-end case uses the live loopback
Ollama, like the other ingest tests."""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import fitz

PIPELINE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPELINE_DIR))
import catalog  # noqa: E402
import sample_matter  # noqa: E402
from answering import answer  # noqa: E402


class TestSampleDocs(unittest.TestCase):
    def test_generated_pdfs_are_readable_and_banner_labelled(self):
        tmp = Path(tempfile.mkdtemp())
        for filename, body in sample_matter._DOCS.items():
            dest = tmp / filename
            sample_matter._write_pdf(dest, body)
            with fitz.open(dest) as doc:
                text = "".join(p.get_text() for p in doc)
            self.assertIn("SYNTHETIC SAMPLE", text, filename)  # hard rule #1
            # every paragraph survived pagination
            for para in body.split("\n\n"):
                probe = para.splitlines()[0][:40].strip()
                self.assertIn(probe, text.replace("\n", " ").replace("  ", " "),
                              f"{filename}: lost {probe!r}")

    def test_key_facts_present_for_suggested_questions(self):
        joined = " ".join(sample_matter._DOCS.values())
        for fact in ("$12,500", "sixty (60) days", "$7,500"):
            self.assertIn(fact, joined)


class TestSeedGuards(unittest.TestCase):
    def test_seed_noops_when_any_matter_exists(self):
        tmp = Path(tempfile.mkdtemp())
        cat = tmp / "cat.db"
        catalog.create_matter("Existing Matter", db_path=cat)
        out = sample_matter.seed_sample_matter(db_path=cat, kb_db=tmp / "kb",
                                               kb_docs=tmp / "docs")
        self.assertIsNone(out)
        self.assertEqual(len(catalog.list_matters(db_path=cat)), 1)  # untouched
        self.assertFalse((tmp / "docs").exists())


class TestDemoLabelMigration(unittest.TestCase):
    """UX-2: the sample matter is 'Sample Matter' — no '(Demo)' in a shipped app.
    Pre-rename installs get their label migrated; user matters are never touched."""

    def test_new_name_has_no_demo(self):
        self.assertEqual(sample_matter.SAMPLE_MATTER_NAME, "Sample Matter")
        self.assertNotIn("demo", sample_matter.SAMPLE_MATTER_NAME.lower())

    def test_legacy_label_migrates_once_and_only_the_sample(self):
        tmp = Path(tempfile.mkdtemp())
        cat = tmp / "cat.db"
        # simulate a pre-rename install: legacy slug + old label, plus a user matter
        # whose name legitimately contains "(Demo)" and must survive untouched
        catalog.create_matter("Sample Matter (Demo)", db_path=cat)   # -> legacy slug
        catalog.create_matter("Acme (Demo) Litigation", db_path=cat)
        self.assertTrue(sample_matter.migrate_demo_label(db_path=cat))
        names = {m["slug"]: m["display_name"] for m in catalog.list_matters(db_path=cat)}
        self.assertEqual(names[sample_matter.LEGACY_SAMPLE_SLUG], "Sample Matter")
        self.assertEqual(names["acme-demo-litigation"], "Acme (Demo) Litigation")
        # idempotent: second run is a no-op
        self.assertFalse(sample_matter.migrate_demo_label(db_path=cat))

    def test_both_slugs_flagged_sample(self):
        self.assertIn(sample_matter.SAMPLE_MATTER_SLUG, sample_matter.SAMPLE_SLUGS)
        self.assertIn(sample_matter.LEGACY_SAMPLE_SLUG, sample_matter.SAMPLE_SLUGS)


class TestSeedDigestEnqueue(unittest.TestCase):
    """Critical fix: seeding calls kb_ingest.ingest_document() directly, bypassing
    ingest_worker._run's digest.enqueue hook — without one here, seeded docs never
    get a digest_version stamp and routes_digest's idle-proxy "stuck" heuristic
    falsely reports them as unprocessable on the very first screen."""

    def test_each_ingested_doc_is_digest_enqueued(self):
        tmp = Path(tempfile.mkdtemp())
        cat, kb, docs = tmp / "cat.db", tmp / "kb", tmp / "kb_docs"
        seen = []
        with mock.patch.object(sample_matter.kb_ingest, "ingest_document",
                               return_value="ready"), \
             mock.patch.object(sample_matter.digest, "enqueue",
                               side_effect=lambda doc_id, *a, **k: seen.append(doc_id)):
            slug = sample_matter.seed_sample_matter(db_path=cat, kb_db=kb, kb_docs=docs)
        rows = catalog.list_documents(slug, db_path=cat)
        self.assertEqual(len(rows), len(sample_matter._DOCS))
        self.assertEqual(sorted(seen), sorted(r["id"] for r in rows))

    def test_needs_review_is_also_digest_enqueued(self):
        tmp = Path(tempfile.mkdtemp())
        cat, kb, docs = tmp / "cat.db", tmp / "kb", tmp / "kb_docs"
        with mock.patch.object(sample_matter.kb_ingest, "ingest_document",
                               return_value="needs_review"), \
             mock.patch.object(sample_matter.digest, "enqueue") as enq:
            sample_matter.seed_sample_matter(db_path=cat, kb_db=kb, kb_docs=docs)
        self.assertEqual(enq.call_count, len(sample_matter._DOCS))

    def test_failed_ingest_does_not_enqueue_digest(self):
        tmp = Path(tempfile.mkdtemp())
        cat, kb, docs = tmp / "cat.db", tmp / "kb", tmp / "kb_docs"
        with mock.patch.object(sample_matter.kb_ingest, "ingest_document",
                               return_value="failed"), \
             mock.patch.object(sample_matter.digest, "enqueue") as enq:
            sample_matter.seed_sample_matter(db_path=cat, kb_db=kb, kb_docs=docs)
        enq.assert_not_called()

    def test_digest_enqueue_failure_never_fails_seeding(self):
        tmp = Path(tempfile.mkdtemp())
        cat, kb, docs = tmp / "cat.db", tmp / "kb", tmp / "kb_docs"
        with mock.patch.object(sample_matter.kb_ingest, "ingest_document",
                               return_value="ready"), \
             mock.patch.object(sample_matter.digest, "enqueue",
                               side_effect=RuntimeError("boom")):
            slug = sample_matter.seed_sample_matter(db_path=cat, kb_db=kb, kb_docs=docs)
        self.assertEqual(slug, sample_matter.SAMPLE_MATTER_SLUG)   # seeding still succeeded
        rows = catalog.list_documents(slug, db_path=cat)
        self.assertEqual(len(rows), len(sample_matter._DOCS))


class TestSeedEndToEnd(unittest.TestCase):
    def test_fresh_seed_answers_a_suggested_question_with_citation(self):
        tmp = Path(tempfile.mkdtemp())
        cat, kb, docs = tmp / "cat.db", tmp / ".lancedb_kb", tmp / "kb_docs"
        slug = sample_matter.seed_sample_matter(db_path=cat, kb_db=kb, kb_docs=docs)
        self.assertEqual(slug, sample_matter.SAMPLE_MATTER_SLUG)

        rows = catalog.list_documents(slug, db_path=cat)
        self.assertEqual(len(rows), len(sample_matter._DOCS))
        for r in rows:
            self.assertEqual(r["status"], "ready", r["filename"])

        # ACCEPTANCE (P1.3): a suggested question gets a span-verified cited answer.
        res = answer(sample_matter.SUGGESTED_QUESTIONS[0], matter=slug, db_path=str(kb))
        self.assertTrue(res["citations"],
                        f"no citation; answer={res['answer_text']!r}")
        self.assertIn("12,500", res["answer_text"])
        self.assertEqual(res["citations"][0]["filename"], "sample-services-agreement.pdf")


if __name__ == "__main__":
    unittest.main(verbosity=2)
