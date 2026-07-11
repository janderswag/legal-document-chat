"""D-58 v1 — macOS launcher lifecycle (headless; no GUI).

Proves the launcher's server lifecycle without opening a window: an unused port reads free;
start_server -> health 200 -> stop_server releases the port; free_port() kills a stale
listener (pre-kill on launch); and a SIGTERM to the launcher reaps its child uvicorn so a
hard kill cannot orphan the server on port 8000 (the D-59 yellow). The pywebview window
itself is exercised manually (`python desktop/launcher.py`).
"""

import signal
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
import os
import unittest
from pathlib import Path
from unittest import mock
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DESKTOP = REPO_ROOT / "desktop"
sys.path.insert(0, str(DESKTOP))
import launcher  # noqa: E402  (module under test)

PORT = 8771  # a high, unlikely-used port (NOT the app's 8000)
PORT2 = 8772  # a second port for the signal-cleanup driver
PORT3 = 8773  # a third port for the frozen in-process server


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


class TestEnsureOllama(unittest.TestCase):
    """P0.2 — the launcher starts a managed ``ollama serve`` (flash-attention + keep_alive
    env, loopback-forced) ONLY when nothing is on the Ollama port and the binary exists."""

    def test_noop_when_ollama_already_running(self):
        # A user's own Ollama must never be touched (we can't set env on it anyway).
        with patch.object(launcher, "port_in_use", return_value=True), \
             patch.object(launcher.subprocess, "Popen") as popen:
            self.assertIsNone(launcher.ensure_ollama())
            popen.assert_not_called()

    def test_noop_when_binary_missing(self):
        with patch.object(launcher, "port_in_use", return_value=False), \
             patch.object(launcher, "find_ollama", return_value=None), \
             patch.object(launcher.subprocess, "Popen") as popen:
            self.assertIsNone(launcher.ensure_ollama())
            popen.assert_not_called()

    def test_spawns_with_speed_env_and_loopback_bind(self):
        calls = {}
        def fake_popen(cmd, **kwargs):
            calls["cmd"], calls["kwargs"] = cmd, kwargs
            return "PROC"
        # port free at spawn, then "up" so the readiness poll returns immediately
        port_states = iter([False, True])
        with patch.object(launcher, "port_in_use",
                          side_effect=lambda *a, **k: next(port_states, True)), \
             patch.object(launcher, "find_ollama", return_value="/fake/ollama"), \
             patch.object(launcher, "ollama_version", return_value=(0, 18, 0)), \
             patch.object(launcher.subprocess, "Popen", side_effect=fake_popen):
            self.assertEqual(launcher.ensure_ollama(), "PROC")
        self.assertEqual(calls["cmd"], ["/fake/ollama", "serve"])
        env = calls["kwargs"]["env"]
        self.assertEqual(env["OLLAMA_FLASH_ATTENTION"], "1")
        self.assertEqual(env["OLLAMA_KEEP_ALIVE"], launcher.OLLAMA_ENV["OLLAMA_KEEP_ALIVE"])
        self.assertEqual(env["OLLAMA_HOST"], "127.0.0.1:11434")  # loopback only, forced

    def test_stop_server_none_is_safe(self):
        launcher.stop_server(None)  # ensure_ollama() may return None — cleanup must accept it


class TestFrozenInProcessServer(unittest.TestCase):
    def test_inprocess_server_serves_health_and_stops(self):
        # P2.7: a PyInstaller-frozen app must NOT spawn `sys.executable -m uvicorn`
        # (that relaunches the app binary itself). The frozen path runs uvicorn
        # in-process; prove it serves /health and stops on should_exit.
        server = launcher.start_server_frozen(port=PORT3)
        try:
            self.assertTrue(launcher.wait_healthy(port=PORT3, timeout=30),
                            "in-process server never became healthy")
        finally:
            server.should_exit = True
        self.assertTrue(_wait_released(PORT3), "in-process server did not stop")


# A standalone launcher driver: starts the server, installs the signal cleanup, reports
# READY, then idles — exactly what main() does around the (GUI-only) window.
_DRIVER = textwrap.dedent("""
    import sys, time
    sys.path.insert(0, {desktop!r})
    import launcher
    proc = launcher.start_server(port={port})
    launcher.install_cleanup(proc)
    if not launcher.wait_healthy(port={port}, timeout=40):
        launcher.stop_server(proc); sys.exit(3)
    print("READY", flush=True)
    while True:
        time.sleep(0.3)
""")


