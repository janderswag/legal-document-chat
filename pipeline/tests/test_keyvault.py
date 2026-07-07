"""Encryption cycle (D-73, design §3) — key envelope: master key in the macOS
Keychain, per-matter DEKs wrapped AES-256-GCM, file-layer encrypt/decrypt for the
natives tree, and the catalog matter_keys rows the crypto-shred will destroy.

Crypto tests use explicit in-memory master keys (never the real Keychain). The one
Keychain roundtrip test uses a dedicated throwaway service name, deletes it after,
and skips off-macOS."""

import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PIPELINE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPELINE_DIR))
import catalog  # noqa: E402
import keyvault  # noqa: E402


class TestDekEnvelope(unittest.TestCase):
    def setUp(self):
        self.master = keyvault.new_dek()  # any 32 random bytes works as a master

    def test_new_dek_is_32_random_bytes(self):
        a, b = keyvault.new_dek(), keyvault.new_dek()
        self.assertEqual(len(a), 32)
        self.assertNotEqual(a, b)

    def test_wrap_unwrap_roundtrip(self):
        dek = keyvault.new_dek()
        wrapped = keyvault.wrap_dek(dek, self.master)
        self.assertNotIn(dek, wrapped)  # wrapped blob never contains the plaintext key
        self.assertEqual(keyvault.unwrap_dek(wrapped, self.master), dek)

    def test_unwrap_with_wrong_master_fails(self):
        wrapped = keyvault.wrap_dek(keyvault.new_dek(), self.master)
        with self.assertRaises(Exception):
            keyvault.unwrap_dek(wrapped, keyvault.new_dek())

    def test_unwrap_tampered_blob_fails(self):
        wrapped = bytearray(keyvault.wrap_dek(keyvault.new_dek(), self.master))
        wrapped[-1] ^= 0x01
        with self.assertRaises(Exception):
            keyvault.unwrap_dek(bytes(wrapped), self.master)

    def test_wrap_is_nondeterministic(self):
        dek = keyvault.new_dek()
        self.assertNotEqual(keyvault.wrap_dek(dek, self.master),
                            keyvault.wrap_dek(dek, self.master))


class TestFileEncryption(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.dek = keyvault.new_dek()

    def test_encrypt_decrypt_roundtrip(self):
        src = self.dir / "brief.pdf"
        payload = b"%PDF-1.7 synthetic native document body " * 1000
        src.write_bytes(payload)
        enc = self.dir / "brief.pdf.enc"
        keyvault.encrypt_file(src, enc, self.dek)
        raw = enc.read_bytes()
        self.assertTrue(raw.startswith(keyvault.MAGIC))
        self.assertNotIn(b"synthetic native", raw)  # ciphertext, not plaintext
        out = self.dir / "brief.roundtrip.pdf"
        keyvault.decrypt_file(enc, out, self.dek)
        self.assertEqual(out.read_bytes(), payload)

    def test_decrypt_with_wrong_dek_fails_and_writes_nothing(self):
        src = self.dir / "a.txt"
        src.write_bytes(b"attorney work product")
        enc = self.dir / "a.enc"
        keyvault.encrypt_file(src, enc, self.dek)
        out = self.dir / "a.out"
        with self.assertRaises(Exception):
            keyvault.decrypt_file(enc, out, keyvault.new_dek())
        self.assertFalse(out.exists())  # no partial plaintext left behind

    def test_decrypt_rejects_non_encrypted_file(self):
        plain = self.dir / "plain.txt"
        plain.write_bytes(b"not encrypted")
        with self.assertRaises(ValueError):
            keyvault.decrypt_file(plain, self.dir / "x", self.dek)


class TestMatterKeysCatalog(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.db = self.dir / "catalog.db"
        catalog.create_matter("Acme v. Bolt", db_path=self.db)
        self.master = keyvault.new_dek()

    def test_ensure_creates_wraps_and_returns_same_dek(self):
        d1 = keyvault.ensure_matter_dek("acme-v-bolt", self.master, db_path=self.db)
        d2 = keyvault.ensure_matter_dek("acme-v-bolt", self.master, db_path=self.db)
        self.assertEqual(len(d1), 32)
        self.assertEqual(d1, d2)  # stable across calls (unwraps the stored blob)

    def test_dek_stored_only_wrapped(self):
        dek = keyvault.ensure_matter_dek("acme-v-bolt", self.master, db_path=self.db)
        row = sqlite3.connect(str(self.db)).execute(
            "SELECT wrapped_dek FROM matter_keys WHERE matter_slug='acme-v-bolt'"
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertNotIn(dek, row[0])  # plaintext DEK never hits disk

    def test_destroy_matter_dek_is_unrecoverable(self):
        keyvault.ensure_matter_dek("acme-v-bolt", self.master, db_path=self.db)
        self.assertTrue(keyvault.destroy_matter_dek("acme-v-bolt", db_path=self.db))
        row = sqlite3.connect(str(self.db)).execute(
            "SELECT wrapped_dek, destroyed FROM matter_keys WHERE matter_slug='acme-v-bolt'"
        ).fetchone()
        self.assertIsNone(row[0])       # wrapped blob gone, not just flagged
        self.assertIsNotNone(row[1])    # destruction timestamped (certificate input)
        with self.assertRaises(keyvault.KeyDestroyedError):
            keyvault.ensure_matter_dek("acme-v-bolt", self.master, db_path=self.db)

    def test_destroy_missing_key_returns_false(self):
        self.assertFalse(keyvault.destroy_matter_dek("no-such", db_path=self.db))


@unittest.skipUnless(shutil.which("security"), "macOS security CLI required")
class TestKeychainMasterKey(unittest.TestCase):
    SERVICE = "docuchat-kb-test-throwaway"

    def tearDown(self):
        subprocess.run(["security", "delete-generic-password", "-s", self.SERVICE],
                       capture_output=True)

    def test_master_key_created_then_stable(self):
        k1 = keyvault.master_key(service=self.SERVICE)
        k2 = keyvault.master_key(service=self.SERVICE)
        self.assertEqual(len(k1), 32)
        self.assertEqual(k1, k2)  # second call reads the stored key, not a new one


if __name__ == "__main__":
    unittest.main()
