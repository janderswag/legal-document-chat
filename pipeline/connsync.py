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

import email
import hashlib
import inspect
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
    # BOTH the vendor filename AND the fallback pass through the KB sanitizer
    # (basename only; rejects separators + traversal). A vendor-controlled
    # source id in the fallback must never reach a path unsanitized.
    from routes_kb import _safe_name as kb_safe
    return kb_safe(name) or kb_safe(fallback) or "import.txt"


def _ensure_matter(slug):
    """Resolve the import target. 'unfiled' is created lazily (it is a real
    matter, same convention as the Document Hub tray); anything else must exist."""
    if catalog.get_matter(slug):
        return slug
    if slug == "unfiled":
        return catalog.create_matter("Unfiled")["slug"]
    raise ValueError(f"unknown matter: {slug!r}")


# Services whose `since` handling is VERIFIED correct (F4). Nearly every adapter
# declares since=None, but most implement it as a client-side modified-time
# filter — passing last_sync there makes an OLD item that newly enters scope
# (label applied later, page moved into the space) permanently invisible, and
# Slack's ts_from wants an epoch, not our ISO string. So since is allowlisted:
# fireflies filters server-side by fromDate (ISO) and its free-tier quota is the
# reason F4 exists. Everyone else keeps full listing + seen-ledger dedupe.
_SINCE_SAFE = {"fireflies"}


def _list_items(adapter, creds, since, seen, service=None):
    """Call the adapter's list_items with whatever context it can safely use:
    `since` (allowlisted services only — see _SINCE_SAFE) and `exclude_ids`
    (the seen ledger — F1: lets capped adapters like Gmail page past already-
    imported items). Adapters opt in by signature; older two-arg adapters keep
    working untouched."""
    kwargs = {}
    params = inspect.signature(adapter.list_items).parameters
    if "since" in params and since and service in _SINCE_SAFE:
        kwargs["since"] = since
    if "exclude_ids" in params and seen:
        kwargs["exclude_ids"] = seen
    return adapter.list_items(creds, **kwargs)


def _eml_attachments(body):
    """[(filename, bytes)] for the real attachments in raw RFC822 bytes. Inline
    text/html parts have no filename and are skipped; only named parts that
    decode to bytes count."""
    try:
        msg = email.message_from_bytes(body)
    except Exception:
        return []
    out = []
    for part in msg.walk():
        if part.get_content_maintype() == "multipart":
            continue
        fn = part.get_filename()
        if not fn:
            continue
        try:
            payload = part.get_payload(decode=True)
        except Exception:
            payload = None
        if payload:
            out.append((fn, payload))
    return out


