"""Desktop launcher (D-58 v1, Phase A; D-61 cross-platform) — open docuchat in a native window.

Wraps the EXISTING FastAPI app (pipeline/api.py) — it does not touch the pipeline or the
citation verifier. It:
  1. pre-kills anything stuck on the port (so a stale server can't block launch),
  1b. starts ``ollama serve`` as a managed child if nothing is on 11434 and the binary is
     installed (P0.2 warm env: OLLAMA_FLASH_ATTENTION=1 + keep_alive; loopback-forced);
     a user's own running Ollama is never touched,
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
import json
import os
import re
import shutil
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

OLLAMA_PORT = 11434
# Env for an Ollama WE start (P0.2 speed + Move 3a hardening, D-71). A user's own
# already-running Ollama is never touched or restarted.
#  - OLLAMA_ORIGINS: an explicit browser-origin allowlist. Ollama's DEFAULT allows
#    http://0.0.0.0 and any localhost origin — the exact surface of the DNS-rebinding /
#    "0.0.0.0-day" attacks (CVE-2024-28224; Oligo 2024). The app itself talks to Ollama
#    server-to-server (no Origin header), so the tightest browser allowlist costs the
#    app nothing.
OLLAMA_ENV = {"OLLAMA_FLASH_ATTENTION": "1", "OLLAMA_KEEP_ALIVE": "30m",
              "OLLAMA_ORIGINS": "http://127.0.0.1:8000"}
# Minimum safe Ollama (Move 3a): 0.17.1 fixes CVE-2026-7482 "Bleeding Llama" (CVSS 9.1
# unauthenticated heap read leaking env/keys/conversation data on loopback).
MIN_OLLAMA_VERSION = (0, 17, 1)
# Common install locations when the binary isn't on PATH (macOS app bundle CLI,
# Homebrew, Windows per-user install).
_OLLAMA_FALLBACKS = (
    "/Applications/Ollama.app/Contents/Resources/ollama",
    "/opt/homebrew/bin/ollama",
    "/usr/local/bin/ollama",
    str(Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe"),
)

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


def start_server_frozen(host=HOST, port=DEFAULT_PORT):
    """FROZEN build (PyInstaller) path: run uvicorn IN-PROCESS in a daemon thread.

    In a frozen app ``sys.executable`` is the app binary itself, so the subprocess form
    (``sys.executable -m uvicorn``) would relaunch the LAUNCHER recursively instead of
    python — the packaged app would never come up (P2.7 bug). In-process there is no
    child to orphan: the server thread dies with the process. Returns the uvicorn
    Server; the caller may set ``.should_exit = True`` for a graceful stop."""
    import threading

    sys.path.insert(0, str(PIPELINE_DIR))
    import uvicorn
    from api import app
    server = uvicorn.Server(uvicorn.Config(app, host=host, port=port,
                                           log_level="warning"))
    threading.Thread(target=server.run, name="uvicorn-inproc", daemon=True).start()
    return server


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


def find_ollama():
    """Path to the ollama binary: a SILENTLY BUNDLED copy first (P2.7 interim — shipped
    inside the frozen app so the user never installs Ollama by hand), then PATH, then
    the common install spots. None if absent — the setup wizard then guides the user."""
    if getattr(sys, "frozen", False):
        exe_name = "ollama.exe" if _is_windows() else "ollama"
        bundled = Path(sys.executable).resolve().parent / "resources" / exe_name
        if bundled.is_file():
            return str(bundled)
    exe = shutil.which("ollama")
    if exe:
        return exe
    for cand in _OLLAMA_FALLBACKS:
        if cand and Path(cand).is_file():
            return cand
    return None


def ollama_version(exe):
    """(major, minor, patch) from ``ollama --version``, or None if undeterminable."""
    try:
        out = subprocess.run([exe, "--version"], capture_output=True, text=True,
                             timeout=10).stdout
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", out or "")
    return tuple(int(g) for g in m.groups()) if m else None


def ensure_ollama():
    """Start ``ollama serve`` as a managed child when nothing is serving on the Ollama
    port and the binary is installed, with the speed + hardening env (flash attention,
    keep_alive, browser-origin allowlist) and a FORCED loopback bind. Returns the Popen
    (caller reaps it on quit) or None (already running, or not installed). A user's own
    running Ollama — where we cannot set env — is left alone; the app's request-side
    keep_alive still applies.

    Move 3a (D-71): refuses to START an Ollama older than MIN_OLLAMA_VERSION (known
    critical CVEs in the local API) with a clear upgrade message on stderr — the setup
    wizard then guides the user. An undeterminable version starts anyway (fail-open on
    detection, fail-closed on a KNOWN-bad version)."""
    if port_in_use(OLLAMA_PORT):
        return None
    exe = find_ollama()
    if exe is None:
        return None
    ver = ollama_version(exe)
    if ver is not None and ver < MIN_OLLAMA_VERSION:
        print(f"Ollama {'.'.join(map(str, ver))} has known security fixes in "
              f"{'.'.join(map(str, MIN_OLLAMA_VERSION))}+ (CVE-2026-7482). Please update "
              "Ollama (ollama.com/download); not starting the older version.",
              file=sys.stderr)
        return None
    env = dict(os.environ)
    env.update(OLLAMA_ENV)
    env["OLLAMA_HOST"] = f"{HOST}:{OLLAMA_PORT}"   # loopback only — never 0.0.0.0
    kwargs = {}
    if _is_windows():
        kwargs["creationflags"] = _CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    proc = subprocess.Popen([exe, "serve"], env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            **kwargs)
    for _ in range(50):                            # wait briefly so the app's startup
        if port_in_use(OLLAMA_PORT):               # preload finds a live server
            break
        time.sleep(0.1)
    return proc


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


def install_cleanup(*procs):
    """Guarantee the child processes (server + any Ollama we started) are reaped however
    the launcher exits — window close (main's finally), normal exit (atexit), OR a hard
    kill via SIGTERM/SIGINT (handlers). This closes the D-59 yellow: a killed launcher
    can no longer orphan uvicorn on port 8000. (An uncatchable kill — POSIX SIGKILL /
    Windows ``taskkill /F`` of the launcher — is self-healed by free_port() on the next
    launch.)"""
    procs = [p for p in procs if p is not None]
    for p in procs:
        atexit.register(stop_server, p)

    def _handler(signum, _frame):
        for p in procs:
            stop_server(p)
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


def install_cleanup_live(handles):
    """install_cleanup for the window-first flow (UX-10): the children are created on
    a WORKER thread after the handlers are installed, so the handlers read the shared
    ``handles`` dict at FIRE time instead of binding a fixed list. Registered on the
    main thread (signal.signal requires it); covers atexit + SIGTERM/SIGINT/SIGHUP."""
    def _procs():
        return [p for p in (handles.get("proc"), handles.get("ollama")) if p is not None]

    atexit.register(lambda: [stop_server(p) for p in _procs()])

    def _handler(signum, _frame):
        server = handles.get("server")
        if server is not None:
            server.should_exit = True
        for p in _procs():
            stop_server(p)
        try:
            signal.signal(signum, signal.SIG_DFL)
            os.kill(os.getpid(), signum)
        except (OSError, ValueError):
            pass

    sigs = [signal.SIGTERM, signal.SIGINT]
    hup = getattr(signal, "SIGHUP", None)
    if hup is not None:
        sigs.append(hup)
    for sig in sigs:
        try:
            signal.signal(sig, _handler)
        except (ValueError, OSError):
            pass
    return _handler


# UX-10: the splash the window shows INSTANTLY at launch, before the engine exists.
# Inline HTML (no server yet, no assets) matching the app's Ledger look.
SPLASH_HTML = """<!doctype html><html><head><meta charset="utf-8"><style>
  body{margin:0;height:100vh;display:grid;place-items:center;background:#f4f0e8;
       font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;
       color:#1d1b16;-webkit-font-smoothing:antialiased}
  .card{text-align:center}
  .mark{width:56px;height:56px;border-radius:14px;display:grid;place-items:center;
        background:linear-gradient(150deg,#cda465,#b48a4a);color:#231a09;
        font-family:Georgia,'Times New Roman',serif;font-weight:600;font-size:32px;
        margin:0 auto 14px;box-shadow:inset 0 1px 0 rgba(255,255,255,.35)}
  b{font-size:17px}
  p{color:#6b6557;font-size:13.5px;margin:8px 0 0}
  .spin{width:22px;height:22px;border:3px solid #e7e0d3;border-top-color:#b48a4a;
        border-radius:50%;margin:20px auto 0;animation:r .9s linear infinite}
  @keyframes r{to{transform:rotate(360deg)}}
</style></head><body><div class="card"><div class="mark">&sect;</div>
<b>docuchat</b><p id="msg">Starting the local engine&hellip;</p>
<div class="spin"></div></div></body></html>"""

FAIL_HTML = """<!doctype html><html><head><meta charset="utf-8"><style>
  body{margin:0;height:100vh;display:grid;place-items:center;background:#f4f0e8;
       font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;
       color:#1d1b16}
  .card{text-align:center;max-width:46ch;padding:0 20px}
  h2{font-family:Georgia,serif;font-weight:500;margin:0 0 8px}
  p{color:#6b6557;font-size:14px;line-height:1.55}
</style></head><body><div class="card"><h2>docuchat could not start</h2>
<p>The local engine did not come up. Quit docuchat and open it again — that clears
almost every case.</p>
<p>If it keeps happening, another program may be using its port on this computer, or
a background copy of docuchat may still be running (quit it from Activity Monitor).</p>
</div></body></html>"""


def _splash_msg(window, text):
    """Best-effort progress line on the splash; never fatal."""
    try:
        window.evaluate_js(
            "document.getElementById('msg').textContent=" + json.dumps(text))
    except Exception:
        pass


def main(port=DEFAULT_PORT):
    """UX-10 window-first launch: the branded splash appears IMMEDIATELY (was: ~20s of
    Dock bouncing while Ollama spawned + the frozen server imported + health polling,
    all before any window existed). The engine boots on a worker thread and the same
    window then loads the app. Cleanup handlers are installed on the main thread
    BEFORE anything spawns and read the live handles at fire time."""
    handles = {"proc": None, "ollama": None, "server": None}
    install_cleanup_live(handles)

    import webview  # deferred: needs a display; keep the helpers headless-importable
    window = webview.create_window(
        "docuchat", html=SPLASH_HTML,
        width=1200, height=820, min_size=(900, 640),
    )

    def boot():
        try:
            free_port(port)                   # pre-kill a stale server holding the port
            _splash_msg(window, "Starting the local models…")
            handles["ollama"] = ensure_ollama()
            _splash_msg(window, "Starting the document engine…")
            if getattr(sys, "frozen", False):     # packaged app: in-process (P2.7)
                handles["server"] = start_server_frozen(port=port)
            else:
                handles["proc"] = start_server(port=port)
            _splash_msg(window, "Almost ready…")
            if wait_healthy(port=port):
                # wizard first; it redirects to /app when ready
                window.load_url(f"http://{HOST}:{port}/setup")
            else:
                print("Server did not become healthy on "
                      f"http://{HOST}:{port}", file=sys.stderr)
                window.load_html(FAIL_HTML)
        except Exception as e:                # never a silent dead splash
            print(f"launcher boot failed: {e}", file=sys.stderr)
            try:
                window.load_html(FAIL_HTML)
            except Exception:
                pass

    try:
        webview.start(boot)                   # boot runs on a worker thread; blocks
        return 0                              # until the window is closed
    finally:
        server = handles.get("server")
        if server is not None:                # in-process: graceful stop; daemon thread
            server.should_exit = True
        stop_server(handles.get("proc"))      # kill the children on quit (no orphans)
        stop_server(handles.get("ollama"))


if __name__ == "__main__":
    raise SystemExit(main())
