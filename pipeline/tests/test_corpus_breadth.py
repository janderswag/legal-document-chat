"""Task 2 proof: the synthetic corpus is 20-50 docs across >=4 document_types and >=3
formats (PDF+DOCX+TXT/MD incl. >=5 scanned), and ingests clean through the T1
orchestrator. Bodies are git-ignored (D-28); document_type comes from the tracked
sidecar eval/corpus_manifest.jsonl. Synthetic-only."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

PIPELINE_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = PIPELINE_DIR.parent
CORPUS = REPO_ROOT / "documents" / "synthetic_corpus" / "corpus"
SIDECAR = REPO_ROOT / "eval" / "corpus_manifest.jsonl"

sys.path.insert(0, str(PIPELINE_DIR))
from ingest_pipeline import ingest_dir  # noqa: E402

_TYPES = {"contract", "correspondence", "pleading", "public_legal_text"}


def _sidecar():
    return [json.loads(l) for l in SIDECAR.read_text().splitlines() if l.strip()]


class TestCorpusBreadth(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not CORPUS.is_dir():
            raise unittest.SkipTest("corpus not built — run: .venv/bin/python build_corpus.py")
        cls.tmp = tempfile.mkdtemp()
        cls.report = ingest_dir(CORPUS, Path(cls.tmp) / "report.jsonl", Path(cls.tmp) / "failed")

    def test_at_least_20_docs_ingest_clean(self):
        self.assertGreaterEqual(
            len(self.report["ingested"]), 20,
            f"only {len(self.report['ingested'])} ingested clean "
            f"(quarantined={len(self.report['quarantined'])}, "
            f"needs_review={len(self.report['needs_review'])})",
        )

    def test_at_most_50_docs(self):
        total = (len(self.report["ingested"]) + len(self.report["needs_review"])
                 + len(self.report["quarantined"]))
        self.assertLessEqual(total, 50)

    def test_three_formats_present(self):
        formats = {Path(x["file"]).suffix.lower() for x in self.report["ingested"]}
        self.assertTrue({".pdf", ".docx", ".txt"} <= formats, f"missing formats: {formats}")

    def test_all_four_document_types_present(self):
        types = {s["document_type"] for s in _sidecar()}
        self.assertEqual(types, _TYPES, f"document_types present: {types}")

    def test_format_minimums_docx_txt_scanned(self):
        side = {s["filename"]: s for s in _sidecar()}
        ingested_names = {x["file"] for x in self.report["ingested"]}
        fmt = lambda f: side.get(f, {}).get("format")
        docx = [f for f in ingested_names if fmt(f) == "docx"]
        textmd = [f for f in ingested_names if fmt(f) in ("txt", "md")]
        scanned = [f for f in ingested_names if fmt(f) == "scanned_pdf"]
        self.assertGreaterEqual(len(docx), 3, f"docx={docx}")
        self.assertGreaterEqual(len(textmd), 3, f"txt/md={textmd}")
        self.assertGreaterEqual(len(scanned), 5, f"scanned={scanned}")

    def test_sidecar_covers_every_ingested_file(self):
        side = {s["filename"] for s in _sidecar()}
        for x in self.report["ingested"]:
            self.assertIn(x["file"], side, f"{x['file']} missing from corpus_manifest.jsonl")


if __name__ == "__main__":
    unittest.main(verbosity=2)
