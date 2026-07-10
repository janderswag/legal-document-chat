"""Connector import engine (v0.3.0, D-81) — pulls a connection's documents in.

Every import is user-initiated (the Import button or a sync toggle the user
turned on). Fetched bytes take the SAME path as a manual upload: managed copy
under the matter (DEK-encrypted where the encryption cycle is active), catalog
row with provenance (source_json), serialized ingest worker. Dedupe is by
(connection, source id) first — an item is imported once — then by content
against same-named files, exactly like uploads.

Jobs run on daemon threads (one per connection at a time); the watcher loop
calls sync_due() so connections with sync enabled refresh at most every
SYNC_INTERVAL_S without any new scheduler machinery.
"""

import hashlib
import json
import threading
import time

import catalog
import connectors
import ingest_worker
import keyvault

SYNC_INTERVAL_S = 30 * 60          # sync-enabled connections refresh at most this often

_jobs = {}                          # connection id -> job dict (in-memory, UI status)
_jobs_lock = threading.Lock()


def job_status(conn_id):
    with _jobs_lock:
        job = _jobs.get(conn_id)
        return dict(job) if job else None


def _job_update(conn_id, **kw):
    with _jobs_lock:
        _jobs.setdefault(conn_id, {}).update(kw)


def _safe_name(name, fallback):
    from routes_kb import _safe_name as kb_safe
    return kb_safe(name) or fallback


def _ensure_matter(slug):
    """Resolve the import target. 'unfiled' is created lazily (it is a real
    matter, same convention as the Document Hub tray); anything else must exist."""
    if catalog.get_matter(slug):
        return slug
    if slug == "unfiled":
        return catalog.create_matter("Unfiled")["slug"]
    raise ValueError(f"unknown matter: {slug!r}")


def _store_item(matter, filename, body, provenance):
    """Managed copy + catalog row + ingest enqueue (the watchers pattern, plus
    provenance). Returns the document row, or None for an empty fetch."""
    import routes_kb
    if not body:
        return None
    dest_dir = routes_kb.KB_DOCS / matter
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / filename
    stem, suf, i = dest.stem, dest.suffix, 1
    while dest.exists() and keyvault.read_matter_file(dest, matter) != body:
        dest = dest_dir / f"{stem}-{i}{suf}"
        i += 1
    keyvault.write_matter_file(dest, body, matter)
    doc = catalog.add_document(matter, dest, filename=dest.name, status="queued",
                               checksum=hashlib.sha256(body).hexdigest(),
                               size_bytes=len(body),
                               source_json=json.dumps(provenance))
    ingest_worker.enqueue(doc["id"], str(dest), matter,
                          str(routes_kb.KB_DB), catalog.DEFAULT_DB)
    return doc


def run_import(conn_id):
    """One full import pass for a connection. Returns a summary dict; errors are
    recorded on the connection row (last_error) AND re-raised for the caller."""
    import routes_kb
    row = catalog.get_connection(conn_id)
    if row is None:
        raise ValueError(f"unknown connection: {conn_id}")
    adapter = connectors.get(row["service"])
    creds = json.loads(keyvault.decrypt_secret(row["credential"]).decode("utf-8"))
    config = json.loads(row["config"] or "{}")
    matter = _ensure_matter(config.get("matter") or "unfiled")

    _job_update(conn_id, state="listing", done=0, total=0, skipped=0,
                error=None, started=time.time())
    try:
        items = adapter.list_items(creds)
        seen = catalog.connection_seen_ids(conn_id)
        fresh = [it for it in items if str(it["id"]) not in seen]
        _job_update(conn_id, state="importing", total=len(fresh))
        imported = skipped = 0
        for it in fresh:
            filename, body, prov = adapter.fetch_item(creds, it)
            name = _safe_name(filename, f"{row['service']}-{it['id']}.txt")
            if ("." + name.rsplit(".", 1)[-1].lower() if "." in name else "") \
                    not in routes_kb._ALLOWED:
                skipped += 1               # honest count, never a fake success
                catalog.record_connection_item(conn_id, it["id"], None)
                _job_update(conn_id, skipped=skipped)
                continue
            prov = dict(prov or {})
            prov.setdefault("service", row["service"])
            prov.setdefault("source_id", str(it["id"]))
            doc = _store_item(matter, name, body, prov)
            catalog.record_connection_item(conn_id, it["id"],
                                           doc["id"] if doc else None)
            imported += 1
            _job_update(conn_id, done=imported)
        catalog.touch_connection_sync(conn_id)
        summary = {"imported": imported, "skipped": skipped,
                   "already": len(items) - len(fresh)}
        _job_update(conn_id, state="done", **summary)
        return summary
    except Exception as e:
        catalog.touch_connection_sync(conn_id, error=e)
        _job_update(conn_id, state="error", error=str(e))
        raise


def start_import(conn_id):
    """Kick a background import (no-op if one is already running). Returns the
    job snapshot."""
    with _jobs_lock:
        job = _jobs.get(conn_id)
        if job and job.get("state") in ("listing", "importing"):
            return dict(job)
    t = threading.Thread(target=_run_quiet, args=(conn_id,),
                         name=f"conn-import-{conn_id}", daemon=True)
    t.start()
    return job_status(conn_id) or {"state": "starting"}


def _run_quiet(conn_id):
    try:
        run_import(conn_id)
    except Exception:
        pass                      # recorded on the row + job; never kills a thread


def sync_due():
    """Called from the watcher tick: re-import every sync-enabled connection whose
    last pass is older than SYNC_INTERVAL_S. Serialized with imports per
    connection by start_import's running check."""
    now = time.time()
    for row in catalog.list_connections():
        if not row.get("config", {}).get("sync"):
            continue
        job = job_status(row["id"])
        if job and job.get("state") in ("listing", "importing"):
            continue
        last = row.get("last_sync")
        if last:
            try:
                from datetime import datetime
                age = now - datetime.fromisoformat(last).timestamp()
            except ValueError:
                age = SYNC_INTERVAL_S + 1
            if age < SYNC_INTERVAL_S:
                continue
        start_import(row["id"])
