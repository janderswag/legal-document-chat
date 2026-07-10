"""Keychain read-safety proofs (v0.3.0 post-mortem — the master-key overwrite).

The 2026-07-10 incident: keychain_secret() treated ANY failed read as "item
missing" and ran add-generic-password with -U, silently REPLACING the real
master key when the read failed for environmental reasons (locked keychain,
sandbox, denied ACL). That is irreversible loss of every DEK-wrapped secret.

These tests pin the corrected contract by scripting the ``security`` seam:
  1. a successful read returns the stored key and never writes
  2. an explicit "could not be found" creates ONCE, without -U
  3. any OTHER read failure raises and NEVER attempts a write
  4. a create race ("already exists") re-reads the winner's key
"""

import subprocess
import sys
import unittest
from pathlib import Path

PIPELINE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPELINE_DIR))
import keyvault  # noqa: E402

KEY = "ab" * 32


def scripted(responses):
    """Replace keyvault._security with a script: pops (rc, stdout, stderr) per
    call and records the raw command strings."""
    calls = []
    seq = list(responses)

    def fake(commands):
        calls.append(commands)
        rc, out, err = seq.pop(0)
        return subprocess.CompletedProcess(["security", "-i"], rc,
                                           stdout=out, stderr=err)
    return fake, calls


class TestKeychainReadSafety(unittest.TestCase):
    def setUp(self):
        self._orig = keyvault._security

    def tearDown(self):
        keyvault._security = self._orig

    def test_successful_read_never_writes(self):
        keyvault._security, calls = scripted([(0, KEY + "\n", "")])
        got = keyvault.keychain_secret("master-key-v1")
        self.assertEqual(got, bytes.fromhex(KEY))
        self.assertEqual(len(calls), 1)
        self.assertIn("find-generic-password", calls[0])

    def test_not_found_creates_without_update_flag(self):
        keyvault._security, calls = scripted([
            (44, "", "security: SecKeychainSearchCopyNext: The specified item "
                     "could not be found in the keychain."),
            (0, "", ""),
        ])
        got = keyvault.keychain_secret("master-key-v1")
        self.assertEqual(len(got), 32)
        self.assertEqual(len(calls), 2)
        self.assertIn("add-generic-password", calls[1])
        self.assertNotIn("-U", calls[1],
                         "-U turns a failed read into key destruction")

    def test_ambiguous_read_failure_raises_and_never_writes(self):
        for stderr in ("SecKeychainSearchCopyNext: User interaction is not allowed.",
                       "security: unable to open keychain",
                       ""):
            keyvault._security, calls = scripted([(1, "", stderr)])
            with self.assertRaises(RuntimeError) as ctx:
                keyvault.keychain_secret("master-key-v1")
            self.assertEqual(len(calls), 1,
                             f"a write was attempted after: {stderr!r}")
            self.assertIn("NOT creating", str(ctx.exception))

    def test_create_race_rereads_the_winner(self):
        keyvault._security, calls = scripted([
            (44, "", "The specified item could not be found in the keychain."),
            (45, "", "security: SecKeychainItemCreateFromContent: The specified "
                     "item already exists in the keychain."),
            (0, KEY + "\n", ""),
        ])
        got = keyvault.keychain_secret("master-key-v1")
        self.assertEqual(got, bytes.fromhex(KEY))
        self.assertEqual(len(calls), 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
