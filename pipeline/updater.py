"""In-place updater (v0.3.0) — click "Update available" and get the new app.

The second deliberate egress after updates.py, and only ever user-clicked:
download the release DMG from GitHub, verify the code signature BEFORE
touching anything, swap the app bundle with a rename-aside rollback, relaunch.
Every failure leaves the running version untouched and the UI falls back to
the browser download page.

Safety order (nothing is destructive until step 5, and step 5 can roll back):
  1. download DMG -> temp file (size-checked against the release asset)
  2. hdiutil attach read-only, find the .app inside
  3. codesign --verify --deep --strict on the NEW app
  4. TEAM ID PINNED: the new app's TeamIdentifier must equal OURS (8W2KYM5Y4J)
     — a compromised download can never install, signed-by-someone-else or not
  5. rename the current .app aside -> ditto the new one in -> remove the aside
     (any error: put the aside back)
  6. detached relaunch of the new app, then SIGTERM to ourselves (the launcher's
     D-59 cleanup path reaps the server; the sleep gives it time to exit)

Runs only from an installed .app bundle (a dev checkout refuses honestly).
State machine mirrors connsync jobs: idle -> downloading -> verifying ->
installing -> restarting | error.
"""

import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

import updates

TEAM_ID = "8W2KYM5Y4J"                      # Developer ID: Jake Anderson
RELEASES_API = updates.RELEASES_API

_state = {"state": "idle", "detail": None, "pct": 0}
_lock = threading.Lock()


def status():
    with _lock:
        return dict(_state)


def _set(state, detail=None, pct=None):
    with _lock:
        _state["state"] = state
        _state["detail"] = detail
        if pct is not None:
            _state["pct"] = pct


def app_bundle_path():
    """The installed .app root we are running from, or None (dev checkout)."""
    if sys.platform != "darwin":
        return None
    p = Path(sys.executable).resolve()
    for parent in p.parents:
        if parent.suffix == ".app":
            return parent
    return None


def _release_dmg_asset():
    """(browser_download_url, size, tag) for the latest release's DMG."""
    req = urllib.request.Request(RELEASES_API,
                                 headers={"Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        rel = json.load(r)
    for asset in rel.get("assets") or []:
        if asset.get("name", "").endswith(".dmg"):
            return asset["browser_download_url"], asset.get("size") or 0, \
                rel.get("tag_name")
    raise RuntimeError("the release has no DMG attached")


def _download(url, dest, expect_size):
    req = urllib.request.Request(url)
    done = 0
    with urllib.request.urlopen(req, timeout=30) as r, open(dest, "wb") as f:
        while True:
            block = r.read(1 << 20)
            if not block:
                break
            f.write(block)
            done += len(block)
            if expect_size:
                _set("downloading", None, min(99, int(done * 100 / expect_size)))
    if expect_size and done != expect_size:
        raise RuntimeError(f"download incomplete ({done} of {expect_size} bytes)")


def _codesign_team(app_path):
    """TeamIdentifier from codesign; raises on an unsigned/broken bundle."""
    subprocess.run(["codesign", "--verify", "--deep", "--strict", str(app_path)],
                   check=True, capture_output=True)
    out = subprocess.run(["codesign", "-dv", str(app_path)],
                         check=True, capture_output=True, text=True).stderr
    for line in out.splitlines():
        if line.startswith("TeamIdentifier="):
            return line.split("=", 1)[1].strip()
    raise RuntimeError("no TeamIdentifier on the downloaded app")


def _mount(dmg):
    out = subprocess.run(["hdiutil", "attach", "-nobrowse", "-readonly",
                          "-plist", str(dmg)], check=True, capture_output=True,
                         text=True).stdout
    import plistlib
    for ent in plistlib.loads(out.encode()).get("system-entities", []):
        if ent.get("mount-point"):
            return ent["mount-point"]
    raise RuntimeError("could not mount the update image")


def _unmount(mount_point):
    subprocess.run(["hdiutil", "detach", mount_point, "-quiet"],
                   capture_output=True)


def _swap(current, incoming):
    """Rename-aside install: any failure puts the old app back."""
    aside = current.with_name(current.name + ".replaced")
    if aside.exists():
        shutil.rmtree(aside, ignore_errors=True)
    os.rename(current, aside)                # same-volume atomic rename
    try:
        # ditto preserves signatures/xattrs exactly (cp -R does not)
        subprocess.run(["ditto", str(incoming), str(current)], check=True,
                       capture_output=True)
    except Exception:
        if current.exists():
            shutil.rmtree(current, ignore_errors=True)
        os.rename(aside, current)            # rollback
        raise
    shutil.rmtree(aside, ignore_errors=True)


def _relaunch(app_path):
    subprocess.Popen(["/bin/sh", "-c",
                      f'sleep 2; open "{app_path}"'],
                     start_new_session=True,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(0.5)
    os.kill(os.getpid(), signal.SIGTERM)     # launcher's D-59 path reaps cleanly


def run_install():
    """The full download-verify-swap-relaunch pass (background thread)."""
    current = app_bundle_path()
    if current is None:
        _set("error", "not running from an installed app — "
                      "download the update from the website instead")
        return
    tmp = None
    mount = None
    try:
        _set("downloading", None, 0)
        url, size, tag = _release_dmg_asset()
        fd, tmp = tempfile.mkstemp(suffix=".dmg")
        os.close(fd)
        _download(url, tmp, size)
        _set("verifying")
        mount = _mount(tmp)
        apps = list(Path(mount).glob("*.app"))
        if not apps:
            raise RuntimeError("the update image contains no app")
        team = _codesign_team(apps[0])
        if team != TEAM_ID:
            raise RuntimeError(f"signature team mismatch ({team}) — refusing to install")
        _set("installing")
        _swap(current, apps[0])
        _unmount(mount)
        mount = None
        _set("restarting", str(tag))
        _relaunch(current)
    except subprocess.CalledProcessError as e:
        detail = (e.stderr or b"").decode(errors="replace")[:200] \
            if isinstance(e.stderr, bytes) else str(e)
        _set("error", f"update failed safely — the current version is untouched "
                      f"({detail or 'verification error'})")
    except Exception as e:
        _set("error", f"update failed safely — the current version is untouched "
                      f"({e})")
    finally:
        if mount:
            _unmount(mount)
        if tmp:
            try:
                os.unlink(tmp)
            except OSError:
                pass


def start_install():
    with _lock:
        if _state["state"] in ("downloading", "verifying", "installing",
                               "restarting"):
            return dict(_state)
        _state.update({"state": "downloading", "detail": None, "pct": 0})
    threading.Thread(target=run_install, name="in-place-update",
                     daemon=True).start()
    return status()
