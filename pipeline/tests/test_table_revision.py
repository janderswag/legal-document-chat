"""A0a — code-enforce the pinned TableFormer model revision (D-50/D-53 carry-forward).

`TABLEFORMER_REVISION` was documentary-only; this asserts the locally-cached Docling model
snapshot actually matches the pin, so a silent model swap fails loud (forcing a deliberate
re-index) instead of silently changing table extraction. Both paths tested: a matching
cache passes; a mismatched cache raises.
"""

import sys
import unittest
from pathlib import Path

PIPELINE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPELINE_DIR))
import table_extract  # noqa: E402


class TestModelRevisionPin(unittest.TestCase):
    def test_pin_is_a_40hex_commit(self):
        self.assertRegex(table_extract.TABLEFORMER_REVISION, r"^[0-9a-f]{40}$")

    def test_cached_revision_matches_pin_on_this_machine(self):
        rev = table_extract.cached_model_revision()
        self.assertEqual(rev, table_extract.TABLEFORMER_REVISION,
                         "cached Docling model snapshot != pin (re-index intended?)")

    def test_assert_passes_when_cache_matches(self):
        # real cache matches the pin -> returns the revision, no raise
        self.assertEqual(table_extract.assert_model_revision(),
                         table_extract.TABLEFORMER_REVISION)

    def test_assert_fails_loud_on_revision_mismatch(self):
        orig = table_extract.cached_model_revision
        table_extract.cached_model_revision = lambda: "0" * 40  # simulate a swapped model
        try:
            with self.assertRaises(RuntimeError):
                table_extract.assert_model_revision()
        finally:
            table_extract.cached_model_revision = orig

    def test_assert_is_lenient_when_cache_absent(self):
        # a fresh machine (about to fetch) has no resolvable cached commit -> don't block
        orig = table_extract.cached_model_revision
        table_extract.cached_model_revision = lambda: None
        try:
            self.assertIsNone(table_extract.assert_model_revision())
        finally:
            table_extract.cached_model_revision = orig


if __name__ == "__main__":
    unittest.main(verbosity=2)
