"""B4 — logprob answer-confidence (non-gating, display-only).

confidence = exp(mean token logprob) (kotaemon qa_score), computed from the Ollama
response's logprobs. It is a DISPLAY signal only: it is added to the result but never feeds
the mechanical verifier, so it can NEVER change which citations are verified/displayed
(D-19/D-38). Default answer() does not request logprobs (parity preserved); confidence is
opt-in via with_confidence=True.
"""

import math
import sys
import unittest
from pathlib import Path

PIPELINE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPELINE_DIR))
import answering  # noqa: E402


class TestConfidenceFromLogprobs(unittest.TestCase):
    def test_exp_mean_logprob(self):
        lp = [{"token": "a", "logprob": -0.2}, {"token": "b", "logprob": -0.4}]
        self.assertAlmostEqual(answering.confidence_from_logprobs(lp),
                               math.exp((-0.2 + -0.4) / 2))

    def test_empty_is_none(self):
        self.assertIsNone(answering.confidence_from_logprobs([]))
        self.assertIsNone(answering.confidence_from_logprobs(None))

    def test_confident_token_scores_high(self):
        self.assertAlmostEqual(answering.confidence_from_logprobs([{"token": "ok", "logprob": 0.0}]), 1.0)


class TestConfidenceIsDisplayOnly(unittest.TestCase):
    """confidence must never alter the verified citations."""

    def setUp(self):
        chunk = {"source_filename": "d.pdf", "matter": "m", "page_number": 1,
                 "section": "S", "char_start": 0, "char_end": 40,
                 "text": "The monthly fee is $1,234 per the terms."}
        self._retr = answering.retrieve
        self._chat = answering._chat
        self._post = answering._post_chat
        answering.retrieve = lambda *a, **k: [chunk]
        text = ('The monthly fee is $1,234 [document: d.pdf, page: 1, chunk: C1, '
                'span: "$1,234"].')
        answering._chat = lambda *a, **k: text
        answering._post_chat = lambda *a, **k: {
            "message": {"content": text},
            "logprobs": [{"token": "x", "logprob": -0.1}, {"token": "y", "logprob": -0.3}]}

    def tearDown(self):
        answering.retrieve = self._retr
        answering._chat = self._chat
        answering._post_chat = self._post

    def test_citations_identical_with_and_without_confidence(self):
        base = answering.answer("fee?", matter="m")
        conf = answering.answer("fee?", matter="m", with_confidence=True)
        self.assertEqual(base["citations"], conf["citations"])
        self.assertNotIn("confidence", base)                 # default path unchanged
        self.assertIn("confidence", conf)
        self.assertIsInstance(conf["confidence"], float)
        self.assertGreater(conf["confidence"], 0.0)
        self.assertLessEqual(conf["confidence"], 1.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
