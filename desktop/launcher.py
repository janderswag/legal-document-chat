"""Desktop launcher (D-58 v1, Phase A; D-61 cross-platform) — open docuchat in a native window.

Wraps the EXISTING FastAPI app (pipeline/api.py) — it does not touch the pipeline or the
citation verifier. It:
  1. pre-kills anything stuck on the port (so a stale server can't block launch),
  2. starts the FastAPI server as a CHILD process (handle held for clean shutdown),
  3. health-checks 127.0.0.1:8000,
  4. opens the first-run wizard (/setup, which drops into /app when ready) in a pywebview
     window,
  5. kills the child server on quit — whether the window is closed, the process exits
     normally, OR the launcher is hard-killed (no orphaned uvicorn).

Cross-platform process handling (D-61): POSIX uses sessions + signals (start_new_session,
SIGTERM/SIGKILL, killpg); Windows — which has no POSIX signals or process groups — uses a new
process group (CREATE_NEW_PROCESS_GROUP) and ``taskkill /T`` to reap the child tree. The Windows
branch is exercised on the owner's Windows box (see desktop/WINDOWS_TEST.md); it is unit-selected
here under a mocked ``os.name == 'nt'``.

Loopback-only (the server binds 127.0.0.1, never 0.0.0.0); no telemetry; no auto-update.
Run locally:  python desktop/launcher.py
The pywebview import is deferred into main() so the helpers are importable/testable headless.
"""

import atexit
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

HOST = "127.0.0.1"          # loopback only — never 0.0.0.0
DEFAULT_PORT = 8000
PIPELINE_DIR = Path(__file__).resolve().parent.parent / "pipeline"

# Windows-only Popen flag (absent on POSIX); 0 is a no-op elsewhere.
_CREATE_NEW_PROCESS_GROUP = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)


def _is_windows():
    """True on Windows (``os.name == 'nt'``). Read at call time so it can be mocked/tested."""
    return os.name == "nt"


def port_in_use(port, host=HOST):
    """True if something is accepting connections on host:port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.3)
        return s.connect_ex((host, port)) == 0


def _listening_pids_windows(port):
    """PIDs LISTENing on ``port`` parsed from ``netstat -ano`` (Windows)."""
    try:
        out = subprocess.run(["netstat", "-ano", "-p", "tcp"],
                             capture_output=True, text=True, timeout=5)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    pids = set()
    for line in out.stdout.splitlines():
        parts = line.split()
        # proto  local-addr  foreign-addr  STATE  PID
        if len(parts) >= 5 and parts[3] == "LISTENING" \
                and parts[1].rsplit(":", 1)[-1] == str(port) and parts[-1].isdigit():
            pids.add(int(parts[-1]))
    return list(pids)


def listening_pids(port):
    """PIDs LISTENing on ``port``. Empty if none / the lookup tool is unavailable."""
    if _is_windows():
        return _listening_pids_windows(port)
    try:
        out = subprocess.run(["lsof", "-ti", f"tcp:{port}", "-sTCP:LISTEN"],
                             capture_output=True, text=True, timeout=5)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    return [int(p) for p in out.stdout.split() if p.strip().isdigit()]


def _kill_pid(pid, hard=False):
    """Signal a single process by PID, cross-platform.

    POSIX: ``SIGKILL`` if ``hard`` else ``SIGTERM``.
    Windows: ``taskkill /T`` (whole tree), adding ``/F`` when ``hard`` (no POSIX signals exist)."""
    if _is_windows():
        cmd = ["taskkill", "/PID", str(pid), "/T"]
        if hard:
            cmd.append("/F")
        try:
            subprocess.run(cmd, capture_output=True, timeout=5)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        return
    try:
        os.kill(pid, signal.SIGKILL if hard else signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        pass


def free_port(port):
    """Pre-kill any process LISTENing on ``port`` (graceful, then hard stragglers) so a stale
    server can't block launch. Returns the number of processes initially signaled."""
    pids = listening_pids(port)
    for pid in pids:
        _kill_pid(pid, hard=False)
    if pids:
        for _ in range(20):
            if not listening_pids(port):
                break
            time.sleep(0.1)
        for pid in listening_pids(port):
            _kill_pid(pid, hard=True)
    return len(pids)


