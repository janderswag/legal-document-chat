"""C1/C2 — unit tests for the experiment harnesses' pure ranking/measure helpers.

The full measurements run against the read-only baseline (Ollama + torch reranker) and are
recorded in docs/experiments/; here we only assert the pure helpers are correct, fast.
"""

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "experiments"))
import exp_c1_topk_rerank as c1  # noqa: E402
import exp_c2_sentence_window as c2  # noqa: E402


class TestRankOfCorrect(unittest.TestCase):
    def setUp(self):
        self.rows = [
            {"source_filename": "a.pdf", "page_number": 3, "text": "irrelevant page three"},
            {"source_filename": "a.pdf", "page_number": 1, "text": "Counsel: Sabrina Voss here"},
        ]

    def test_finds_correct_chunk_rank(self):
        self.assertEqual(c1.rank_of_correct(self.rows, "a.pdf", 1, "Sabrina Voss"), 2)

    def test_wrong_page_not_matched(self):
        self.assertIsNone(c1.rank_of_correct(self.rows, "a.pdf", 2, "Sabrina Voss"))

    def test_absent_needle_is_none(self):
        self.assertIsNone(c1.rank_of_correct(self.rows, "a.pdf", 1, "Nonexistent Name"))


class TestSentenceWindow(unittest.TestCase):
    def test_window_expands_around_match_without_crossing_chunk(self):
        text = "S0. S1. S2 has the FEE. S3. S4."
        win = c2.sentence_window(text, "FEE", radius=1)
        self.assertIn("FEE", win)
        self.assertIn("S1", win)   # neighbor before
        self.assertIn("S3", win)   # neighbor after
        self.assertNotIn("S0", win)  # outside the radius

    def test_no_match_returns_full_text(self):
        self.assertEqual(c2.sentence_window("a. b. c.", "zzz", radius=1), "a. b. c.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
