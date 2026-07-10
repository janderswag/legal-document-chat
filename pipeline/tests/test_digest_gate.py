"""M-2 write gate: the LLM proposes, verifier.locate_span disposes. A fabricated
span never becomes a row; a truthful span lands with mechanical page offsets.
date_iso survives only when explicit. Page reconstruction round-trips chunk tiling."""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import lancedb
import pyarrow as pa

PIPELINE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPELINE_DIR))
import catalog  # noqa: E402
import digest  # noqa: E402

PAGE1 = ("MASTER SERVICE AGREEMENT dated March 1, 2026 between Nimbus Analytics LLC "
         "(“Provider”) and Pemberton Logistics Inc. Recipient may cure within "
         "thirty (30) days after receipt of written notice of termination.")


def _raw(**kw):
    base = {"fact_type": "date_event", "span": "within thirty (30) days after receipt",
            "page": 1, "kind": "deadline", "label": "Cure period",
            "date_text": "within thirty (30) days after receipt",
            "date_iso": "", "date_kind": "relative", "anchor": "receipt of notice"}
    base.update(kw)
    return base


class TestGate(unittest.TestCase):
    def setUp(self):
        self.pages = [{"page_number": 1, "page_text": PAGE1}]

    def test_verified_span_becomes_fact_with_mechanical_offsets(self):
        verified, dropped = digest.gate_facts([_raw()], self.pages, doc_id=7)
        self.assertEqual(dropped, 0)
        f = verified[0]
        self.assertEqual(f["page"], 1)
        self.assertEqual(PAGE1[f["char_start"]:f["char_end"]].lower()[:12], "within thirt")
        self.assertEqual(f["value"]["kind"], "deadline")
        self.assertEqual(f["fact_key"], digest.fact_key(7, "date_event", 1, f["span"]))

    def test_fabricated_span_dropped_and_counted(self):
        verified, dropped = digest.gate_facts(
            [_raw(span="the fee shall be ten million dollars")], self.pages, doc_id=7)
        self.assertEqual((verified, dropped), ([], 1))

    def test_date_iso_only_when_explicit(self):
        raw = _raw(span="dated March 1, 2026", date_text="March 1, 2026",
                   date_kind="relative", date_iso="2026-03-01")
        verified, _ = digest.gate_facts([raw], self.pages, doc_id=7)
        self.assertIsNone(verified[0]["value"]["date_iso"])   # relative -> stripped
        raw = _raw(span="dated March 1, 2026", date_text="March 1, 2026",
                   date_kind="explicit", date_iso="2026-03-01")
        verified, _ = digest.gate_facts([raw], self.pages, doc_id=7)
        self.assertEqual(verified[0]["value"]["date_iso"], "2026-03-01")
        raw = _raw(date_kind="explicit", date_iso="March next year")
        verified, _ = digest.gate_facts([raw], self.pages, doc_id=7)
        self.assertIsNone(verified[0]["value"]["date_iso"])   # malformed -> stripped

    def test_wrong_reported_page_recovers_by_search(self):
        pages = [{"page_number": 1, "page_text": "nothing here"},
                 {"page_number": 2, "page_text": PAGE1}]
        verified, dropped = digest.gate_facts([_raw(page=1)], pages, doc_id=7)
        self.assertEqual(dropped, 0)
        self.assertEqual(verified[0]["page"], 2)              # page is where it was FOUND

    def test_required_value_fields_enforced(self):
        verified, dropped = digest.gate_facts(
            [{"fact_type": "party", "span": "Nimbus Analytics LLC", "page": 1}],
            self.pages, doc_id=7)                              # party without a name
        self.assertEqual((verified, dropped), ([], 1))