def start_server(host=HOST, port=DEFAULT_PORT):
    """Start the FastAPI app as a child uvicorn process (loopback only); return the Popen.
    The caller MUST stop_server() it on exit (handle held — no orphaned server).

    The child runs in its OWN process group/session so (a) a terminal Ctrl-C aimed at the
    launcher's group doesn't race-kill the child before our handler runs, and (b) stop_server()
    can reap the whole group (uvicorn + any workers). POSIX uses ``start_new_session``; Windows
    uses ``CREATE_NEW_PROCESS_GROUP``."""
    kwargs = {}
    if _is_windows():
        kwargs["creationflags"] = _CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    return subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "api:app",
         "--host", host, "--port", str(port), "--log-level", "warning"],
        cwd=str(PIPELINE_DIR),
        **kwargs,
    )


def wait_healthy(port=DEFAULT_PORT, host=HOST, timeout=40.0):
    """Poll GET /health until 200 (True) or ``timeout`` (False)."""
    url = f"http://{host}:{port}/health"
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1.0) as r:
                if r.status == 200:
                    return True
        except Exception:
            time.sleep(0.4)
    return False


def _signal_group(proc, sig):
    """POSIX: send ``sig`` to the child's whole process group (start_new_session leader); fall
    back to signalling just the child if the group can't be resolved."""
    try:
        os.killpg(os.getpgid(proc.pid), sig)
    except (ProcessLookupError, PermissionError, OSError):
        try:
            proc.send_signal(sig)
        except (ProcessLookupError, OSError):
            pass


def stop_server(proc, timeout=8.0):
    """Terminate the child server's whole process tree, escalating to a hard kill; idempotent
    and safe to call from a signal handler, atexit, and the main finally — never leaves an
    orphan holding the port. Cross-platform: POSIX signals the process group; Windows uses
    ``taskkill /T`` on the child tree."""
    if proc is None or proc.poll() is not None:
        return
    if _is_windows():
        _kill_pid(proc.pid, hard=False)
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            _kill_pid(proc.pid, hard=True)
            try:
                proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                pass
        return
    _signal_group(proc, signal.SIGTERM)
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        _signal_group(proc, signal.SIGKILL)
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            pass


def install_cleanup(proc):
    """Guarantee the child server is reaped however the launcher exits — window close
    (main's finally), normal exit (atexit), OR a hard kill via SIGTERM/SIGINT (handlers).
    This closes the D-59 yellow: a killed launcher can no longer orphan uvicorn on port
    8000. (An uncatchable kill — POSIX SIGKILL / Windows ``taskkill /F`` of the launcher —
    is self-healed by free_port() on the next launch.)"""
    atexit.register(stop_server, proc)

    def _handler(signum, _frame):
        stop_server(proc)
        # re-raise the default disposition so the exit status reflects the signal
        try:
            signal.signal(signum, signal.SIG_DFL)
            os.kill(os.getpid(), signum)
        except (OSError, ValueError):
            pass  # platform can't re-raise (e.g. Windows) — atexit/finally already cleaned up

    # SIGHUP is POSIX-only; build the list defensively so import/use works on Windows too.
    sigs = [signal.SIGTERM, signal.SIGINT]
    hup = getattr(signal, "SIGHUP", None)
    if hup is not None:
        sigs.append(hup)
    for sig in sigs:
        try:
            signal.signal(sig, _handler)
        except (ValueError, OSError):
            pass  # not on the main thread / unsupported — atexit + finally still cover it
    return _handler


def main(port=DEFAULT_PORT):
    free_port(port)                       # pre-kill a stale server holding the port
    proc = start_server(port=port)
    install_cleanup(proc)                 # reap the child on window-close, exit, OR kill
    try:
        if not wait_healthy(port=port):
            stop_server(proc)
            print("Server did not become healthy on "
                  f"http://{HOST}:{port}", file=sys.stderr)
            return 1
        import webview  # deferred: needs a display; keep the helpers headless-importable
        webview.create_window(
            "docuchat",
            f"http://{HOST}:{port}/setup",   # wizard first; it redirects to /app when ready
            width=1200, height=820, min_size=(900, 640),
        )
        webview.start()                   # blocks until the window is closed
        return 0
    finally:
        stop_server(proc)                 # kill the child server on quit (no orphan)


if __name__ == "__main__":
    raise SystemExit(main())
