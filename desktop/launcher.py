"""macOS desktop launcher (D-58 v1, Phase A) — open Legal Document Chat in a native window.

Wraps the EXISTING FastAPI app (pipeline/api.py) — it does not touch the pipeline or the
citation verifier. It:
  1. pre-kills anything stuck on the port (so a stale server can't block launch),
  2. starts the FastAPI server as a CHILD process (handle held for clean shutdown),
  3. health-checks 127.0.0.1:8000,
  4. opens the first-run wizard (/setup, which drops into /app when ready) in a pywebview
     window,
  5. kills the child server on quit.

Loopback-only (the server binds 127.0.0.1, never 0.0.0.0); no telemetry; no auto-update.
Run locally:  python desktop/launcher.py
The pywebview import is deferred into main() so the helpers are importable/testable headless.
"""

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


def port_in_use(port, host=HOST):
    """True if something is accepting connections on host:port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.3)
        return s.connect_ex((host, port)) == 0


def listening_pids(port):
    """PIDs LISTENing on ``port`` (macOS/BSD lsof). Empty if none / lsof unavailable."""
    try:
        out = subprocess.run(["lsof", "-ti", f"tcp:{port}", "-sTCP:LISTEN"],
                             capture_output=True, text=True, timeout=5)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    return [int(p) for p in out.stdout.split() if p.strip().isdigit()]


def free_port(port):
    """Pre-kill any process LISTENing on ``port`` (TERM, then KILL stragglers) so a stale
    server can't block launch. Returns the number of processes signaled."""
    pids = listening_pids(port)
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    if pids:
        for _ in range(20):
            if not listening_pids(port):
                break
            time.sleep(0.1)
        for pid in listening_pids(port):
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
    return len(pids)


def start_server(host=HOST, port=DEFAULT_PORT):
    """Start the FastAPI app as a child uvicorn process (loopback only); return the Popen.
    The caller MUST stop_server() it on exit (handle held — no orphaned server)."""
    return subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "api:app",
         "--host", host, "--port", str(port), "--log-level", "warning"],
        cwd=str(PIPELINE_DIR),
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


def stop_server(proc, timeout=8.0):
    """Terminate the child server, escalating to KILL; never leave it orphaned."""
    if proc is None or proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=timeout)


def main(port=DEFAULT_PORT):
    free_port(port)                       # pre-kill a stale server holding the port
    proc = start_server(port=port)
    try:
        if not wait_healthy(port=port):
            stop_server(proc)
            print("Server did not become healthy on "
                  f"http://{HOST}:{port}", file=sys.stderr)
            return 1
        import webview  # deferred: needs a display; keep the helpers headless-importable
        webview.create_window(
            "Legal Document Chat",
            f"http://{HOST}:{port}/setup",   # wizard first; it redirects to /app when ready
            width=1200, height=820, min_size=(900, 640),
        )
        webview.start()                   # blocks until the window is closed
        return 0
    finally:
        stop_server(proc)                 # kill the child server on quit (no orphan)


if __name__ == "__main__":
    raise SystemExit(main())
