"""T-CLAUSE core proof: the clause-extraction checklist over answer() + the span verifier.

Three layers of proof:

1. Taxonomy (data) — `clause_taxonomy.json` is well-formed, ids are unique, every entry
   carries our required fields, CUAD provenance is attributed (CC BY) and the questions
   are OUR phrasing (not CUAD's "Highlight the parts ..." text).

2. Classification (mocked answer, fast + deterministic) — the never-false-accept
   invariant: a clause is "found" ONLY when answer() returned >=1 span-verified,
   chunk-derived citation; the exact D-30 refusal -> "potentially_missing" with ZERO
   citations (never a fabricated citation for an absence); confident prose whose spans
   the verifier REJECTED -> "not_confirmed", never "found", zero citations surfaced.

3. Integration (real loopback Ollama, read-only against the eval .lancedb) — a
   known-present clause (Pemberton MSA indemnification, golden F-009) returns "found"
   with a span-verified citation on the correct file (nimbus_pemberton_msa.pdf) + page
   (3); a known-absent clause (arbitration, golden NF-001) returns "potentially_missing"
   with zero citations. Baseline store is only READ — never re-embedded (D-31).
"""

import json
import sys
import unittest
from pathlib import Path

PIPELINE_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = PIPELINE_DIR.parent
sys.path.insert(0, str(PIPELINE_DIR))

import clauses  # noqa: E402  (module under test)
from answering import REFUSAL  # noqa: E402

TAXONOMY = PIPELINE_DIR / "data" / "clause_taxonomy.json"
EVAL_DB = PIPELINE_DIR / ".lancedb"
PEMBERTON = "Pemberton Logistics (Nimbus MSA)"


# --- 1. Taxonomy data -------------------------------------------------------------

