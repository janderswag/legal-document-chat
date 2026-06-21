"""A1/A2/A4 — tabular-review grid backend.

The grid evaluates a (document x question) matrix by reusing the EXISTING
retrieve+answer+verify path and the T-CLAUSE cell classifier — never a forked verifier.
Proven here: every cell is produced; never-false-accept per cell (found requires a
span-verified citation; refusal -> potentially_missing; prose-with-rejected-span ->
not_confirmed; all with zero fabricated citations); the doc_id post-filter blocks a
cross-document citation leak; concurrency is bounded (<= max_workers, never unbounded);
columns default to the clause taxonomy with a custom-question override.
"""

import sys
import threading
import time
import unittest
from pathlib import Path

PIPELINE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPELINE_DIR))
import grid  # noqa: E402  (module under test)
from answering import REFUSAL  # noqa: E402


def _cite(filename="a.pdf", page=1):
    return {"filename": filename, "page": page, "chunk_id": "C1", "span": "x",
            "char_start": 0, "char_end": 1}


class TestColumns(unittest.TestCase):
    def test_defaults_to_full_clause_taxonomy(self):
        cols = grid.resolve_columns()
        ids = {c["id"] for c in cols}
        self.assertIn("indemnification", ids)
        self.assertIn("governing_law", ids)

    def test_clause_ids_subset(self):
        cols = grid.resolve_columns(clause_ids=["governing_law", "indemnification"])
        self.assertEqual([c["id"] for c in cols], ["governing_law", "indemnification"])

    def test_custom_question_override(self):
        cols = grid.resolve_columns(questions=["What is the termination notice period?"])
        self.assertEqual(len(cols), 1)
        self.assertEqual(cols[0]["question"], "What is the termination notice period?")


class TestMatrix(unittest.TestCase):
    def setUp(self):
        self._orig = grid.answer
        self.docs = [{"doc_id": 1, "filename": "a.pdf"}, {"doc_id": 2, "filename": "b.pdf"}]
        self.cols = [{"id": "found_q", "name": "Found", "category": "X", "question": "found?"},
                     {"id": "miss_q", "name": "Miss", "category": "X", "question": "miss?"}]

    def tearDown(self):
        grid.answer = self._orig

    def _fake(self, mapping):
        def fake(question, matter=None, top_k=5, db_path=None):
            return mapping.get(question, {"answer_text": REFUSAL, "citations": [],
                                          "rejected_claims": [], "grounding_chunks": []})
        grid.answer = fake

    def test_full_matrix_every_cell_present(self):
        self._fake({})  # everything refuses
        cells = list(grid.run_grid("m", self.docs, self.cols, max_workers=2))
        self.assertEqual(len(cells), 4)  # 2 docs x 2 cols
        keys = {(c["doc_id"], c["column_id"]) for c in cells}
        self.assertEqual(keys, {(1, "found_q"), (1, "miss_q"), (2, "found_q"), (2, "miss_q")})

    def test_found_requires_verified_citation(self):
        self._fake({"found?": {"answer_text": "yes", "citations": [_cite("a.pdf")],
                               "rejected_claims": [], "grounding_chunks": []}})
        cells = {(c["doc_id"], c["column_id"]): c
                 for c in grid.run_grid("m", self.docs, self.cols, max_workers=2)}
        a_found = cells[(1, "found_q")]
        self.assertEqual(a_found["status"], "found")
        self.assertEqual(a_found["citations"][0]["doc_id"], 1)  # enriched
        self.assertEqual(cells[(1, "miss_q")]["status"], "potentially_missing")
        self.assertEqual(cells[(1, "miss_q")]["citations"], [])

    def test_prose_with_rejected_span_is_not_confirmed(self):
        self._fake({"found?": {"answer_text": "yes [document: a.pdf, page: 9]",
                               "citations": [],
                               "rejected_claims": [{"span": "z", "reason": "no overlap"}],
                               "grounding_chunks": []}})
        cells = {(c["doc_id"], c["column_id"]): c
                 for c in grid.run_grid("m", self.docs, self.cols, max_workers=2)}
        self.assertEqual(cells[(1, "found_q")]["status"], "not_confirmed")
        self.assertEqual(cells[(1, "found_q")]["citations"], [])

    def test_doc_id_postfilter_blocks_cross_document_leak(self):
        # answer for doc a.pdf is verified on b.pdf -> must NOT leak onto a.pdf's cell
        self._fake({"found?": {"answer_text": "yes", "citations": [_cite("b.pdf")],
                               "rejected_claims": [], "grounding_chunks": []}})
        cells = {(c["doc_id"], c["column_id"]): c
                 for c in grid.run_grid("m", self.docs, self.cols, max_workers=2)}
        a_cell = cells[(1, "found_q")]
        self.assertEqual(a_cell["status"], "not_confirmed", "cross-doc citation leaked")
        self.assertEqual(a_cell["citations"], [])
        # the SAME verified citation IS valid for doc b.pdf's own cell
        self.assertEqual(cells[(2, "found_q")]["status"], "found")

    def test_concurrency_is_bounded(self):
        peak = {"n": 0, "cur": 0}
        lock = threading.Lock()

        def fake(question, matter=None, top_k=5, db_path=None):
            with lock:
                peak["cur"] += 1
                peak["n"] = max(peak["n"], peak["cur"])
            time.sleep(0.05)
            with lock:
                peak["cur"] -= 1
            return {"answer_text": REFUSAL, "citations": [], "rejected_claims": [],
                    "grounding_chunks": []}
        grid.answer = fake
        big_docs = [{"doc_id": i, "filename": f"{i}.pdf"} for i in range(6)]
        list(grid.run_grid("m", big_docs, self.cols, max_workers=2))
        self.assertLessEqual(peak["n"], 2, f"concurrency exceeded bound: {peak['n']}")
        self.assertGreater(peak["n"], 1, "did not actually run concurrently")

    def test_max_workers_is_clamped_never_unbounded(self):
        self.assertLessEqual(grid._clamp_workers(999), 4)
        self.assertGreaterEqual(grid._clamp_workers(0), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
