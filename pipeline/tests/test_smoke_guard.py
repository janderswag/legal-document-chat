"""Sprint 1 review fix — smoke-mode safety guards.

DOCUCHAT_SMOKE=1 is meant to be driven ONLY by desktop/smoke_packaged.sh, which always
sets DOCUCHAT_DATA_DIR and DOCUCHAT_PORT alongside it. These tests prove the defense in
depth for when that assumption doesn't hold:
  - launcher._require_smoke_env(): DOCUCHAT_SMOKE=1 alone (no scratch dir/port) must
    refuse to proceed, not silently default onto the owner's real app/data on port 8000
    where free_port() would kill their running app.
  - catalog._encrypt_new() / encvol.mount_kb_volume(): even if DOCUCHAT_DATA_DIR is
    overridden so the scratch dir sits at the production catalog path, smoke mode must
    never touch the real production Keychain master/volume key.
"""

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DESKTOP = REPO_ROOT / "desktop"
PIPELINE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(DESKTOP))
sys.path.insert(0, str(PIPELINE_DIR))
import launcher  # noqa: E402  (module under test)
import catalog  # noqa: E402
import encvol  # noqa: E402


class TestSmokeEnvGuard(unittest.TestCase):
    def test_missing_both_env_vars_exits(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("DOCUCHAT_DATA_DIR", None)
            os.environ.pop("DOCUCHAT_PORT", None)
            with self.assertRaises(SystemExit) as ctx:
                launcher._require_smoke_env()
            self.assertEqual(ctx.exception.code, 2)

    def test_missing_one_env_var_exits(self):
        with patch.dict(os.environ, {"DOCUCHAT_DATA_DIR": "/tmp/whatever"}, clear=False):
            os.environ.pop("DOCUCHAT_PORT", None)
            with self.assertRaises(SystemExit) as ctx:
                launcher._require_smoke_env()
            self.assertEqual(ctx.exception.code, 2)

    def test_both_env_vars_set_proceeds(self):
        with patch.dict(os.environ, {"DOCUCHAT_DATA_DIR": "/tmp/whatever",
                                     "DOCUCHAT_PORT": "18731"}, clear=False):
            launcher._require_smoke_env()  # must not raise


class TestSmokeNeverUsesProductionKey(unittest.TestCase):
    def test_encrypt_new_refuses_under_smoke_even_at_production_path(self):
        with patch("sys.platform", "darwin"), \
             patch.dict(os.environ, {"DOCUCHAT_SMOKE": "1"}, clear=False):
            self.assertFalse(catalog._encrypt_new(catalog._PRODUCTION_DB))

    def test_mount_kb_volume_skips_under_smoke(self):
        with patch.dict(os.environ, {"DOCUCHAT_SMOKE": "1"}, clear=False), \
             patch.object(encvol, "volume_passphrase",
                          side_effect=AssertionError("must not touch the Keychain")), \
             patch.object(encvol, "create_volume",
                          side_effect=AssertionError("must not create a volume")), \
             patch.object(encvol, "mount",
                          side_effect=AssertionError("must not mount a volume")):
            self.assertEqual(encvol.mount_kb_volume("/tmp/whatever/.kb_catalog.db"),
                             "no-encrypted-volume")


if __name__ == "__main__":
    unittest.main(verbosity=2)
