"""D-58 v1 — macOS launcher lifecycle (headless; no GUI).

Proves the launcher's server lifecycle without opening a window: an unused port reads free;
start_server -> health 200 -> stop_server releases the port; and free_port() actually kills
a stale listener (pre-kill on launch). The pywebview window itself is exercised manually
(`python desktop/launcher.py`) — these tests cover everything around it.
"""

import sys
import time
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "desktop"))
import launcher  # noqa: E402  (module under test)

PORT = 8771  # a high, unlikely-used port (NOT the app's 8000)


def _wait_released(port, timeout=10.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not launcher.port_in_use(port):
            return True
        time.sleep(0.2)
    return False


class TestLauncherLifecycle(unittest.TestCase):
    def test_unused_port_reads_free(self):
        self.assertFalse(launcher.port_in_use(PORT))
        self.assertEqual(launcher.listening_pids(PORT), [])
        self.assertEqual(launcher.free_port(PORT), 0)  # no-op when nothing is listening

    def test_start_health_stop_releases_port(self):
        proc = launcher.start_server(port=PORT)
        try:
            self.assertTrue(launcher.wait_healthy(port=PORT), "server never became healthy")
            self.assertTrue(launcher.port_in_use(PORT))
        finally:
            launcher.stop_server(proc)
        self.assertTrue(_wait_released(PORT), "port not released after stop_server")

    def test_free_port_kills_a_stale_listener(self):
        proc = launcher.start_server(port=PORT)
        try:
            self.assertTrue(launcher.wait_healthy(port=PORT))
            killed = launcher.free_port(PORT)              # pre-kill behavior
            self.assertGreaterEqual(killed, 1, "free_port did not signal the listener")
            self.assertTrue(_wait_released(PORT), "free_port left the port held")
        finally:
            launcher.stop_server(proc)


if __name__ == "__main__":
    unittest.main(verbosity=2)
