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
     normally, OR the launcher is hard-killed (no orphaned uvicorn),
  6. watches for pipeline/updater.py's restart marker (a user-clicked in-place update)
     and OWNS the relaunch: spawns the new app detached, destroys the window, exits
     cleanly. Only the launcher's main thread can safely do this (see
     _watch_restart_marker) — a background server thread cannot.

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
import threading
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


def _restart_marker_path():
    """Where updater.py drops its restart marker. Mirrors pipeline/apppaths.py's
    data_root() rather than importing it, so this module stays import-safe/headless
    (the module docstring's guarantee) without needing the pipeline dir on sys.path."""
    override = os.environ.get("DOCUCHAT_DATA_DIR")
    if override:
        return Path(override) / ".update-restart"
    if getattr(sys, "frozen", False):
        return Path.home() / "Library" / "Application Support" / "docuchat" / ".update-restart"
    return PIPELINE_DIR / ".update-restart"


def _watch_restart_marker(window, poll=0.5):
    """Background thread: the only reliable way to notice an in-place update wants to
    restart the app. The packaged build runs uvicorn IN-PROCESS (start_server_frozen),
    sharing this OS process with the pywebview GUI, whose main thread is blocked inside
    the native macOS run loop for the whole session — a bare SIGTERM from updater.py can
    sit pending forever because the interpreter never returns to bytecode to run the
    registered handler, leaving the window stuck showing "Restarting…" (the bug this
    closes). window.destroy() is safe to call from ANY thread — pywebview marshals it
    onto the main run loop (AppHelper.callAfter), the same mechanism evaluate_js() from
    boot() already relies on — so this thread notices the marker and drives the actual
    relaunch + shutdown without needing a signal to ever be delivered.

    No marker: no-op, forever — a server crash must never relaunch-loop; the marker is
    the explicit consent from a user-clicked update."""
    marker = _restart_marker_path()
    while True:
        time.sleep(poll)
        if not marker.exists():
            continue
        app_path = marker.read_text().strip()
        try:
            marker.unlink()
        except OSError:
            pass
        if app_path:
            # `open` must not fire until THIS process has actually exited — otherwise
            # macOS just re-activates the still-running old instance (the original bug,
            # in a slow-teardown corner: window.destroy() unblocks webview.start(), but
            # main()'s finally still has to run stop_server() on the child server/Ollama,
            # which can take up to ~16s of SIGTERM-then-SIGKILL waits). A fixed sleep
            # can't bound that, so poll our own pid with `kill -0` instead of sleeping a
            # guess. Capped at 120s (240 * 0.5s) so a launch can never hang forever; past
            # the bound we open anyway — worst case it just re-activates the old instance,
            # and by then the UI's 25s "Restarting…" fallback has already told the user to
            # quit and reopen.
            pid = os.getpid()
            subprocess.Popen(
                ["/bin/sh", "-c",
                 f'n=0; while kill -0 {pid} 2>/dev/null && [ $n -lt 240 ]; do '
                 f'sleep 0.5; n=$((n+1)); done; open "{app_path}"'],
                start_new_session=True,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        window.destroy()
        return


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


# Adoption council 2026-07-11: an 8GB Mac downloads 10.5GB of models and then
# swap-thrashes with no explanation. Refuse-with-explanation instead. Fails
# OPEN (never blocks when RAM cannot be read); DOCUCHAT_SKIP_RAM_GATE=1 is the
# documented escape hatch for a wrong detection.
MIN_RAM_BYTES = 16 * 1024**3


def total_ram_bytes():
    """Physical RAM; 0 when undeterminable (the gate then fails open)."""
    try:
        out = subprocess.run(["sysctl", "-n", "hw.memsize"],
                             capture_output=True, text=True, timeout=5)
        return int(out.stdout.strip() or 0)
    except (OSError, subprocess.SubprocessError, ValueError):
        # any failure at all -> 0 -> the gate fails open (never a crash
        # before a window exists; that is the exact mystery this gate kills)
        return 0


def ram_ok():
    if os.environ.get("DOCUCHAT_SKIP_RAM_GATE") == "1":
        return True
    total = total_ram_bytes()
    return total == 0 or total >= MIN_RAM_BYTES


LOWRAM_HTML = """<!doctype html><html><head><meta charset="utf-8"><style>
  body{margin:0;height:100vh;display:grid;place-items:center;background:#f4f0e8;
       font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;
       color:#1d1b16}
  .card{max-width:480px;padding:0 32px}
  h2{font-family:Georgia,serif;font-weight:500;margin:0 0 12px}
  p{font-size:14px;line-height:1.55}
  .fine{color:#6b6557;font-size:13px}
  code{background:#f6f2ea;border:1px solid #e7e0d3;border-radius:5px;padding:1px 5px;
       font-size:12px}
</style></head><body><div class="card">
<h2>This Mac does not have enough memory for docuchat</h2>
<p>docuchat runs its AI models entirely on this Mac - that is what keeps your
documents private - and the models need <b>16 GB of memory</b>. This Mac has
{ram_gb} GB, so answers would be extremely slow or fail outright.</p>
<p class="fine">Nothing was installed or changed. If you believe this detection
is wrong, relaunch from Terminal with
<code>DOCUCHAT_SKIP_RAM_GATE=1 open -n -a docuchat</code> after closing this
window.</p>
</div></body></html>"""


def _require_smoke_env():
    """Guard for the DOCUCHAT_SMOKE=1 branch: refuse to proceed unless the caller
    EXPLICITLY set both DOCUCHAT_DATA_DIR and DOCUCHAT_PORT. Defense in depth — the
    real caller (desktop/smoke_packaged.sh) always passes both, but the launcher must
    not trust that: DOCUCHAT_SMOKE=1 alone would default to port 8000 and the owner's
    real data dir, and free_port() would then kill the owner's running app."""
    missing = [v for v in ("DOCUCHAT_DATA_DIR", "DOCUCHAT_PORT") if not os.environ.get(v)]
    if missing:
        print("smoke: DOCUCHAT_SMOKE=1 requires " + " and ".join(missing) + " to also be "
              "set explicitly — refusing to risk the owner's real app/data on the defaults "
              "(see desktop/smoke_packaged.sh)", file=sys.stderr)
        sys.exit(2)


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

    # DOCUCHAT_SMOKE=1: packaged-app smoke gate (desktop/smoke_packaged.sh). No display
    # is available/wanted for an automated check, so skip pywebview entirely and start
    # the SAME server the real launcher starts (in-process for a frozen build), then
    # block until the smoke script sends SIGTERM — install_cleanup_live's handler above
    # already stops the server/Ollama children on that signal. Unset (the default): zero
    # behavior change to a normal launch.
    if os.environ.get("DOCUCHAT_SMOKE") == "1":
        _require_smoke_env()
        free_port(port)
        handles["ollama"] = ensure_ollama()
        if getattr(sys, "frozen", False):
            handles["server"] = start_server_frozen(port=port)
        else:
            handles["proc"] = start_server(port=port)
        # smoke_packaged.sh documents 120s patience for a cold scratch start (fresh
        # data dir, no warm model cache) — the 40s default is tuned for a warm launch.
        if not wait_healthy(port=port, timeout=120):
            print(f"smoke: server did not become healthy on http://{HOST}:{port}",
                  file=sys.stderr)
            stop_server(handles.get("proc"))
            stop_server(handles.get("ollama"))
            return 1
        print(f"smoke: healthy on http://{HOST}:{port}", flush=True)
        while True:
            time.sleep(1)

    # RAM gate BEFORE any server/Ollama start (the smoke path above is never
    # gated: an automated check must not depend on the build machine's RAM).
    if not ram_ok():
        import webview
        # ram_ok() was False, so this read succeeded (0 fails open) — reuse it
        # rather than re-reading and risking "This Mac has 0 GB" in the dialog
        gb = round(total_ram_bytes() / 1024**3)
        webview.create_window("docuchat",
                              html=LOWRAM_HTML.replace("{ram_gb}", str(gb)),
                              width=640, height=420)
        webview.start()
        return 0

    import webview  # deferred: needs a display; keep the helpers headless-importable

    class JsBridge:
        """Native helpers exposed to the UI as window.pywebview.api (council
        2026-07-11 Move 4). DIALOGS ONLY — no file access of any kind lives
        here; choose_folder returns the path the user picked (or None), and
        the server-side validate_folder still gates it. NOTE for the release
        gate: the headless smoke never creates a window, so bridge presence is
        a MANUAL gate item (click 'Choose a folder' once in the built app)."""

        def __init__(self):
            # UNDERSCORE-PRIVATE, load-bearing: pywebview's get_functions walks
            # every PUBLIC attribute recursively - a public window attribute
            # would re-expose the whole Window API (load_url to a remote
            # origin, SAVE dialogs, destroy) to page JS. Keep it private.
            self._window = None

        def choose_folder(self):
            if self._window is None:
                return None
            try:
                picked = self._window.create_file_dialog(webview.FOLDER_DIALOG)
            except Exception as e:
                print(f"folder dialog failed: {e}", file=sys.stderr)
                return None
            if not picked:
                return None
            return picked[0] if isinstance(picked, (list, tuple)) else str(picked)

    bridge = JsBridge()
    window = webview.create_window(
        "docuchat", html=SPLASH_HTML,
        width=1200, height=820, min_size=(900, 640),
        js_api=bridge,
    )
    bridge._window = window
    # Guarded by construction, not just by condition: DOCUCHAT_SMOKE=1 always returns
    # above before a window (or this thread) ever exists, so the restart-marker flow
    # can never fire during a smoke run.
    threading.Thread(target=_watch_restart_marker, args=(window,),
                     name="update-restart-watch", daemon=True).start()

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
    # DOCUCHAT_PORT: smoke_packaged.sh points a real built .app at a scratch port so it
    # never collides with the owner's real app on the default 8000.
    raise SystemExit(main(port=int(os.environ.get("DOCUCHAT_PORT", DEFAULT_PORT))))
