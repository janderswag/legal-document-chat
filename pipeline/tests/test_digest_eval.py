"""G-DIG scorer: recall per fact type against a hand-labeled inventory, matched
via the verifier's normalization; drop counts reported; exit code from targets."""

import sys
import unittest
from pathlib import Path

PIPELINE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPELINE_DIR))
import run_digest_eval  # noqa: E402


class TestScorer(unittest.TestCase):
    def test_recall_by_type(self):
        inventory = [
            {"doc": "a.pdf", "fact_type": "party", "span_contains": "pemberton logistics"},
            {"doc": "a.pdf", "fact_type": "party", "span_contains": "nimbus analytics"},
            {"doc": "a.pdf", "fact_type": "amount", "span_contains": "$28,000"},
        ]
        extracted = {("a.pdf", "party"): ["Pemberton Logistics Inc. (\"Client\")"],
                     ("a.pdf", "amount"): []}
        recall = run_digest_eval.score(inventory, extracted)
        self.assertEqual(recall["party"], {"hit": 1, "total": 2})
        self.assertEqual(recall["amount"], {"hit": 0, "total": 1})

    def test_targets_gate(self):
        self.assertTrue(run_digest_eval.meets_targets(
            {"party": {"hit": 9, "total": 10}}, {"party": 0.90}))
        self.assertFalse(run_digest_eval.meets_targets(
            {"party": {"hit": 8, "total": 10}}, {"party": 0.90}))


if __name__ == "__main__":
    unittest.main(verbosity=2)
