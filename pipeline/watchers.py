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
    """Copy one new file into the matter through the manual-upload path."""
    import routes_kb
    body = src.read_bytes()
    if not body:
        return None
    dest_dir = routes_kb.KB_DOCS / matter
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name
    stem, suf, i = dest.stem, dest.suffix, 1
    while dest.exists() and keyvault.read_matter_file(dest, matter) != body:
        dest = dest_dir / f"{stem}-{i}{suf}"
        i += 1
    keyvault.write_matter_file(dest, body, matter)
    doc = catalog.add_document(matter, dest, filename=dest.name, status="queued",
                               checksum=hashlib.sha256(body).hexdigest(),
                               size_bytes=len(body))
    ingest_worker.enqueue(doc["id"], str(dest), matter,
                          str(routes_kb.KB_DB), catalog.DEFAULT_DB)
    return doc


def scan_once(db_path=None):
    """One pass over all watched folders. Returns the list of newly-queued docs.
    A missing/renamed folder is skipped silently (the UI shows its status)."""
    allowed = _allowed_suffixes()
    queued = []
    for wf in catalog.list_watch_folders(db_path=db_path):
        folder = Path(wf["path"])
        if not folder.is_dir():
            continue
        if not catalog.get_matter(wf["matter_slug"], db_path=db_path):
            continue    # matter was disposed; folder row is inert
        existing = {d["filename"] for d in
                    catalog.list_documents(wf["matter_slug"], db_path=db_path)}
        try:
            entries = sorted(folder.iterdir())
        except OSError:
            continue
        for f in entries:
            if not f.is_file() or f.suffix.lower() not in allowed:
                continue
            if f.name in existing or f.name.startswith("."):
                continue
            try:
                if time.time() - f.stat().st_mtime < _STABLE_SECONDS:
                    continue    # possibly still being written; next pass gets it
                doc = _ingest_file(wf["matter_slug"], f)
            except OSError:
                continue
            if doc:
                queued.append(doc)
    return queued


def _loop():
    while True:
        try:
            scan_once()
        except Exception:
            pass    # a bad pass never kills the watcher; next tick retries
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