class TestTaxonomyData(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = json.loads(TAXONOMY.read_text(encoding="utf-8"))
        cls.entries = cls.doc["clauses"]

    def test_every_entry_has_required_fields(self):
        for c in self.entries:
            for k in ("id", "name", "category", "question", "doc_types"):
                self.assertIn(k, c, f"{c.get('id')!r} missing {k}")
            self.assertTrue(c["id"] and c["question"].strip())
            self.assertIsInstance(c["doc_types"], list)
            self.assertTrue(c["doc_types"])

    def test_ids_are_unique(self):
        ids = [c["id"] for c in self.entries]
        self.assertEqual(len(ids), len(set(ids)), "duplicate clause id")

    def test_covers_core_attorney_clauses(self):
        ids = {c["id"] for c in self.entries}
        for needed in ("governing_law", "indemnification", "limitation_of_liability",
                       "termination", "confidentiality", "assignment", "non_compete",
                       "ip_ownership", "payment_terms", "warranties", "dispute_resolution"):
            self.assertIn(needed, ids, f"checklist missing the {needed} clause")

    def test_provenance_attributes_cuad_cc_by(self):
        prov = json.dumps(self.doc["_provenance"]).lower()
        self.assertIn("cuad", prov)
        self.assertIn("cc by", prov)

    def test_questions_are_not_cuad_verbatim(self):
        # CUAD phrases every item "Highlight the parts (if any) of this contract ...".
        # Our questions must be original phrasing, not that template.
        for c in self.entries:
            self.assertNotIn("highlight the parts", c["question"].lower(),
                             f"{c['id']} copies CUAD question text")

    def test_loader_returns_entries(self):
        loaded = clauses.load_taxonomy(TAXONOMY)
        self.assertEqual([c["id"] for c in loaded], [c["id"] for c in self.entries])


# --- 2. Classification (mocked answer) --------------------------------------------

class _FakeAnswer:
    """A monkeypatch for clauses.answer keyed by a substring of the question."""

    def __init__(self, mapping):
        self.mapping = mapping
        self.calls = []
        self.scopes = []

    def __call__(self, question, matter=None, top_k=5, db_path=None,
                 source_filename=None):
        self.calls.append((question, matter, db_path))
        self.scopes.append(source_filename)
        for needle, result in self.mapping.items():
            if needle.lower() in question.lower():
                return result
        # default: a clean D-30 refusal
        return {"answer_text": REFUSAL, "citations": [], "rejected_claims": [],
                "grounding_chunks": []}


def _verified_citation(filename="nimbus_pemberton_msa.pdf", page=3):
    return {"filename": filename, "page": page, "chunk_id": "C1",
            "span": "shall indemnify, defend, and hold harmless",
            "char_start": 100, "char_end": 145}


class TestClassification(unittest.TestCase):
    def setUp(self):
        # a 3-clause synthetic taxonomy exercising all three statuses
        self.tax = [
            {"id": "indemnification", "name": "Indemnification", "category": "Risk Allocation",
             "question": "What are the indemnification obligations?", "doc_types": ["contract"]},
            {"id": "arbitration", "name": "Arbitration", "category": "Dispute Resolution",
             "question": "What are the mandatory arbitration provisions?", "doc_types": ["contract"]},
            {"id": "governing_law", "name": "Governing Law", "category": "Boilerplate",
             "question": "Which law governs this agreement?", "doc_types": ["contract"]},
        ]
        self._orig = clauses.answer

    def tearDown(self):
        clauses.answer = self._orig

    def _run(self, mapping):
        fake = _FakeAnswer(mapping)
        clauses.answer = fake
        out = clauses.extract_clauses("any-matter", taxonomy=self.tax, db_path="/tmp/x")
        return out, fake

    def test_found_requires_a_verified_citation(self):
        out, _ = self._run({
            "indemnification": {
                "answer_text": "Each party shall indemnify the other "
                               "[document: nimbus_pemberton_msa.pdf, page: 3, chunk: C1, "
                               "span: \"shall indemnify, defend, and hold harmless\"].",
                "citations": [_verified_citation()], "rejected_claims": [],
                "grounding_chunks": [],
            },
        })
        by_id = {r["id"]: r for r in out["results"]}
        self.assertEqual(by_id["indemnification"]["status"], "found")
        self.assertEqual(len(by_id["indemnification"]["citations"]), 1)
        self.assertEqual(by_id["indemnification"]["citations"][0]["page"], 3)

    def test_refusal_is_potentially_missing_with_zero_citations(self):
        out, _ = self._run({})  # everything refuses
        for r in out["results"]:
            self.assertEqual(r["status"], "potentially_missing")
            self.assertEqual(r["citations"], [], "fabricated a citation for an absence")

    def test_prose_with_rejected_spans_is_not_confirmed_never_found(self):
        # The model asserted a confident answer WITH a citation tag, but the verifier
        # rejected every span (citations empty, rejected_claims populated). This must
        # NEVER be reported found and must surface ZERO citations.
        out, _ = self._run({
            "arbitration": {
                "answer_text": "Arbitration is required in Delaware "
                               "[document: nimbus_pemberton_msa.pdf, page: 9, chunk: C1, "
                               "span: \"all disputes shall be arbitrated\"].",
                "citations": [],
                "rejected_claims": [{"span": "all disputes shall be arbitrated",
                                     "asserted_chunk": "C1", "reason": "no overlap"}],
                "grounding_chunks": [],
            },
        })
        r = {x["id"]: x for x in out["results"]}["arbitration"]
        self.assertEqual(r["status"], "not_confirmed")
        self.assertNotEqual(r["status"], "found")
        self.assertEqual(r["citations"], [])
        self.assertTrue(r["rejected_claims"])

    def test_summary_counts_and_full_coverage(self):
        out, fake = self._run({
            "indemnification": {"answer_text": "x", "citations": [_verified_citation()],
                                "rejected_claims": [], "grounding_chunks": []},
            "governs": {"answer_text": "Delaware law governs.",
                        "citations": [_verified_citation(page=4)],
                        "rejected_claims": [], "grounding_chunks": []},
        })
        # arbitration falls through to the default refusal
        self.assertEqual(out["summary"]["found"], 2)
        self.assertEqual(out["summary"]["potentially_missing"], 1)
        self.assertEqual(out["summary"]["total"], 3)
        self.assertEqual(len(fake.calls), 3)  # every clause was actually run

    def test_matter_and_db_path_are_passed_through(self):
        _, fake = self._run({})
        for (_q, matter, db_path) in fake.calls:
            self.assertEqual(matter, "any-matter")
            self.assertEqual(db_path, "/tmp/x")

    def test_doc_id_postfilter_drops_other_document_citation_no_leak(self):
        # Regression (D-52): a clause is span-verified on file A, but the review is
        # scoped to doc_id -> file B. The doc_id post-filter must drop the file-A
        # citation, so this document reads NOT_CONFIRMED with ZERO citations — a
        # clause present elsewhere in the matter never leaks onto the wrong document.
        import catalog
        orig_get = catalog.get_document
        catalog.get_document = lambda doc_id, db_path=None: {
            "id": doc_id, "filename": "file_b.pdf", "matter_slug": "any-matter"}
        try:
            fake = _FakeAnswer({"indemnification": {
                "answer_text": "Each party shall indemnify the other "
                               "[document: file_a.pdf, page: 3, chunk: C1, "
                               "span: \"shall indemnify\"].",
                # the verifier returned a REAL, span-verified citation — on file A
                "citations": [_verified_citation(filename="file_a.pdf", page=3)],
                "rejected_claims": [], "grounding_chunks": []}})
            clauses.answer = fake
            out = clauses.extract_clauses("any-matter", doc_id=42,
                                          taxonomy=[self.tax[0]], db_path="/tmp/x")
        finally:
            catalog.get_document = orig_get
        r = out["results"][0]
        self.assertEqual(r["status"], "not_confirmed",
                         "file-A citation leaked onto file-B-scoped review")
        self.assertEqual(r["citations"], [], "cross-document citation leak")

    def test_doc_id_scopes_retrieval_not_just_the_postfilter(self):
        # D3 (G-SCOPE): a single-document review must pass the resolved filename
        # into answer() as source_filename, so RETRIEVAL is scoped (the D-52
        # post-filter stays as belt-and-braces, but the top-5 must come from
        # this document, not the whole matter).
        import catalog
        orig_get = catalog.get_document
        catalog.get_document = lambda doc_id, db_path=None: {
            "id": doc_id, "filename": "file_b.pdf", "matter_slug": "any-matter"}
        try:
            fake = _FakeAnswer({})
            clauses.answer = fake
            clauses.extract_clauses("any-matter", doc_id=42,
                                    taxonomy=self.tax, db_path="/tmp/x")
        finally:
            catalog.get_document = orig_get
        self.assertEqual(len(fake.scopes), 3)
        self.assertTrue(all(s == "file_b.pdf" for s in fake.scopes),
                        f"answer() not retrieval-scoped: {fake.scopes}")

    def test_matter_wide_review_passes_no_scope(self):
        _, fake = self._run({})
        self.assertEqual(len(fake.scopes), 3)
        self.assertTrue(all(s is None for s in fake.scopes))

    def test_scoped_review_fails_loud_when_doc_not_in_index(self):
        # D3 rider: "document not in the index" (still processing / OCR-failed)
        # must PROPAGATE on a scoped review — swallowing it would persist a
        # complete all-"Not located" review of unchecked passages. A matter-wide
        # ValueError still degrades to clean refusals.
        import catalog
        orig_get = catalog.get_document
        catalog.get_document = lambda doc_id, db_path=None: {
            "id": doc_id, "filename": "file_b.pdf", "matter_slug": "any-matter"}

        def raising_answer(q, matter=None, top_k=5, db_path=None,
                           source_filename=None):
            raise ValueError("document not found in the index for this matter")
        try:
            clauses.answer = raising_answer
            with self.assertRaises(ValueError):
                clauses.extract_clauses("any-matter", doc_id=42,
                                        taxonomy=self.tax, db_path="/tmp/x")
            # matter-wide: same error degrades to refusals, never raises
            out = clauses.extract_clauses("any-matter", taxonomy=self.tax,
                                          db_path="/tmp/x")
            self.assertEqual(out["summary"]["potentially_missing"], 3)
        finally:
            catalog.get_document = orig_get


# --- 3. Integration (real loopback Ollama, read-only eval store) -------------------

@unittest.skipUnless(EVAL_DB.exists(), "eval .lancedb baseline not present")
class TestIntegrationAgainstBaseline(unittest.TestCase):
    """Read-only against the eval baseline (D-31): never re-embeds, only queries."""

    def test_known_present_and_absent_clauses(self):
        tax = [
            {"id": "indemnification", "name": "Indemnification", "category": "Risk Allocation",
             "question": "What are each party's indemnification obligations under this "
                         "agreement: who must defend, indemnify, or hold harmless whom?",
             "doc_types": ["contract"]},
            {"id": "arbitration", "name": "Arbitration", "category": "Dispute Resolution",
             "question": "What are the terms of the mandatory arbitration provision in "
                         "this agreement?", "doc_types": ["contract"]},
        ]
        out = clauses.extract_clauses(PEMBERTON, taxonomy=tax, db_path=str(EVAL_DB))
        by_id = {r["id"]: r for r in out["results"]}

        # known-present: indemnification (golden F-009, page 3)
        ind = by_id["indemnification"]
        self.assertEqual(ind["status"], "found",
                         f"indemnification not found: {ind['value']!r}")
        self.assertTrue(ind["citations"], "found clause has no citation")
        c = ind["citations"][0]
        self.assertEqual(c["filename"], "nimbus_pemberton_msa.pdf")
        self.assertEqual(c["page"], 3)
        # span-verified -> carries page offsets from the verifier
        self.assertIn("char_start", c)
        self.assertLess(c["char_start"], c["char_end"])

        # known-absent: arbitration (golden NF-001) -> advisory, zero citations
        arb = by_id["arbitration"]
        self.assertEqual(arb["status"], "potentially_missing",
                         f"arbitration mis-classified: {arb!r}")
        self.assertEqual(arb["citations"], [], "fabricated a citation for an absent clause")


if __name__ == "__main__":
    unittest.main(verbosity=2)