class TestLauncherSignalCleanup(unittest.TestCase):
    def test_sigterm_reaps_child_no_orphan(self):
        # The launcher's child is in its own session (start_new_session); only the
        # install_cleanup SIGTERM handler reaps it. If the handler is missing/broken, the
        # grandchild uvicorn is orphaned and the port stays held -> this test fails.
        src = _DRIVER.format(desktop=str(DESKTOP), port=PORT2)
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
            f.write(src)
            driver_path = f.name
        drv = subprocess.Popen([sys.executable, driver_path],
                               stdout=subprocess.PIPE, text=True)
        try:
            line = drv.stdout.readline().strip()  # blocks until READY (or EOF on failure)
            self.assertEqual(line, "READY", "driver did not bring the server up")
            self.assertTrue(launcher.port_in_use(PORT2))

            drv.send_signal(signal.SIGTERM)       # hard-kill the launcher driver
            drv.wait(timeout=20)
            self.assertTrue(_wait_released(PORT2, timeout=15),
                            "SIGTERM orphaned the child uvicorn (port still held)")
        finally:
            if drv.poll() is None:
                drv.kill()
            if drv.stdout:
                drv.stdout.close()
            launcher.free_port(PORT2)             # belt-and-suspenders
            try:
                os.unlink(driver_path)
            except OSError:
                pass


class TestWindowFirstLaunch(unittest.TestCase):
    """UX-10: the splash window appears before the engine exists; cleanup handlers
    installed BEFORE the children spawn still reap children created later."""

    def test_splash_and_fail_pages_are_inline(self):
        # no server, no assets — pure inline HTML the window can show instantly
        self.assertIn("docuchat", launcher.SPLASH_HTML)
        self.assertIn("Starting the local engine", launcher.SPLASH_HTML)
        self.assertNotIn("http", launcher.SPLASH_HTML.lower())
        self.assertIn("could not start", launcher.FAIL_HTML)

    def test_install_cleanup_live_reaps_children_created_after_registration(self):
        import types
        handles = {"proc": None, "ollama": None, "server": None}
        stopped = []
        captured = {}
        orig_signal, orig_stop, orig_kill = signal.signal, launcher.stop_server, os.kill
        try:
            signal.signal = lambda s, h: captured.setdefault(s, h)
            launcher.stop_server = lambda p, timeout=8.0: stopped.append(p)
            handler = launcher.install_cleanup_live(handles)
            # children arrive AFTER the handlers were installed (the whole point)
            late_child = types.SimpleNamespace(poll=lambda: 0)   # a dead-safe fake Popen
            fake_server = types.SimpleNamespace(should_exit=False)
            handles["proc"] = late_child
            handles["server"] = fake_server
            os.kill = lambda pid, sig: None                      # swallow the re-raise
            handler(signal.SIGTERM, None)
            self.assertIn(late_child, stopped, "late child not reaped at fire time")
            self.assertTrue(fake_server.should_exit, "in-process server not stopped")
        finally:
            signal.signal, launcher.stop_server, os.kill = orig_signal, orig_stop, orig_kill


class _FakeWindow:
    def __init__(self):
        self.destroyed = False

    def destroy(self):
        self.destroyed = True


