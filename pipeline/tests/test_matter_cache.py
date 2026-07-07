"""Move 0a (D-68) — the matter allowlist must be a version-cached COLUMN scan, never a
full-store materialization, and the cache must invalidate on any store write (LanceDB
bumps the table version on every write, which is the invalidation signal).

Behavioral contract preserved from the original implementation: the allowlist is exactly
the set of matter values present in the target store; unknown matters raise; the D-18
prefilter isolation is untouched (covered by test_retrieval.py)."""

import sys
import tempfile
import unittest
from pathlib import Path

PIPELINE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPELINE_DIR))
import retrieval  # noqa: E402
from embed_store import EMBED_DIM, open_table  # noqa: E402


def _mk_store(db_path, matters):
    """A tiny store with one chunk per matter (random-ish fixed vectors; no Ollama)."""
    import lancedb
    import pyarrow as pa

    rows = [{
        "source_filename": f"{m}.pdf", "matter": m, "document_type": "doc",
        "page_number": 1, "section": "", "char_start": 0, "char_end": 4,
        "text": "text", "embedding_text": "text",
        "vector": [float(i % 7) / 7.0] * EMBED_DIM,
    } for i, m in enumerate(matters)]
    db = lancedb.connect(str(db_path))
    schema = pa.schema([
        pa.field("source_filename", pa.string()), pa.field("matter", pa.string()),
        pa.field("document_type", pa.string()), pa.field("page_number", pa.int64()),
        pa.field("section", pa.string()), pa.field("char_start", pa.int64()),
        pa.field("char_end", pa.int64()), pa.field("text", pa.string()),
        pa.field("embedding_text", pa.string()),
        pa.field("vector", pa.list_(pa.float32(), EMBED_DIM)),
    ])
    db.create_table("chunks", rows, schema=schema)


class TestMatterAllowlistCache(unittest.TestCase):
    def setUp(self):
        self.db = Path(tempfile.mkdtemp()) / ".lancedb_t"
        _mk_store(self.db, ["matter-a", "matter-b"])
        retrieval._MATTERS_CACHE.clear()

    def test_known_matters_reads_the_store(self):
        self.assertEqual(retrieval.known_matters(self.db), ["matter-a", "matter-b"])

    def test_second_call_is_a_cache_hit(self):
        retrieval.known_matters(self.db)
        key = str(self.db)
        self.assertIn(key, retrieval._MATTERS_CACHE)
        ver, matters = retrieval._MATTERS_CACHE[key]
        # poison the cached set; a cache hit must return the poisoned value (proving no rescan)
        retrieval._MATTERS_CACHE[key] = (ver, frozenset({"poisoned"}))
        self.assertEqual(retrieval.known_matters(self.db), ["poisoned"])

    def test_store_write_invalidates_the_cache(self):
        self.assertEqual(retrieval.known_matters(self.db), ["matter-a", "matter-b"])
        table = open_table(str(self.db))
        table.add([{
            "source_filename": "c.pdf", "matter": "matter-c", "document_type": "doc",
            "page_number": 1, "section": "", "char_start": 0, "char_end": 4,
            "text": "text", "embedding_text": "text", "vector": [0.5] * EMBED_DIM,
        }])
        # the add bumped the table version -> next call must rescan and see matter-c
        self.assertIn("matter-c", retrieval.known_matters(self.db))

    def test_unknown_matter_still_rejected(self):
        table = open_table(str(self.db))
        with self.assertRaises(ValueError):
            retrieval._matter_filter(table, "not-a-matter", str(self.db))

    def test_filter_string_unchanged_for_known_matter(self):
        table = open_table(str(self.db))
        self.assertEqual(retrieval._matter_filter(table, "matter-a", str(self.db)),
                         "matter = 'matter-a'")

    def test_empty_store_yields_empty_allowlist(self):
        empty = Path(tempfile.mkdtemp()) / ".lancedb_e"
        _mk_store(empty, ["only"])
        table = open_table(str(empty))
        table.delete("matter = 'only'")
        retrieval._MATTERS_CACHE.clear()
        self.assertEqual(retrieval.known_matters(empty), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
