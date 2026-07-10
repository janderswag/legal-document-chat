"""Self-heal recovery proofs (v0.3.2). The dangerous failure mode is a FALSE
POSITIVE that moves a HEALTHY data dir aside (data loss), so these tests lean
hard on the "must NOT act" cases: healthy catalog, plain catalog, missing/empty
catalog, and an unobtainable master key (transient Keychain lock). It acts ONLY
when the catalog is encrypted-format AND genuinely won't open with a real key.
"""

import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

PIPELINE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPELINE_DIR))
import catalog  # noqa: E402
import startup_recovery  # noqa: E402

FIXED_NOW = datetime(2026, 7, 10, 15, 30, 0, tzinfo=timezone.utc)
KEY = b"\x11" * 32


class RecoveryBase(unittest.TestCase):
    def setUp(self):
        if sys.platform != "darwin":
            self.skipTest("recovery is macOS-only")
        self.tmp = Path(tempfile.mkdtemp())
        self.data = self.tmp / "docuchat"
        self.data.mkdir()
        self.db = self.data / ".kb_catalog.db"
        # point the module at our sandbox
        self._prod, catalog._PRODUCTION_DB = catalog._PRODUCTION_DB, self.db
        self._def, catalog.DEFAULT_DB = catalog.DEFAULT_DB, self.db
        self._mkp, catalog.MASTER_KEY_PROVIDER = catalog.MASTER_KEY_PROVIDER, \
            lambda: KEY
        import apppaths
        self._data_root = apppaths.data_root
        apppaths.data_root = lambda: self.data
        self.detached = []

    def tearDown(self):
        catalog._PRODUCTION_DB = self._prod
        catalog.DEFAULT_DB = self._def
        catalog.MASTER_KEY_PROVIDER = self._mkp
        import apppaths
        apppaths.data_root = self._data_root

    def _fake_detach(self, mp):
        self.detached.append(mp)

    def _run(self):
        return startup_recovery.recover_if_unreadable(now=FIXED_NOW,
                                                      detach=self._fake_detach)

    def _write_encrypted_catalog(self):
        """A real SQLCipher catalog encrypted with KEY (opens with KEY)."""
        conn = catalog._connect(self.db)  # created encrypted via the provider
        conn.close()
        self.assertTrue(catalog.is_encrypted(self.db))


class TestMustNotAct(RecoveryBase):
    def test_healthy_encrypted_catalog_is_left_alone(self):
        self._write_encrypted_catalog()
        self.assertIsNone(self._run())
        self.assertTrue(self.data.exists())
        self.assertTrue(self.db.exists())
        self.assertEqual(self.detached, [])

    def test_plain_sqlite_catalog_is_left_alone(self):
        # simulate a non-production (plain) catalog: no encryption
        catalog.MASTER_KEY_PROVIDER = None
        self.db.write_bytes(b"SQLite format 3\x00" + b"\x00" * 100)
        self.assertIsNone(self._run())
        self.assertTrue(self.data.exists())

    def test_missing_catalog_is_left_alone(self):
        self.assertFalse(self.db.exists())
        self.assertIsNone(self._run())
        self.assertTrue(self.data.exists())

    def test_empty_catalog_is_left_alone(self):
        self.db.write_bytes(b"")
        self.assertIsNone(self._run())
        self.assertTrue(self.data.exists())

    def test_unobtainable_master_key_never_touches_data(self):
        # an ENCRYPTED catalog + a Keychain that RAISES (transient lock): we must
        # NOT move data — the catalog may be perfectly fine under the real key.
        self._write_encrypted_catalog()
        def boom():
            raise RuntimeError("User interaction is not allowed")
        catalog.MASTER_KEY_PROVIDER = boom
        self.assertIsNone(self._run())
        self.assertTrue(self.data.exists())
        self.assertTrue(self.db.exists())
        self.assertEqual(self.detached, [])


class TestActsOnPoisonedState(RecoveryBase):
    def test_undecryptable_catalog_is_moved_aside(self):
        # encrypted-format bytes that will NOT open with KEY (the D-81 state)
        self.db.write_bytes(b"\xa4\xe2m|~J\xaf\xde\xe8(\xf9\xc0)S\x05=" +
                            b"\x00" * 4096)
        self.assertTrue(catalog.is_encrypted(self.db))
        (self.data / "documents").mkdir()
        (self.data / ".profile_photo").write_bytes(b"\x89PNG")

        aside = self._run()
        self.assertIsNotNone(aside)
        # original moved ASIDE, not deleted; nothing left at the live path
        self.assertFalse(self.data.exists())
        self.assertTrue(aside.exists())
        self.assertTrue((aside / ".kb_catalog.db").exists())
        self.assertTrue((aside / "documents").is_dir())
        self.assertIn("unreadable-20260710-153000", aside.name)

    def test_a_fresh_start_works_after_recovery(self):
        self.db.write_bytes(b"\xa4\xe2m|~J\xaf\xde" + b"\x00" * 2048)
        self._run()
        # the app path is clear -> a new encrypted catalog is created cleanly
        conn = catalog._connect(self.db)
        conn.close()
        self.assertTrue(self.db.exists())
        self.assertTrue(catalog.is_encrypted(self.db))


if __name__ == "__main__":
    unittest.main(verbosity=2)
