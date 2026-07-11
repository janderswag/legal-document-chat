"""Watched-folder connector (UX-6) — local-first document ingestion.

The connector story for a 100%-local app: anything that reaches the disk is
already reachable. Point a watched folder at a scanner's scan-to-folder target or
at a Dropbox/Drive/OneDrive SYNCED folder and you get cloud import with zero
network code in docuchat — the sync client moves the bytes, we only ever read a
local directory.

Mechanics: a single daemon thread polls each watched folder (no new watchdog
dependency; poll interval 15s). A file is picked up when (a) its suffix is a
supported document type, (b) no document with that filename already exists in the
target matter, and (c) it has been stable on disk for a couple of seconds (so we
never ingest a half-written file). Pickup runs the SAME path as a manual upload:
bytes are copied into the managed KB tree (DEK-encrypted where the encryption
cycle is active), a catalog row is created, and the serialized ingest worker does
the rest. The source file in the watched folder is NEVER modified or deleted
(hard rule #5: originals are read-only).
"""

import hashlib
import sys
import threading
import time
from pathlib import Path

import catalog
import ingest_worker
import keyvault

POLL_SECONDS = 15
_STABLE_SECONDS = 2     # a file must be this old (mtime) before pickup

_started = False
_start_lock = threading.Lock()

# Heartbeat (council 2026-07-11 Move 4): per-folder liveness the UI can render as
# "Watching · checked 12s ago · 3 files added". In-memory by design — after a
# restart "not checked yet" is the honest answer.
_stats = {}             # folder id -> {"last_scan": epoch, "files_added": int}
_stats_lock = threading.Lock()

# Re-scan bookkeeping: (folder id, filename) -> the file's mtime at our last
# READ of it. Comparing against this (never against the document row's
# `updated`, which is bumped by processing-status transitions and can postdate
# a correction saved during a long OCR) means a corrected re-scan always lands,
# and a file is read+hashed at most once per change — not once per poll.
# In-memory: after a restart every file is re-read ONCE, checksum identity
# drops the known ones, and the map is warm again.
_seen_mtimes = {}


def folder_stats(folder_id):
    with _stats_lock:
        s = _stats.get(folder_id)
        return dict(s) if s else None


def _bump_stats(folder_id, added):
    with _stats_lock:
        s = _stats.setdefault(folder_id, {"files_added": 0})
        s["last_scan"] = time.time()
        s["files_added"] += added


def _allowed_suffixes():
    import routes_kb
    return routes_kb._ALLOWED


def validate_folder(path):
    """A watchable folder is an absolute, existing directory OUTSIDE the managed KB
    tree (watching our own output would loop). Returns the resolved Path or raises
    ValueError."""
    import routes_kb
    p = Path(path).expanduser()
    if not p.is_absolute():
        raise ValueError("folder path must be absolute")
    p = p.resolve()
    if not p.is_dir():
        raise ValueError(f"not a folder: {p}")
    try:
        p.relative_to(routes_kb.KB_DOCS.resolve())
        inside_kb = True
    except ValueError:
        inside_kb = False
    if inside_kb:
        raise ValueError("cannot watch docuchat's own document store")
    return p


def _ingest_file(matter, src):
    """Copy one new file into the matter through the manual-upload path. Returns
    the new document row, or None when the matter already holds this exact
    content (checksum identity — never a second catalog row over one file)."""
    import routes_kb
    body = src.read_bytes()
    if not body:
        return None
    checksum = hashlib.sha256(body).hexdigest()
    if catalog.find_document_by_checksum(matter, checksum):
        return None    # content already in the matter (e.g. touched mtime only)
    dest_dir = routes_kb.KB_DOCS / matter
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name
    stem, suf, i = dest.stem, dest.suffix, 1
    while dest.exists() and keyvault.read_matter_file(dest, matter) != body:
        dest = dest_dir / f"{stem}-{i}{suf}"
        i += 1
    keyvault.write_matter_file(dest, body, matter)
    doc = catalog.add_document(matter, dest, filename=dest.name, status="queued",
                               checksum=checksum,
                               size_bytes=len(body))
    ingest_worker.enqueue(doc["id"], str(dest), matter,
                          str(routes_kb.KB_DB), catalog.DEFAULT_DB)
    return doc