class TestExtractForDocument(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._cat, catalog.DEFAULT_DB = catalog.DEFAULT_DB, self.tmp / "cat.db"
        catalog.create_matter("Nimbus Dispute")
        self.pdf_path = self.tmp / "msa.pdf"
        self.pdf_path.write_text("dummy content")
        self.doc = catalog.add_document("nimbus-dispute", self.pdf_path, status="ready")

    def tearDown(self):
        catalog.DEFAULT_DB = self._cat

    def test_extracts_writes_and_stamps(self):
        with mock.patch.object(digest, "pages_from_store",
                               return_value=[{"page_number": 1, "page_text": PAGE1}]), \
             mock.patch.object(digest, "_extract_call",
                               return_value=[_raw(), _raw(span="not in the doc at all")]), \
             mock.patch.object(digest, "_yield_to_chat"):
            out = digest.extract_for_document(self.doc["id"], self.tmp / "kb")
        self.assertEqual(out, {"extracted": 1, "dropped": 1})
        rows = catalog.facts_for_matter("nimbus-dispute")
        self.assertEqual(len(rows), 1)
        self.assertEqual(catalog.get_document(self.doc["id"])["digest_version"],
                         digest.EXTRACTOR_VERSION)

    def test_disabled_by_env(self):
        with mock.patch.dict("os.environ", {"LDI_MATTER_DIGEST": "0"}):
            self.assertIsNone(digest.extract_for_document(self.doc["id"], self.tmp / "kb"))

    def test_store_read_failure_leaves_doc_unstamped(self):
        with mock.patch.object(digest, "pages_from_store",
                               side_effect=RuntimeError("lance down")):
            out = digest.extract_for_document(self.doc["id"], self.tmp / "kb")
        self.assertIsNone(out)
        self.assertIsNone(catalog.get_document(self.doc["id"])["digest_version"])

    def test_extract_call_failure_leaves_doc_unstamped(self):
        # _extract_call returning None means a transport/JSON failure, indistinguishable
        # from a genuine empty result if left unhandled — must not stamp digest_version.
        with mock.patch.object(digest, "pages_from_store",
                               return_value=[{"page_number": 1, "page_text": PAGE1}]), \
             mock.patch.object(digest, "_extract_call", return_value=None), \
             mock.patch.object(digest, "_yield_to_chat"):
            out = digest.extract_for_document(self.doc["id"], self.tmp / "kb")
        self.assertIsNone(out)
        self.assertEqual(catalog.facts_for_matter("nimbus-dispute"), [])
        self.assertIsNone(catalog.get_document(self.doc["id"])["digest_version"])


class TestPageGrouping(unittest.TestCase):
    def test_groups_respect_page_and_char_budget(self):
        pages = [{"page_number": i, "page_text": "x" * 3000} for i in range(1, 8)]
        groups = digest._groups(pages, max_chars=6000, max_pages=4)
        self.assertTrue(all(len(g) <= 4 for g in groups))
        self.assertTrue(all(sum(len(p["page_text"]) for p in g) <= 6000 or len(g) == 1
                            for g in groups))
        self.assertEqual(sum(len(g) for g in groups), 7)       # every page exactly once


class TestPagesFromLegacyStore(unittest.TestCase):
    def test_pre_d69_store_without_document_type(self):
        tmp = Path(tempfile.mkdtemp())
        schema = pa.schema([
            pa.field("source_filename", pa.string()), pa.field("matter", pa.string()),
            pa.field("page_number", pa.int64()), pa.field("char_start", pa.int64()),
            pa.field("char_end", pa.int64()), pa.field("text", pa.string()),
        ])
        rows = [{"source_filename": "a.pdf", "matter": "m", "page_number": 1,
                 "char_start": 0, "char_end": 5, "text": "hello"},
                {"source_filename": "a.pdf", "matter": "m", "page_number": 1,
                 "char_start": 5, "char_end": 11, "text": " world"}]
        lancedb.connect(str(tmp / "db")).create_table("chunks", data=rows, schema=schema)
        pages = digest.pages_from_store(tmp / "db", "a.pdf", "m")
        self.assertEqual(pages, [{"page_number": 1, "page_text": "hello world"}])

    def test_modern_store_with_document_type_excludes_table_chunks(self):
        tmp = Path(tempfile.mkdtemp())
        schema = pa.schema([
            pa.field("source_filename", pa.string()), pa.field("matter", pa.string()),
            pa.field("page_number", pa.int64()), pa.field("char_start", pa.int64()),
            pa.field("char_end", pa.int64()), pa.field("text", pa.string()),
            pa.field("document_type", pa.string()),
        ])
        rows = [{"source_filename": "a.pdf", "matter": "m", "page_number": 1,
                 "char_start": 0, "char_end": 5, "text": "hello", "document_type": "prose"},
                {"source_filename": "a.pdf", "matter": "m", "page_number": 1,
                 "char_start": 5, "char_end": 11, "text": " world", "document_type": "prose"},
                {"source_filename": "a.pdf", "matter": "m", "page_number": 1,
                 "char_start": 0, "char_end": 20, "text": "| a | b |",
                 "document_type": "table"}]
        lancedb.connect(str(tmp / "db")).create_table("chunks", data=rows, schema=schema)
        pages = digest.pages_from_store(tmp / "db", "a.pdf", "m")
        self.assertEqual(pages, [{"page_number": 1, "page_text": "hello world"}])


if __name__ == "__main__":
    unittest.main(verbosity=2)
