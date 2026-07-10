"""UX-11 proof: universal file import — HTML, VTT/SRT meeting transcripts, CSV, JSON.

All stdlib parsing, single-page records like .txt (no fake page splits). VTT/SRT is
the export format Zoom/Teams/Meet hand out for meeting transcripts: cue text keeps a
searchable [HH:MM:SS] start-time prefix and speaker tags."""

import sys
import tempfile
import unittest
from pathlib import Path

PIPELINE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPELINE_DIR))
import extractors  # noqa: E402
import routes_kb  # noqa: E402


def _extract(tmp, name, body):
    p = tmp / name
    p.write_text(body, encoding="utf-8")
    pages = extractors.extract(p)
    return pages[0]


class TestNewFormats(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def test_all_new_suffixes_uploadable(self):
        for suf in (".html", ".htm", ".vtt", ".srt", ".csv", ".json"):
            self.assertIn(suf, routes_kb._ALLOWED, suf)

    def test_html_strips_scripts_and_tags(self):
        r = _extract(self.tmp, "letter.html",
                     "<html><head><style>b{color:red}</style>"
                     "<script>alert('x')</script></head>"
                     "<body><h1>Demand Letter</h1><p>Amount due: <b>$12,000</b> "
                     "&amp; interest.</p></body></html>")
        self.assertIn("Demand Letter", r["page_text"])
        self.assertIn("$12,000 & interest", r["page_text"])
        self.assertNotIn("alert", r["page_text"])
        self.assertNotIn("<", r["page_text"])

    def test_vtt_meeting_transcript_keeps_timestamps_and_speakers(self):
        r = _extract(self.tmp, "client-call.vtt",
                     "WEBVTT\n\n1\n00:00:12.000 --> 00:00:15.000\n"
                     "<v Jake Anderson>We propose $45,000 to settle.\n\n"
                     "2\n00:01:02.500 --> 00:01:04.000\nOpposing counsel: rejected.\n")
        self.assertEqual(r["source"], "vtt")
        self.assertIn("[00:00:12] Jake Anderson: We propose $45,000",
                      r["page_text"])
        self.assertIn("[00:01:02]", r["page_text"])
        self.assertNotIn("-->", r["page_text"])
        self.assertNotIn("WEBVTT", r["page_text"])

    def test_srt_transcript(self):
        r = _extract(self.tmp, "depo.srt",
                     "1\n00:00:05,000 --> 00:00:07,000\nState your name.\n\n"
                     "2\n01:02:03,000 --> 01:02:05,000\nJane Doe.\n")
        self.assertIn("[00:00:05] State your name.", r["page_text"])
        self.assertIn("[01:02:03] Jane Doe.", r["page_text"])

    def test_csv_rows_readable(self):
        r = _extract(self.tmp, "billing.csv",
                     "date,description,amount\n2026-01-05,Filing fee,310.00\n")
        self.assertIn("date | description | amount", r["page_text"])
        self.assertIn("2026-01-05 | Filing fee | 310.00", r["page_text"])

    def test_json_pretty_and_malformed_fallback(self):
        r = _extract(self.tmp, "matter.json", '{"client":"Acme","fee":5000}')
        self.assertIn('"client": "Acme"', r["page_text"])
        bad = _extract(self.tmp, "notes.json", "{not json")
        self.assertIn("not json", bad["page_text"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
