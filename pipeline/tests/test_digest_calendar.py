"""Deadline -> calendar.ics export: confirmed deadlines produce a well-formed, RFC 5545
VEVENT carrying the attorney's confirmed date verbatim (no computed dates, no alarms).
Unconfirmed/dismissed/unknown facts are refused."""

import sys
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

PIPELINE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPELINE_DIR))
import catalog  # noqa: E402
import api  # noqa: E402
import routes_digest  # noqa: E402

client = TestClient(api.app)


def _fact(key, ftype="date_event", value=None, page=1, span="within 30 days"):
    return {"fact_type": ftype,
            "value": value or {"kind": "deadline", "label": "Answer due",
                               "date_text": "within 30 days", "date_iso": None,
                               "date_kind": "relative", "anchor": "service"},
            "page": page, "char_start": 0, "char_end": len(span),
            "span": span, "fact_key": key}


class TestDeadlineCalendar(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._cat, catalog.DEFAULT_DB = catalog.DEFAULT_DB, self.tmp / "cat.db"
        catalog.create_matter("Nimbus Dispute")
        self.pdf_path = self.tmp / "msa.pdf"
        self.pdf_path.write_text("dummy content")
        self.doc = catalog.add_document("nimbus-dispute", self.pdf_path, status="ready")
        catalog.replace_facts(self.doc["id"], "nimbus-dispute", [
            _fact("dl", value={"kind": "deadline", "label": "Response to termination notice",
                               "date_text": "within 30 days", "date_iso": None,
                               "date_kind": "relative", "anchor": "service"}),
            _fact("ev", value={"kind": "event", "label": "MSA executed",
                               "date_text": "March 1, 2026", "date_iso": "2026-03-01",
                               "date_kind": "explicit", "anchor": None}),
            _fact("dl_comma", value={"kind": "obligation", "label": "Notice, cure; and remedy",
                                     "date_text": "10 days", "date_iso": None,
                                     "date_kind": "relative", "anchor": "receipt"},
                  span="within 10 days, subject to; a cure period\nsecond line of the clause"),
            _fact("dl_long", value={"kind": "deadline", "label": "Long clause deadline",
                                    "date_text": "within 45 days", "date_iso": None,
                                    "date_kind": "relative", "anchor": "service"},
                  span="A very long verbatim quoted span pulled straight from the source "
                       "document that will force RFC 5545 line folding to kick in for real"),
        ], "v1")

    def tearDown(self):
        catalog.DEFAULT_DB = self._cat

    def _confirm(self, key, date="2026-07-24"):
        r = client.post(f"/matters/nimbus-dispute/facts/{key}/review",
                        json={"status": "confirmed", "confirmed_date": date})
        self.assertEqual(r.status_code, 200)

    def test_confirmed_deadline_returns_ics(self):
        self._confirm("dl", "2026-07-24")
        r = client.get("/matters/nimbus-dispute/facts/dl/calendar.ics")
        self.assertEqual(r.status_code, 200)
        self.assertIn("text/calendar", r.headers["content-type"])
        self.assertIn("attachment", r.headers["content-disposition"])
        self.assertIn("deadline-2026-07-24.ics", r.headers["content-disposition"])
        body = r.text
        self.assertIn("BEGIN:VCALENDAR", body)
        self.assertIn("VERSION:2.0", body)
        self.assertIn("PRODID:-//docuchat//EN", body)
        self.assertIn("UID:dl@docuchat.local", body)
        self.assertIn("DTSTART;VALUE=DATE:20260724", body)
        self.assertIn("SUMMARY:Response to termination notice (Nimbus Dispute)", body)
        self.assertIn("END:VEVENT", body)
        self.assertIn("END:VCALENDAR", body)

    def test_audit_entry_written(self):
        self._confirm("dl", "2026-07-24")
        client.get("/matters/nimbus-dispute/facts/dl/calendar.ics")
        entries = catalog.audit_entries("nimbus-dispute")
        events = [e["event"] for e in entries]
        self.assertIn("deadline_calendar_export", events)

    def test_rfc_escaping_of_comma_semicolon_newline(self):
        self._confirm("dl_comma", "2026-08-01")
        r = client.get("/matters/nimbus-dispute/facts/dl_comma/calendar.ics")
        self.assertEqual(r.status_code, 200)
        raw = r.content.decode("utf-8")
        # unfold physical lines (CRLF + single leading WSP) before checking escaping
        unfolded = raw.replace("\r\n ", "").replace("\r\n\t", "")
        self.assertIn("within 10 days\\, subject to\\; a cure period\\nsecond line", unfolded)
        # a raw (unescaped) comma/semicolon must not appear in the DESCRIPTION value
        desc_line = next(l for l in unfolded.split("\r\n") if l.startswith("DESCRIPTION:"))
        self.assertNotIn(",", desc_line.replace("\\,", ""))
        self.assertNotIn(";", desc_line.replace("\\;", ""))

    def test_long_line_is_folded_under_76_octets(self):
        self._confirm("dl_long", "2026-09-01")
        r = client.get("/matters/nimbus-dispute/facts/dl_long/calendar.ics")
        self.assertEqual(r.status_code, 200)
        for line in r.content.split(b"\r\n"):
            self.assertLessEqual(len(line), 75, line)
        # a folded description line must exist (source span alone exceeds 75 octets)
        self.assertTrue(any(l.startswith(b" ") for l in r.content.split(b"\r\n")))

    def test_required_properties_present(self):
        self._confirm("dl", "2026-07-24")
        r = client.get("/matters/nimbus-dispute/facts/dl/calendar.ics")
        lines = r.content.decode("utf-8").split("\r\n")
        joined = "\n".join(lines)
        for prop in ("BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:", "BEGIN:VEVENT",
                     "UID:", "DTSTAMP:", "DTSTART;VALUE=DATE:", "SUMMARY:",
                     "DESCRIPTION:", "END:VEVENT", "END:VCALENDAR"):
            self.assertIn(prop, joined)

    def test_unconfirmed_deadline_rejected(self):
        r = client.get("/matters/nimbus-dispute/facts/dl/calendar.ics")
        self.assertIn(r.status_code, (400, 409))

    def test_dismissed_deadline_rejected(self):
        client.post("/matters/nimbus-dispute/facts/dl/review", json={"status": "dismissed"})
        r = client.get("/matters/nimbus-dispute/facts/dl/calendar.ics")
        self.assertIn(r.status_code, (400, 409))

    def test_non_deadline_fact_rejected(self):
        # "ev" is a plain event, not a deadline/obligation
        client.post("/matters/nimbus-dispute/facts/ev/review",
                    json={"status": "confirmed", "confirmed_date": "2026-03-01"})
        r = client.get("/matters/nimbus-dispute/facts/ev/calendar.ics")
        self.assertIn(r.status_code, (400, 409))

    def test_unknown_matter_404(self):
        r = client.get("/matters/nope/facts/dl/calendar.ics")
        self.assertEqual(r.status_code, 404)

    def test_unknown_fact_404(self):
        r = client.get("/matters/nimbus-dispute/facts/nope/calendar.ics")
        self.assertEqual(r.status_code, 404)


class TestIcsHelpers(unittest.TestCase):
    def test_escape_order_and_chars(self):
        raw = 'a\\b,c;d\ne'
        esc = routes_digest._ics_escape(raw)
        self.assertEqual(esc, 'a\\\\b\\,c\\;d\\ne')

    def test_fold_short_line_untouched(self):
        line = "SUMMARY:short"
        self.assertEqual(routes_digest._ics_fold_line(line), line)

    def test_fold_long_line_all_physical_lines_le_75_octets(self):
        line = "DESCRIPTION:" + ("x" * 200)
        folded = routes_digest._ics_fold_line(line)
        for physical in folded.split(routes_digest._ICS_CRLF):
            self.assertLessEqual(len(physical.encode("utf-8")), 75)

    def test_fold_does_not_split_multibyte_utf8(self):
        # en-dash-free content but with accented characters near the fold boundary
        line = "SUMMARY:" + ("é" * 80)
        folded = routes_digest._ics_fold_line(line)
        # every physical line must decode cleanly as UTF-8 (no split multi-byte char)
        for physical in folded.split(routes_digest._ICS_CRLF):
            physical.lstrip(" ").encode("utf-8")  # would raise if line itself is malformed
        rejoined = "".join(p[1:] if i else p for i, p in
                           enumerate(folded.split(routes_digest._ICS_CRLF)))
        self.assertEqual(rejoined, line)


if __name__ == "__main__":
    unittest.main(verbosity=2)