def scan_once(db_path=None):
    """One pass over all watched folders. Returns the list of newly-queued docs.
    A missing folder or disposed matter is skipped (the UI shows its status).

    Re-scan integrity (council 2026-07-11 Move 4, Elena's filing hazard): a file
    whose name already exists in the matter is NOT skipped forever — whenever
    its mtime advances past our last read (_seen_mtimes), it is re-read, and
    ingested when the content actually changed (a corrected re-scan of
    contract.pdf must land; a merely-touched identical file is dropped by
    checksum identity in _ingest_file, and is not read again until it changes
    again). The folder and its IMMEDIATE subfolders are scanned (scanner trays
    write dated dirs, council 2026-07-12); deeper nesting is deliberately not
    walked, and the UI says exactly that."""
    allowed = _allowed_suffixes()
    queued = []
    for wf in catalog.list_watch_folders(db_path=db_path):
        folder = Path(wf["path"])
        if not folder.is_dir():
            _bump_stats(wf["id"], 0)
            continue
        if not catalog.get_matter(wf["matter_slug"], db_path=db_path):
            _bump_stats(wf["id"], 0)
            continue    # matter was disposed; folder row is inert
        try:
            entries = sorted(folder.iterdir())
            for sub in list(entries):
                # one level of subfolders (scanner trays write dated dirs);
                # deeper nesting is deliberately NOT walked, and the UI says so
                # symlinked dirs are skipped: following one would silently
                # broaden the picker-chosen root (validate_folder guards the
                # root only) — worst case a link into the KB store self-ingests
                if sub.is_dir() and not sub.is_symlink() \
                        and not sub.name.startswith("."):
                    try:
                        entries.extend(sorted(sub.iterdir()))
                    except OSError as e:
                        print(f"[watchers] cannot read {sub}: {e}",
                              file=sys.stderr)
        except OSError as e:
            print(f"[watchers] cannot read {folder}: {e}", file=sys.stderr)
            _bump_stats(wf["id"], 0)
            continue
        added = 0
        for f in entries:
            if not f.is_file() or f.suffix.lower() not in allowed:
                continue
            if f.name.startswith("."):
                continue
            # keyed by path RELATIVE to the watched root, so a.pdf in two
            # different subfolders stays two distinct files on re-scan
            key = (wf["id"], str(f.relative_to(folder)))
            try:
                mtime = f.stat().st_mtime
                if time.time() - mtime < _STABLE_SECONDS:
                    continue    # possibly still being written; next pass gets it
                if _seen_mtimes.get(key, -1.0) >= mtime:
                    continue    # unchanged since our last read of this file
                doc = _ingest_file(wf["matter_slug"], f)
                _seen_mtimes[key] = mtime
            except OSError as e:
                print(f"[watchers] cannot ingest {f.name}: {e}", file=sys.stderr)
                continue
            if doc:
                queued.append(doc)
                added += 1
        _bump_stats(wf["id"], added)
    return queued


def _loop():
    while True:
        try:
            scan_once()
        except Exception as e:
            # a bad pass never kills the watcher; next tick retries — but it is
            # LOGGED, never swallowed (council 2026-07-11 Move 4 honesty rider)
            print(f"[watchers] scan pass failed: {type(e).__name__}: {e}",
                  file=sys.stderr)
        try:
            # v0.3.0 (D-81): sync-enabled connector connections ride the same tick;
            # sync_due() rate-limits itself per connection and spawns its own thread.
            import connsync
            connsync.sync_due()
        except Exception:
            pass
        time.sleep(POLL_SECONDS)


def start():
    """Start the single poller thread (idempotent, daemon)."""
    global _started
    with _start_lock:
        if _started:
            return False
        _started = True
    threading.Thread(target=_loop, name="folder-watcher", daemon=True).start()
    return True