def _store_item(matter, filename, body, provenance):
    """Managed copy + catalog row + ingest enqueue (the watchers pattern, plus
    provenance). Returns the document row, or None for an empty fetch.

    Content identity: if the matter already holds a document with this exact
    checksum, that row is returned and NOTHING new is written or enqueued — the
    same exhibit attached to two emails in a thread (F2), or a Gmail
    UIDVALIDITY rotation re-listing a whole label, must never mint duplicate
    catalog rows over one stored file (a delete would dangle the survivor)."""
    import routes_kb
    if not body:
        return None
    checksum = hashlib.sha256(body).hexdigest()
    existing = catalog.find_document_by_checksum(matter, checksum)
    if existing:
        return existing
    dest_dir = routes_kb.KB_DOCS / matter
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / filename
    stem, suf, i = dest.stem, dest.suffix, 1
    while dest.exists() and keyvault.read_matter_file(dest, matter) != body:
        dest = dest_dir / f"{stem}-{i}{suf}"
        i += 1
    keyvault.write_matter_file(dest, body, matter)
    doc = catalog.add_document(matter, dest, filename=dest.name, status="queued",
                               checksum=checksum,
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
    # Owner decision #4 (council 2026-07-11, Sam's option a): synced items ALWAYS
    # land in Unfiled — suggest-then-confirm, never silent auto-filing into a
    # matter. A configured matter survives as the SUGGESTION on the tray row.
    matter = _ensure_matter("unfiled")
    suggested = config.get("matter")
    if suggested in (None, "", "unfiled") or not catalog.get_matter(suggested):
        suggested = None

    _job_update(conn_id, state="listing", done=0, total=0, skipped=0,
                error=None, started=time.time())
    try:
        seen = catalog.connection_seen_ids(conn_id)
        items = _list_items(adapter, creds, row.get("last_sync"), seen,
                            service=row["service"])
        fresh = [it for it in items if str(it["id"]) not in seen]
        _job_update(conn_id, state="importing", total=len(fresh))
        imported = skipped = attachments = 0
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
            if suggested:
                prov.setdefault("suggested_matter", suggested)
            doc = _store_item(matter, name, body, prov)
            # F2 — "attachments included" must be TRUE: an email's attachments
            # become their own searchable documents (same _ALLOWED gate + size
            # cap as any upload), provenance-linked to the parent message.
            # Stored BEFORE the parent is marked seen: if this pass dies here,
            # the whole message is retried next pass (checksum dedupe makes the
            # retry cheap), instead of the attachments being lost forever.
            if name.lower().endswith(".eml"):
                for att_name, att_body in _eml_attachments(body):
                    # routes_kb._safe_name directly — it returns None for
                    # traversal/separator names, and there is no fallback here:
                    # an attachment we cannot name safely is skipped, never
                    # stored under a default name with un-gated bytes.
                    safe_att = routes_kb._safe_name(att_name)
                    ext = ("." + safe_att.rsplit(".", 1)[-1].lower()
                           if safe_att and "." in safe_att else "")
                    if not safe_att or ext not in routes_kb._ALLOWED:
                        continue           # unsupported attachment types skipped
                    if len(att_body) > routes_kb._MAX_BYTES:
                        continue           # same 25 MB cap as the upload route
                    att_prov = dict(prov)
                    att_prov["attachment_of"] = name
                    if _store_item(matter, safe_att, att_body, att_prov):
                        attachments += 1
            catalog.record_connection_item(conn_id, it["id"],
                                           doc["id"] if doc else None)
            imported += 1
            _job_update(conn_id, done=imported, attachments=attachments)
        catalog.touch_connection_sync(conn_id)
        summary = {"imported": imported, "skipped": skipped,
                   "attachments": attachments,
                   "already": len(items) - len(fresh)}
        _job_update(conn_id, state="done", **summary)
        return summary
    except Exception as e:
        catalog.touch_connection_sync(conn_id, error=e)
        _job_update(conn_id, state="error", error=str(e))
        raise


def start_import(conn_id):
    """Kick a background import (no-op if one is already running). Returns the
    job snapshot. The status is reset SYNCHRONOUSLY before the thread spawns:
    a poll right after this call must never read the previous pass's 'done'
    as the new pass's result."""
    with _jobs_lock:
        job = _jobs.get(conn_id)
        if job and job.get("state") in ("listing", "importing"):
            return dict(job)
        _jobs[conn_id] = {"state": "listing", "done": 0, "total": 0,
                          "skipped": 0, "attachments": 0, "error": None,
                          "started": time.time()}
    t = threading.Thread(target=_run_quiet, args=(conn_id,),
                         name=f"conn-import-{conn_id}", daemon=True)
    t.start()
    return job_status(conn_id) or {"state": "starting"}


def _run_quiet(conn_id):
    try:
        run_import(conn_id)
    except Exception as e:
        # run_import records in-flight failures itself, but a failure BEFORE its
        # try block (unknown connection, unregistered adapter, keyvault error)
        # would otherwise leave the synchronously-reset "listing" status wedged
        # forever — and start_import would refuse to ever spawn again.
        _job_update(conn_id, state="error", error=str(e))


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
