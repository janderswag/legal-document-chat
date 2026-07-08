"""Encryption cycle (D-73) — encrypted KB volume lifecycle + the store-migration
drill: create/mount/eject roundtrip, migration verified row-for-row with the plain
store kept aside, rehearsal touches nothing, and a sabotaged verification aborts
before any swap. hdiutil is real (darwin-gated); stores are tiny scratch LanceDB
tables (4-dim vectors, no Ollama); passphrases are throwaway — never the Keychain."""

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

PIPELINE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPELINE_DIR))
import encvol  # noqa: E402
import migrate_store_encvol as mig  # noqa: E402

darwin_only = unittest.skipUnless(sys.platform == "darwin", "hdiutil is macOS-only")


def _tiny_store(path):
    import lancedb
    db = lancedb.connect(str(path))
    rows = [{"vector": [float(i)] * 4, "source_filename": f"doc{i}.pdf",
             "matter": "acme-v-bolt", "page_number": i, "char_start": 0,
             "char_end": 10, "text": f"chunk {i}"} for i in range(6)]
    db.create_table("chunks", data=rows)


@darwin_only
class TestVolumeLifecycle(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.bundle = self.dir / "test.sparsebundle"
        self.mnt = self.dir / "mnt"
        self.addCleanup(encvol.eject, self.mnt)
        self.passphrase = "test-passphrase-not-a-secret"

    def test_create_mount_write_eject_roundtrip(self):
        encvol.create_volume(self.bundle, self.passphrase, size="64m")
        self.assertTrue(encvol.mount(self.bundle, self.mnt, self.passphrase))
        self.assertTrue(encvol.is_mounted(self.mnt))
        (self.mnt / "probe.txt").write_text("inside the volume")
        self.assertFalse(encvol.mount(self.bundle, self.mnt, self.passphrase))  # idempotent
        self.assertTrue(encvol.eject(self.mnt))
        self.assertFalse(encvol.is_mounted(self.mnt))
        # content persists across remount
        encvol.mount(self.bundle, self.mnt, self.passphrase)
        self.assertEqual((self.mnt / "probe.txt").read_text(), "inside the volume")

    def test_wrong_passphrase_fails(self):
        encvol.create_volume(self.bundle, self.passphrase, size="64m")
        with self.assertRaises(RuntimeError):
            encvol.mount(self.bundle, self.mnt, "wrong-passphrase")
        self.assertFalse(encvol.is_mounted(self.mnt))

    def test_mount_kb_volume_with_existing_plain_store_is_noop(self):
        # a pre-existing plain store is never silently swallowed into a new volume
        self.mnt.mkdir()
        self.assertEqual(encvol.mount_kb_volume(self.mnt, bundle=self.dir / "nope.sparsebundle"),
                         "no-encrypted-volume")

    def test_mount_kb_volume_fresh_install_creates_encrypted_volume(self):
        # no bundle AND no store yet = fresh install -> volume created + mounted
        status = encvol.mount_kb_volume(self.mnt, bundle=self.bundle,
                                        passphrase=self.passphrase)
        self.assertEqual(status, "mounted")
        self.assertTrue(self.bundle.exists())
        self.assertTrue(encvol.is_mounted(self.mnt))


@darwin_only
class TestStoreMigrationDrill(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.store = self.dir / ".lancedb_kb"
        _tiny_store(self.store)
        self.bundle = self.dir / "kb.sparsebundle"
        self.passphrase = "drill-passphrase-not-a-secret"
        self.addCleanup(encvol.eject, self.store)

    def test_drill_migrate_mounts_verified_store_and_keeps_aside(self):
        before = mig._dump_store(self.store)
        report = mig.migrate(store_dir=self.store, bundle=self.bundle,
                             passphrase=self.passphrase)
        self.assertTrue(report["verified"])
        self.assertTrue(encvol.is_mounted(self.store))       # store path IS the volume
        self.assertEqual(mig._dump_store(self.store), before)  # same data, same path
        aside = Path(report["aside"])
        self.assertTrue(aside.is_dir())
        self.assertEqual(mig._dump_store(aside), before)     # plain aside intact
        # second run: already migrated, refuses to redo
        self.assertTrue(mig.migrate(store_dir=self.store, bundle=self.bundle,
                                    passphrase=self.passphrase)["already_migrated"])

    def test_drill_rehearse_touches_nothing(self):
        before = mig._dump_store(self.store)
        report = mig.migrate(store_dir=self.store, bundle=self.bundle,
                             passphrase=self.passphrase, rehearse=True)
        self.assertTrue(report["verified"])
        self.assertTrue(report["rehearsal"])
        self.assertFalse(self.bundle.exists())               # no bundle installed
        self.assertFalse(encvol.is_mounted(self.store))
        self.assertEqual(mig._dump_store(self.store), before)

    def test_drill_sabotaged_verification_aborts_before_swap(self):
        real = mig._dump_store
        calls = {"n": 0}

        def sabotage(path):
            calls["n"] += 1
            return real(path) if calls["n"] == 1 else {"chunks": (0, [])}
        mig._dump_store = sabotage
        self.addCleanup(setattr, mig, "_dump_store", real)
        with self.assertRaises(mig.StoreVerificationError):
            mig.migrate(store_dir=self.store, bundle=self.bundle,
                        passphrase=self.passphrase)
        mig._dump_store = real
        self.assertFalse(encvol.is_mounted(self.store))      # no swap happened
        self.assertTrue(self.store.is_dir())
        self.assertEqual(len(mig._dump_store(self.store)["chunks"][1]), 6)  # intact
        self.assertFalse(self.bundle.exists())               # no half-built bundle left


if __name__ == "__main__":
    unittest.main()
