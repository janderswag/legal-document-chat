"""Move 3c (D-71) — keep client-document stores out of OS backup/index pipelines.

The KB vector store, catalog database, and managed document copies contain client text.
On macOS, Time Machine (and any backup target it feeds) will silently copy them
off-device unless excluded, and Spotlight will index document CONTENT into its local
indexes. This module applies the exclusions idempotently at app startup:

  - Time Machine: ``tmutil addexclusion <path>`` (sticky, per-path, unprivileged).
  - Spotlight: a ``.metadata_never_index`` marker inside each store directory (the
    unprivileged mechanism; system Settings can also exclude but needs the user).

Honest scope: this is leak REDUCTION for the dev/run-from-source layout. The full
answer is Move 4 at-rest encryption (encrypted stores are useless in any backup);
these exclusions still matter so plaintext never reaches a backup in the interim.
Failures are logged, never fatal — a missing tmutil (non-macOS) is normal.
"""

import logging
import subprocess
import sys
from pathlib import Path

log = logging.getLogger("docuchat.data_protection")


def _tm_exclude(path):
    try:
        r = subprocess.run(["tmutil", "addexclusion", str(path)],
                           capture_output=True, text=True, timeout=10)
        return r.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False


def _spotlight_marker(path):
    p = Path(path)
    if not p.is_dir():
        return False
    try:
        (p / ".metadata_never_index").touch(exist_ok=True)
        return True
    except OSError:
        return False


def protect_paths(named_paths):
    """Apply backup/index exclusions to each existing path. Returns a report dict keyed
    by store NAME (never a filesystem path — the Settings status surface has a no-path
    contract), surfaced in Settings so the posture is visible, not assumed."""
    report = {}
    for name, path in named_paths.items():
        p = Path(path)
        if not p.exists():
            report[name] = "absent"
            continue
        tm = _tm_exclude(p) if sys.platform == "darwin" else False
        sl = _spotlight_marker(p) if p.is_dir() and sys.platform == "darwin" else False
        report[name] = ("time-machine-excluded" if tm else "tmutil-unavailable") + \
                       ("+spotlight-marker" if sl else "")
        if not tm and sys.platform == "darwin":
            log.warning("could not add Time Machine exclusion for %s", p)
    return report


def default_protected_paths():
    """The client-data stores of the run-from-source layout, keyed by display name."""
    import catalog
    import routes_kb
    return {"search index": routes_kb.KB_DB, "document copies": routes_kb.KB_DOCS,
            "catalog database": catalog.DEFAULT_DB}
