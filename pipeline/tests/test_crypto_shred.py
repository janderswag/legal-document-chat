"""Encryption cycle (D-73) — crypto-shred at disposition and the earned-Purge
certificate: an all-encrypted matter's disposal destroys its DEK (own audit event),
certifies originals as Purge with derived data honestly at Clear, and provably
leaves surviving ciphertext copies irrecoverable. A plain-era or mixed matter never
earns Purge. Injected master key; temp stores only."""

import sys
import tempfile
import unittest
from pathlib import Path

PIPELINE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPELINE_DIR))
import catalog  # noqa: E402
import keyvault  # noqa: E402
import retention  # noqa: E402

PURGE = "Purge (cryptographic erase"


class _ShredBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._cat, catalog.DEFAULT_DB = catalog.DEFAULT_DB, self.tmp / "cat.db"
        self._master = keyvault.new_dek()
        catalog.MASTER_KEY_PROVIDER = lambda: self._master
        keyvault.NATIVES_ENCRYPTION = True
        self.kb_docs = self.tmp / "kb"
        self.kb_db = self.tmp / ".lancedb_kb"   # no store -> store_state 'no-store'
        self.m = catalog.create_matter("Shred Matter")
        self.slug = self.m["slug"]

    def tearDown(self):
        catalog.DEFAULT_DB = self._cat
        catalog.MASTER_KEY_PROVIDER = None
        keyvault.NATIVES_ENCRYPTION = None

    def _plant(self, name, body, encrypted=True):
        keyvault.NATIVES_ENCRYPTION = encrypted
        d = self.kb_docs / self.slug
        d.mkdir(parents=True, exist_ok=True)
        p = d / name
        import hashlib
        keyvault.write_matter_file(p, body, self.slug)
        catalog.add_document(self.slug, p, status="ready",
                             checksum=hashlib.sha256(body).hexdigest(),
                             size_bytes=len(body))
        keyvault.NATIVES_ENCRYPTION = True
        return p


class TestEarnedPurge(_ShredBase):
    def test_all_encrypted_matter_disposes_as_purge_with_shred(self):
        self._plant("a.txt", b"SYNTHETIC alpha native.")
        p = self._plant("b.txt", b"SYNTHETIC beta native.")
        survivor = p.read_bytes()  # simulate a copy that outlives disposal (backup)

        cert = retention.dispose_matter(self.slug, self.kb_db, self.kb_docs)
        self.assertTrue(cert["crypto_shred"])
        self.assertIn(PURGE, cert["methods"]["original documents"])
        self.assertIn(PURGE, cert["method"])
        # derived data is NEVER claimed as Purge
        self.assertNotIn(PURGE, cert["methods"]["derived index data"])
        self.assertIn("Clear", cert["methods"]["derived index data"])
        # the DEK is gone for good: the surviving ciphertext copy is irrecoverable
        copy = self.tmp / "backup_copy.txt"
        copy.write_bytes(survivor)
        with self.assertRaises(keyvault.KeyDestroyedError):
            keyvault.read_matter_file(copy, self.slug)
        # shred is its own tamper-evident audit event, and the chain still verifies
        events = [e["event"] for e in catalog.audit_entries(self.slug)]
        self.assertIn("crypto-shred", events)
        self.assertIn("disposition", events)
        ok, _ = catalog.verify_audit_chain()
        self.assertTrue(ok)

    def test_plain_era_matter_stays_clear_no_purge_anywhere(self):
        self._plant("old.txt", b"SYNTHETIC plain-era native.", encrypted=False)
        cert = retention.dispose_matter(self.slug, self.kb_db, self.kb_docs)
        self.assertFalse(cert["crypto_shred"])  # no DEK ever existed
        # Purge is claimed nowhere (the caveat may MENTION it to say it doesn't apply)
        self.assertNotIn(PURGE, cert["method"])
        self.assertNotIn(PURGE, cert["methods"]["original documents"])
        self.assertNotIn(PURGE, cert["methods"]["derived index data"])
        self.assertIn("was not the case here", " ".join(cert["caveats"]))

    def test_mixed_matter_never_earns_blanket_purge(self):
        self._plant("sealed.txt", b"SYNTHETIC encrypted native.")
        self._plant("legacy.txt", b"SYNTHETIC plain native.", encrypted=False)
        cert = retention.dispose_matter(self.slug, self.kb_db, self.kb_docs)
        # the DEK existed and is destroyed (defense in depth), but Purge is NOT claimed
        self.assertTrue(cert["crypto_shred"])
        self.assertNotIn(PURGE, cert["methods"]["original documents"])
        self.assertNotIn(PURGE, cert["method"])

    def test_empty_matter_does_not_claim_purge(self):
        cert = retention.dispose_matter(self.slug, self.kb_db, self.kb_docs)
        self.assertNotIn(PURGE, cert["method"])


if __name__ == "__main__":
    unittest.main()
