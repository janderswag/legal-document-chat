"""Move 1b (D-69) — the refusal-triggered second pass: ONE wider anchor-fed retry that
can upgrade a refusal to a SPAN-VERIFIED answer but never to an unverified one
(never-false-accept is preserved by construction: the retry ends at the same verifier).
All Ollama + retrieval calls are mocked; no model or store is touched."""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

PIPELINE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPELINE_DIR))
import answering  # noqa: E402
from answering import REFUSAL, answer, answer_stream, extract_anchors  # noqa: E402

CHUNK = {"source_filename": "d.pdf", "matter": "m", "page_number": 4, "section": "",
         "char_start": 0, "char_end": 40, "text": "The monthly fee is $1,234 exactly."}
VERIFIED = ('The monthly fee is $1,234 '
            '[document: d.pdf, page: 4, chunk: C1, span: "monthly fee is $1,234"].')
FABRICATED = ('The fee is $9,999 '
              '[document: d.pdf, page: 4, chunk: C1, span: "fee is $9,999"].')


class TestAnchors(unittest.TestCase):
    def test_extracts_the_query_shapes_attorneys_use(self):
        a = extract_anchors('What did "the parties" agree for INV-77341, case 5:26-cv-04417, '
                            'about $14,862.50 owed to Nimbus Pemberton per § 12.3?')
        self.assertIn("the parties", a)
        self.assertIn("INV-77341", a)
        self.assertIn("$14,862.50", a)
        self.assertIn("Nimbus Pemberton", a)
        self.assertTrue(any("12.3" in x for x in a))

    def test_no_anchors_returns_empty(self):
        self.assertEqual(extract_anchors("what happens if they stop paying rent"), [])


class TestSecondPassAnswer(unittest.TestCase):
    def _run(self, first, second):
        calls = {"n": 0, "wide": 0}

        def fake_chat(messages, **k):
            calls["n"] += 1
            return first if calls["n"] == 1 else second

        def fake_retrieve(question, **kw):
            if kw.get("hybrid"):
                calls["wide"] += 1
            return [CHUNK]

        with patch.object(answering, "_chat", side_effect=fake_chat), \
             patch.object(answering, "retrieve", side_effect=fake_retrieve):
            res = answer("What is the monthly fee?", matter="m")
        return res, calls

    def test_refusal_upgraded_by_verified_second_pass(self):
        res, calls = self._run(REFUSAL, VERIFIED)
        self.assertTrue(res["second_pass"])
        self.assertEqual(calls["wide"], 1)          # wider hybrid retrieval ran
        self.assertEqual(len(res["citations"]), 1)  # verified
        self.assertNotIn(REFUSAL, res["answer_text"])

    def test_second_refusal_stays_refusal_with_wide_leads(self):
        res, calls = self._run(REFUSAL, REFUSAL)
        self.assertFalse(res["second_pass"])
        self.assertIn(REFUSAL, res["answer_text"])
        self.assertEqual(res["citations"], [])
        self.assertTrue(res["grounding_chunks"])    # near-miss leads present

    def test_unverified_second_pass_never_adopted(self):
        # the retry hallucinated a span not in the chunk -> verifier rejects -> the
        # refusal stands (a refusal may never become an unverified answer)
        res, _ = self._run(REFUSAL, FABRICATED)
        self.assertFalse(res["second_pass"])
        self.assertIn(REFUSAL, res["answer_text"])
        self.assertEqual(res["citations"], [])

    def test_non_refusal_first_pass_runs_once(self):
        res, calls = self._run(VERIFIED, "unused")
        self.assertFalse(res["second_pass"])
        self.assertEqual(calls["n"], 1)
        self.assertEqual(calls["wide"], 0)


class TestSecondPassStream(unittest.TestCase):
    def test_stream_emits_second_pass_marker_then_new_sources(self):
        texts = iter([REFUSAL, VERIFIED])

        def fake_stream(messages, **k):
            yield next(texts)

        with patch.object(answering, "_stream_tokens", side_effect=fake_stream), \
             patch.object(answering, "retrieve", return_value=[CHUNK]):
            events = list(answer_stream("fee?", matter="m"))
        kinds = [e["type"] for e in events]
        self.assertEqual(kinds.count("sources"), 2)
        self.assertIn("second_pass", kinds)
        self.assertLess(kinds.index("second_pass"), kinds.index("sources", 1))
        result = events[-1]
        self.assertEqual(result["type"], "result")
        self.assertEqual(len(result["citations"]), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