class TestRestartMarkerWatch(unittest.TestCase):
    """The launcher-owned relaunch (fixes the stuck-on-"Restarting…" bug): a
    background thread notices updater.py's restart marker and drives the actual
    relaunch + window teardown, since only the main thread's window.destroy() can
    safely unblock webview.start() — a raw SIGTERM to the shared in-process server
    can sit pending forever while the main thread is in the native GUI loop."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.marker = self.tmp / ".update-restart"
        self._orig_env = os.environ.get("DOCUCHAT_DATA_DIR")
        os.environ["DOCUCHAT_DATA_DIR"] = str(self.tmp)

    def tearDown(self):
        if self._orig_env is None:
            os.environ.pop("DOCUCHAT_DATA_DIR", None)
        else:
            os.environ["DOCUCHAT_DATA_DIR"] = self._orig_env

    def test_marker_path_respects_data_dir_override(self):
        self.assertEqual(launcher._restart_marker_path(), self.marker)

    def test_marker_present_spawns_relauncher_deletes_marker_destroys_window(self):
        app_path = self.tmp / "docuchat.app"
        self.marker.write_text(str(app_path))
        window = _FakeWindow()
        with patch.object(launcher.subprocess, "Popen") as popen:
            launcher._watch_restart_marker(window, poll=0.01)
        self.assertFalse(self.marker.exists(), "marker not consumed")
        self.assertTrue(window.destroyed, "window.destroy() not called")
        cmd = popen.call_args[0][0]
        self.assertIn(str(app_path), cmd[-1])
        self.assertIn("open", cmd[-1])
        # relaunch must wait for OUR pid to actually exit (kill -0 poll loop), not a
        # fixed sleep — a fixed sleep can't bound stop_server()'s up-to-~16s teardown,
        # so `open` could fire while the old process is still alive (macOS then just
        # re-activates it instead of relaunching).
        self.assertIn(f"kill -0 {os.getpid()}", cmd[-1])
        self.assertNotRegex(cmd[-1], r"sleep 2;\s*open")

    def test_no_marker_is_a_noop_a_crash_must_not_relaunch_loop(self):
        app_path = self.tmp / "docuchat.app"
        window = _FakeWindow()
        with patch.object(launcher.subprocess, "Popen"):
            t = threading.Thread(target=launcher._watch_restart_marker,
                                 args=(window,), kwargs={"poll": 0.02}, daemon=True)
            t.start()
            time.sleep(0.1)
            self.assertFalse(window.destroyed, "watcher fired with no marker present")
            self.marker.write_text(str(app_path))   # only an explicit marker (a
            t.join(timeout=5)                        # user-clicked update) is consent
            self.assertTrue(window.destroyed)
        self.assertFalse(self.marker.exists())


class TestRamGate(unittest.TestCase):
    """Adoption council: an 8GB Mac degrades mysteriously (Ollama swap-thrash);
    the launcher must refuse WITH AN EXPLANATION instead. Fails OPEN: if RAM
    cannot be read, the gate never blocks."""

    def test_threshold_logic(self):
        with mock.patch.object(launcher, "total_ram_bytes", return_value=8 * 1024**3):
            self.assertFalse(launcher.ram_ok())
        with mock.patch.object(launcher, "total_ram_bytes", return_value=16 * 1024**3):
            self.assertTrue(launcher.ram_ok())

    def test_detection_failure_fails_open(self):
        with mock.patch.object(launcher, "total_ram_bytes", return_value=0):
            self.assertTrue(launcher.ram_ok())

    def test_escape_hatch(self):
        with mock.patch.object(launcher, "total_ram_bytes", return_value=8 * 1024**3), \
             mock.patch.dict(launcher.os.environ, {"DOCUCHAT_SKIP_RAM_GATE": "1"}):
            self.assertTrue(launcher.ram_ok())

    def test_lowram_html_explains_and_names_the_requirement(self):
        self.assertIn("16 GB", launcher.LOWRAM_HTML)
        self.assertIn("on this Mac", launcher.LOWRAM_HTML)   # local-model framing

    def test_gate_is_wired_into_main_before_any_engine_start(self):
        """Deleting the gate block from main() must fail THIS test: on a
        low-RAM machine main() shows the explanation window and returns
        without ever starting Ollama or the server, and the rendered HTML
        carries the real GB count (placeholder substituted)."""
        shown = {}

        class _FakeWebview:
            def create_window(self, title, html=None, **kw):
                shown["html"] = html

            def start(self):
                shown["started"] = True

        with mock.patch.object(launcher, "total_ram_bytes",
                               return_value=8 * 1024**3), \
             mock.patch.object(launcher, "install_cleanup_live"), \
             mock.patch.object(launcher, "ensure_ollama") as ollama, \
             mock.patch.object(launcher, "start_server") as server, \
             mock.patch.object(launcher, "free_port") as freep, \
             mock.patch.dict(sys.modules, {"webview": _FakeWebview()}), \
             mock.patch.dict(launcher.os.environ, {}, clear=False):
            launcher.os.environ.pop("DOCUCHAT_SKIP_RAM_GATE", None)
            launcher.os.environ.pop("DOCUCHAT_SMOKE", None)
            rc = launcher.main(port=PORT3)
        self.assertEqual(rc, 0)
        self.assertTrue(shown.get("started"), "low-RAM window never shown")
        self.assertIn("8 GB", shown["html"])
        self.assertNotIn("{ram_gb}", shown["html"])
        ollama.assert_not_called()
        server.assert_not_called()
        freep.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
