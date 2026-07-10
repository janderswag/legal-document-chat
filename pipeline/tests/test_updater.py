"""v0.3.0 in-place updater proofs: verify-BEFORE-swap ordering, the pinned
team id, rename-aside rollback, dev-checkout refusal, and the honest route
behavior. All subprocess/network seams are monkeypatched — no real DMG,
no codesign, no egress.
"""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

PIPELINE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPELINE_DIR))
import api  # noqa: E402
import updater  # noqa: E402
import updates  # noqa: E402

client = TestClient(api.app)


class TestBundleDetection(unittest.TestCase):
    def test_dev_checkout_refuses(self):
        # tests run from a venv python, never from inside an .app bundle
        self.assertIsNone(updater.app_bundle_path())
        updater._set("idle")
        updater.run_install()
        s = updater.status()
        self.assertEqual(s["state"], "error")
        self.assertIn("installed app", s["detail"])


class TestSwapRollback(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.current = self.tmp / "docuchat.app"
        (self.current / "Contents").mkdir(parents=True)
        (self.current / "Contents" / "version.txt").write_text("old")
        self.incoming = self.tmp / "mount" / "docuchat.app"
        (self.incoming / "Contents").mkdir(parents=True)
        (self.incoming / "Contents" / "version.txt").write_text("new")

    def test_swap_installs_and_removes_aside(self):
        self._orig = updater.subprocess.run

        def fake_run(cmd, **kw):
            if cmd[0] == "ditto":
                import shutil
                shutil.copytree(cmd[1], cmd[2])
                return subprocess.CompletedProcess(cmd, 0)
            return self._orig(cmd, **kw)
        updater.subprocess.run = fake_run
        try:
            updater._swap(self.current, self.incoming)
        finally:
            updater.subprocess.run = self._orig
        self.assertEqual((self.current / "Contents" / "version.txt").read_text(),
                         "new")
        self.assertFalse((self.tmp / "docuchat.app.replaced").exists())

    def test_failed_install_rolls_back_the_old_app(self):
        self._orig = updater.subprocess.run

        def fake_run(cmd, **kw):
            if cmd[0] == "ditto":
                raise subprocess.CalledProcessError(1, cmd, stderr=b"disk full")
            return self._orig(cmd, **kw)
        updater.subprocess.run = fake_run
        try:
            with self.assertRaises(subprocess.CalledProcessError):
                updater._swap(self.current, self.incoming)
        finally:
            updater.subprocess.run = self._orig
        # the ORIGINAL app is back in place, byte-identical
        self.assertEqual((self.current / "Contents" / "version.txt").read_text(),
                         "old")
        self.assertFalse((self.tmp / "docuchat.app.replaced").exists())


class TestVerifyBeforeSwap(unittest.TestCase):
    """A wrong team id must abort BEFORE any filesystem mutation."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.bundle = self.tmp / "docuchat.app"
        (self.bundle / "Contents").mkdir(parents=True)
        (self.bundle / "Contents" / "version.txt").write_text("old")
        self.calls = []
        self._patches = {
            "app_bundle_path": updater.app_bundle_path,
            "_release_dmg_asset": updater._release_dmg_asset,
            "_download": updater._download,
            "_mount": updater._mount,
            "_unmount": updater._unmount,
            "_codesign_team": updater._codesign_team,
            "_swap": updater._swap,
            "_relaunch": updater._relaunch,
        }
        mount = self.tmp / "mount"
        (mount / "evil.app").mkdir(parents=True)
        updater.app_bundle_path = lambda: self.bundle
        updater._release_dmg_asset = lambda: ("https://x/d.dmg", 0, "v9.9.9")
        updater._download = lambda url, dest, size: None
        updater._mount = lambda dmg: str(mount)
        updater._unmount = lambda mp: None
        updater._codesign_team = lambda app: "EVILTEAM99"
        updater._swap = lambda cur, inc: self.calls.append("swap")
        updater._relaunch = lambda app: self.calls.append("relaunch")

    def tearDown(self):
        for name, fn in self._patches.items():
            setattr(updater, name, fn)

    def test_team_mismatch_never_swaps(self):
        updater._set("idle")
        updater.run_install()
        s = updater.status()
        self.assertEqual(s["state"], "error")
        self.assertIn("EVILTEAM99", s["detail"])
        self.assertIn("untouched", s["detail"])
        self.assertEqual(self.calls, [])      # no swap, no relaunch
        self.assertEqual((self.bundle / "Contents" / "version.txt").read_text(),
                         "old")

    def test_pinned_team_installs_and_relaunches(self):
        updater._codesign_team = lambda app: updater.TEAM_ID
        updater._set("idle")
        updater.run_install()
        self.assertEqual(updater.status()["state"], "restarting")
        self.assertEqual(self.calls, ["swap", "relaunch"])


class TestInstallRoute(unittest.TestCase):
    def test_no_update_available_is_a_noop(self):
        orig = updates.status
        updates.status = lambda force=False: {"update_available": False}
        try:
            r = client.post("/updates/install")
        finally:
            updates.status = orig
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["state"], "idle")

    def test_install_status_route(self):
        updater._set("idle")
        r = client.get("/updates/install/status")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["state"], "idle")


if __name__ == "__main__":
    unittest.main(verbosity=2)
