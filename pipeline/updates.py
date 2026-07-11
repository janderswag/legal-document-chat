"""Update check (UX-8, owner-directed) — the app's ONE deliberate non-loopback call.

Everything else in docuchat is loopback-only. This module contacts the GitHub
releases API to read the latest release TAG (a version number) and nothing else:
a plain GET with no identifying payload — no document data, no profile data, no
machine identifiers. Guardrails:

- Runs at most once per 24h, and ONLY when the user's ``update_check`` profile
  toggle is not off (System settings; default on, owner-directed).
- Never runs on server startup and never as part of answering/retrieval — it is
  triggered lazily by the UI polling GET /updates/status, so the SC-6 loopback
  posture of the answer path is untouched and test runs make no network calls
  (the fetcher is monkeypatched in tests).
- Failure is silent: no network, no nag — the cached result (if any) stands.

The visible surface is a one-click "Update available" item above Billing that
opens the download page. Disclosure lives beside the toggle in Settings.
"""

import json
import threading
import time
import urllib.request

import appversion
import catalog

RELEASES_API = ("https://api.github.com/repos/janderswag/docuchat.app/"
                "releases/latest")
DOWNLOAD_PAGE = "https://docuchat.app"
CHECK_INTERVAL_S = 24 * 3600

_cache = {"checked_at": 0.0, "latest": None}
_lock = threading.Lock()


def parse_version(v):
    """'v1.2.3' / '1.2.3-dev' -> (1, 2, 3). Missing/odd parts become 0."""
    v = (v or "").strip().lstrip("v").split("-")[0]
    out = []
    for part in v.split("."):
        try:
            out.append(int(part))
        except ValueError:
            out.append(0)
    return tuple((out + [0, 0, 0])[:3])


def _fetch_latest(timeout=5):
    """One plain GET for the latest release tag. Monkeypatched in tests."""
    req = urllib.request.Request(RELEASES_API,
                                 headers={"Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r).get("tag_name")


def enabled():
    """Default ON (owner-directed); the profile toggle turns it off."""
    return catalog.get_profile().get("update_check", True) is not False


def status(force=False):
    current = appversion.APP_VERSION
    if not enabled():
        return {"current": current, "enabled": False,
                "latest": None, "update_available": False}
    now = time.time()
    with _lock:
        if force or (now - _cache["checked_at"] > CHECK_INTERVAL_S):
            try:
                latest = _fetch_latest()
                if latest:
                    _cache["latest"] = latest
            except Exception:
                pass                      # silent: keep whatever we knew before
            _cache["checked_at"] = now
        latest = _cache["latest"]
    return {
        "current": current,
        "enabled": True,
        "latest": latest,
        "update_available": bool(latest) and parse_version(latest) > parse_version(current),
        "download_page": DOWNLOAD_PAGE,
    }
