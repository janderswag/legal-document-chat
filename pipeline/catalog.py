"""SQLite catalog — durable app state for the local UI (matters, documents, threads).

One responsibility: persistence. All queries are parameterized (no string
interpolation). The DB lives at pipeline/.kb_catalog.db (git-ignored, D-28) and is
overridable via ``db_path`` for tests. Matter slugs are path-safe (validated here so
no caller can inject a path).

Encryption (D-73, design §3): the PRODUCTION catalog is SQLCipher-encrypted, keyed
by the Keychain master key (keyvault). ``_connect`` detects the format from the file
header — SQLCipher files don't carry SQLite's plaintext magic — so both formats work
through the one code path. New catalogs are created encrypted ONLY at the fixed
production path on macOS (``_PRODUCTION_DB``, compared literally so tests that swap
``DEFAULT_DB`` keep getting plain files); existing plain catalogs are migrated once
via ``migrate_catalog_sqlcipher.py`` (rename-aside, rehearsed by the drill tests).
"""

import hashlib
import json
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import apppaths

DEFAULT_DB = apppaths.data_root() / ".kb_catalog.db"
_PRODUCTION_DB = apppaths.data_root() / ".kb_catalog.db"  # fixed; DEFAULT_DB moves in tests
_SQLITE_HEADER = b"SQLite format 3\x00"

# Tests inject a key provider (callable -> 32 bytes); None = keyvault.master_key.
MASTER_KEY_PROVIDER = None


def _master_key():
    if MASTER_KEY_PROVIDER is not None:
        return MASTER_KEY_PROVIDER()
    import keyvault  # deferred: keyvault imports this module
    return keyvault.master_key()


def is_encrypted(path):
    """True if the file exists and is NOT plain SQLite (SQLCipher randomizes the
    header). An empty/missing file is 'not encrypted'."""
    try:
        with open(path, "rb") as f:
            head = f.read(16)
    except FileNotFoundError:
        return False
    return len(head) == 16 and head != _SQLITE_HEADER


def _encrypt_new(path):
    """Create-time policy: encrypt ONLY the real production catalog, only on macOS
    (Keychain), and only if the master key is actually reachable. Everything else
    (tests, scratch copies, other platforms) stays plain sqlite."""
    if sys.platform != "darwin" or Path(path) != _PRODUCTION_DB:
        return False
    try:
        _master_key()
        return True
    except Exception:
        return False  # no Keychain -> plain catalog beats no catalog

_SCHEMA = """
CREATE TABLE IF NOT EXISTS matters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT UNIQUE NOT NULL,
    display_name TEXT UNIQUE NOT NULL,
    created TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    matter_slug TEXT NOT NULL,
    filename TEXT NOT NULL,
    stored_path TEXT NOT NULL,
    checksum TEXT,
    size_bytes INTEGER,
    status TEXT NOT NULL,
    reason TEXT,
    updated TEXT NOT NULL,
    FOREIGN KEY (matter_slug) REFERENCES matters(slug)
);
CREATE TABLE IF NOT EXISTS legal_holds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    matter_slug TEXT NOT NULL,
    reason TEXT NOT NULL,
    created TEXT NOT NULL,
    released TEXT,
    released_reason TEXT
);
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prev_hash TEXT NOT NULL,
    entry_hash TEXT NOT NULL,
    ts TEXT NOT NULL,
    event TEXT NOT NULL,
    matter_slug TEXT,
    detail TEXT
);
CREATE TABLE IF NOT EXISTS transcript_lines (
    doc_id INTEGER NOT NULL,
    page INTEGER NOT NULL,
    line INTEGER NOT NULL,
    char_start INTEGER NOT NULL,
    char_end INTEGER NOT NULL,
    PRIMARY KEY (doc_id, page, line)
);
CREATE TABLE IF NOT EXISTS threads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    matter_slug TEXT NOT NULL,
    title TEXT NOT NULL,
    created TEXT NOT NULL,
    updated TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id INTEGER NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    citations_json TEXT,
    created TEXT NOT NULL,
    FOREIGN KEY (thread_id) REFERENCES threads(id)
);
CREATE TABLE IF NOT EXISTS profile (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS watch_folders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    matter_slug TEXT NOT NULL,
    path TEXT NOT NULL,
    created TEXT NOT NULL,
    UNIQUE (matter_slug, path)
);
CREATE TABLE IF NOT EXISTS connections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    service TEXT NOT NULL,
    label TEXT,
    credential BLOB NOT NULL,
    config TEXT,
    last_sync TEXT,
    last_error TEXT,
    created TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS connection_items (
    connection_id INTEGER NOT NULL,
    source_id TEXT NOT NULL,
    doc_id INTEGER,
    imported TEXT NOT NULL,
    PRIMARY KEY (connection_id, source_id)
);
CREATE TABLE IF NOT EXISTS matter_facts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    matter_slug TEXT NOT NULL,
    doc_id INTEGER NOT NULL,
    fact_key TEXT NOT NULL,
    fact_type TEXT NOT NULL,
    value_json TEXT NOT NULL,
    page INTEGER NOT NULL,
    char_start INTEGER NOT NULL,
    char_end INTEGER NOT NULL,
    span TEXT NOT NULL,
    extractor_version TEXT NOT NULL,
    created TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_matter_facts ON matter_facts (matter_slug, fact_type);
CREATE TABLE IF NOT EXISTS fact_review (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    matter_slug TEXT NOT NULL,
    fact_key TEXT NOT NULL,
    status TEXT NOT NULL,
    confirmed_date TEXT,
    created TEXT NOT NULL,
    UNIQUE (matter_slug, fact_key)
);
"""


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _connect(db_path=None):
    path = Path(db_path) if db_path else DEFAULT_DB
    path.parent.mkdir(parents=True, exist_ok=True)
    if is_encrypted(path) or (not path.exists() and _encrypt_new(path)):
        from sqlcipher3 import dbapi2 as sqlcipher
        conn = sqlcipher.connect(str(path))
        conn.row_factory = sqlcipher.Row
        # key pragma must precede any other statement; hex form avoids derivation
        conn.execute(f"PRAGMA key = \"x'{_master_key().hex()}'\"")
    else:
        conn = sqlite3.connect(str(path))
        conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    # Idempotent migrations for pre-existing databases (CREATE TABLE IF NOT EXISTS
    # doesn't alter existing tables). doc_type: 'document' | 'transcript' (T-TRANS/D-70,
    # user-designated at upload — never auto-detected).
    for migration in (
        "ALTER TABLE documents ADD COLUMN doc_type TEXT NOT NULL DEFAULT 'document'",
        # v0.3.0 (D-81): provenance for cloud-imported documents — JSON with source
        # service, source id, author, dates, meeting title, speakers. NULL = local.
        "ALTER TABLE documents ADD COLUMN source_json TEXT",
        # M-2 matter digest: extractor version this doc's facts were built with.
        # NULL = not yet digested at any version.
        "ALTER TABLE documents ADD COLUMN digest_version TEXT",
    ):
        try:
            conn.execute(migration)
            conn.commit()
        except Exception as e:  # sqlite3 and sqlcipher3 raise distinct OperationalErrors
            if type(e).__name__ != "OperationalError":
                raise
            pass  # column already present
    return conn


def slugify(name):
    """Path-safe slug: lowercase, non-alphanumeric -> '-', collapsed, trimmed."""
    return re.sub(r"[^a-z0-9]+", "-", (name or "").strip().lower()).strip("-")


# --- profile (UX-5 onboarding) -------------------------------------------------
# The attorney's LOCAL identity: name, practice areas, onboarded flag. Lives in the
# (SQLCipher-encrypted in production) catalog and never leaves the machine. JSON
# values keyed by name so new fields need no migration.

def get_profile(db_path=None):
    conn = _connect(db_path)
    try:
        rows = conn.execute("SELECT key, value FROM profile").fetchall()
        out = {}
        for r in rows:
            try:
                out[r["key"]] = json.loads(r["value"])
            except ValueError:
                pass  # a corrupt value is dropped, never fatal
        return out
    finally:
        conn.close()


def set_profile(values, db_path=None):
    """Upsert the given keys (a partial update — absent keys are untouched)."""
    conn = _connect(db_path)
    try:
        for k, v in (values or {}).items():
            conn.execute(
                "INSERT INTO profile (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (str(k), json.dumps(v)),
            )
        conn.commit()
    finally:
        conn.close()


def clear_profile(db_path=None):
    """Erase the whole profile (UX-6 erase-everything)."""
    conn = _connect(db_path)
    try:
        conn.execute("DELETE FROM profile")
        conn.commit()
    finally:
        conn.close()


# --- watched folders (UX-6 connectors) -------------------------------------------

def add_watch_folder(matter_slug, path, db_path=None):
    conn = _connect(db_path)
    try:
        cur = conn.execute(
            "INSERT INTO watch_folders (matter_slug, path, created) VALUES (?, ?, ?)",
            (matter_slug, str(path), _now()),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM watch_folders WHERE id = ?",
                           (cur.lastrowid,)).fetchone()
        return dict(row)
    except sqlite3.IntegrityError:
        raise ValueError("that folder is already watched for this matter")
    finally:
        conn.close()


def list_watch_folders(db_path=None):
    conn = _connect(db_path)
    try:
        rows = conn.execute("SELECT * FROM watch_folders ORDER BY id").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def remove_watch_folder(folder_id, db_path=None):
    conn = _connect(db_path)
    try:
        conn.execute("DELETE FROM watch_folders WHERE id = ?", (folder_id,))
        conn.commit()
    finally:
        conn.close()


# --- connections (v0.3.0 connectors, D-81) --------------------------------------
# A connection = one user-created link to an external service. The credential
# column holds keyvault.encrypt_secret() ciphertext ONLY — plaintext keys never
# touch the catalog, and remove_connection() deletes the row outright (the D-80
# disconnect-and-delete contract).

def add_connection(service, credential_blob, label=None, config=None, db_path=None):
    conn = _connect(db_path)
    try:
        cur = conn.execute(
            "INSERT INTO connections (service, label, credential, config, created) "
            "VALUES (?, ?, ?, ?, ?)",
            (service, label, credential_blob, json.dumps(config or {}), _now()),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM connections WHERE id = ?",
                           (cur.lastrowid,)).fetchone()
        return _connection_public(row)
    finally:
        conn.close()


def _connection_public(row):
    """A connection row with the credential ciphertext stripped (API/UI shape)."""
    out = {k: row[k] for k in row.keys() if k != "credential"}
    out["config"] = json.loads(out.get("config") or "{}")
    return out


def get_connection(conn_id, db_path=None):
    """Full row INCLUDING the credential ciphertext — connsync/adapters only."""
    conn = _connect(db_path)
    try:
        row = conn.execute("SELECT * FROM connections WHERE id = ?",
                           (conn_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_connections(db_path=None):
    """Public rows (no credential), newest first, with per-connection import counts."""
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            "SELECT c.*, (SELECT COUNT(*) FROM connection_items i "
            "WHERE i.connection_id = c.id) AS item_count "
            "FROM connections c ORDER BY c.id DESC").fetchall()
        return [_connection_public(r) for r in rows]
    finally:
        conn.close()


def touch_connection_sync(conn_id, error=None, db_path=None):
    """Stamp a sync attempt: last_sync on success, last_error on failure (kept
    until the next successful pass so the UI can show what went wrong)."""
    conn = _connect(db_path)
    try:
        if error is None:
            conn.execute("UPDATE connections SET last_sync = ?, last_error = NULL "
                         "WHERE id = ?", (_now(), conn_id))
        else:
            conn.execute("UPDATE connections SET last_error = ? WHERE id = ?",
                         (str(error)[:500], conn_id))
        conn.commit()
    finally:
        conn.close()


def remove_connection(conn_id, db_path=None):
    """Disconnect: delete the connection row (credential ciphertext gone) and its
    item ledger. Imported DOCUMENTS stay — they are the user's copies now."""
    conn = _connect(db_path)
    try:
        conn.execute("DELETE FROM connection_items WHERE connection_id = ?", (conn_id,))
        conn.execute("DELETE FROM connections WHERE id = ?", (conn_id,))
        conn.commit()
    finally:
        conn.close()


def connection_seen_ids(conn_id, db_path=None):
    """Source ids already imported for a connection (dedupe set)."""
    conn = _connect(db_path)
    try:
        rows = conn.execute("SELECT source_id FROM connection_items "
                            "WHERE connection_id = ?", (conn_id,)).fetchall()
        return {r["source_id"] for r in rows}
    finally:
        conn.close()


def record_connection_item(conn_id, source_id, doc_id, db_path=None):
    conn = _connect(db_path)
    try:
        conn.execute(
            "INSERT OR IGNORE INTO connection_items (connection_id, source_id, "
            "doc_id, imported) VALUES (?, ?, ?, ?)",
            (conn_id, str(source_id), doc_id, _now()))
        conn.commit()
    finally:
        conn.close()


# --- matters -----------------------------------------------------------------

def create_matter(display_name, db_path=None):
    name = (display_name or "").strip()
    if not name:
        raise ValueError("display_name is required")
    slug = slugify(name)
    if not slug:
        raise ValueError("display_name has no usable (alphanumeric) characters")
    conn = _connect(db_path)
    try:
        cur = conn.execute(
            "INSERT INTO matters (slug, display_name, created) VALUES (?, ?, ?)",
            (slug, name, _now()),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM matters WHERE id = ?", (cur.lastrowid,)).fetchone()
        return dict(row)
    except sqlite3.IntegrityError:
        raise ValueError(f"matter already exists: {name!r}")
    finally:
        conn.close()


def list_matters(db_path=None):
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            "SELECT m.*, (SELECT COUNT(*) FROM documents d WHERE d.matter_slug = m.slug) "
            "AS doc_count FROM matters m ORDER BY m.display_name"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_matter(slug, db_path=None):
    conn = _connect(db_path)
    try:
        row = conn.execute("SELECT * FROM matters WHERE slug = ?", (slug,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def rename_matter(slug, display_name, db_path=None):
    """Update a matter's display label only. The slug (the path/scope key for stored
    natives, KB rows, threads, holds) is immutable — renaming it would orphan data."""
    name = (display_name or "").strip()
    if not name:
        raise ValueError("display_name is required")
    conn = _connect(db_path)
    try:
        conn.execute("UPDATE matters SET display_name = ? WHERE slug = ?", (name, slug))
        conn.commit()
    finally:
        conn.close()


def delete_matter(slug, db_path=None):
    """Remove a matter row (catalog only). Callers must remove its documents + chunks
    first; this never touches a vector store or any document file."""
    conn = _connect(db_path)
    try:
        conn.execute("DELETE FROM matter_facts WHERE matter_slug = ?", (slug,))
        conn.execute("DELETE FROM fact_review WHERE matter_slug = ?", (slug,))
        conn.execute("DELETE FROM matters WHERE slug = ?", (slug,))
        conn.commit()
    finally:
        conn.close()


# --- documents ---------------------------------------------------------------

def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def add_document(matter_slug, file_path, db_path=None, filename=None, status="parsing",
                 doc_type="document", checksum=None, size_bytes=None, source_json=None):
    """Insert a documents row (default status 'parsing'); returns the row dict.
    doc_type: 'document' or 'transcript' (user-designated at upload, D-70).
    checksum/size_bytes: callers whose on-disk file is DEK-encrypted (D-73) pass the
    PLAINTEXT sha256/size here — manifests and certificates always describe the
    document, never the ciphertext. Default: hashed/stat'ed from disk, as before.
    source_json: provenance for cloud-imported documents (D-81); None = local."""
    file_path = Path(file_path)
    name = filename or file_path.name
    conn = _connect(db_path)
    try:
        cur = conn.execute(
            "INSERT INTO documents (matter_slug, filename, stored_path, checksum, size_bytes, "
            "status, reason, updated, doc_type, source_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (matter_slug, name, str(file_path), checksum or _sha256(file_path),
             size_bytes if size_bytes is not None else file_path.stat().st_size,
             status, None, _now(), doc_type, source_json),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM documents WHERE id = ?", (cur.lastrowid,)).fetchone()
        return dict(row)
    finally:
        conn.close()


def save_line_map(doc_id, entries, db_path=None):
    """Replace the transcript line map for a document. ``entries`` =
    [(page, line, char_start, char_end)] with offsets into the CLEAN page text (the
    same text chunks slice — so verified span offsets map straight through, D-70)."""
    conn = _connect(db_path)
    try:
        conn.execute("DELETE FROM transcript_lines WHERE doc_id = ?", (doc_id,))
        conn.executemany(
            "INSERT INTO transcript_lines (doc_id, page, line, char_start, char_end) "
            "VALUES (?, ?, ?, ?, ?)",
            [(doc_id, p, l, s, e) for p, l, s, e in entries])
        conn.commit()
    finally:
        conn.close()


def line_map_for_page(doc_id, page, db_path=None):
    """Ordered [(line, char_start, char_end)] for one transcript page ([] if none)."""
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            "SELECT line, char_start, char_end FROM transcript_lines "
            "WHERE doc_id = ? AND page = ? ORDER BY line", (doc_id, page)).fetchall()
        return [(r["line"], r["char_start"], r["char_end"]) for r in rows]
    finally:
        conn.close()


def delete_line_map(doc_id, db_path=None):
    conn = _connect(db_path)
    try:
        conn.execute("DELETE FROM transcript_lines WHERE doc_id = ?", (doc_id,))
        conn.commit()
    finally:
        conn.close()


# --- matter digest (M-2) -------------------------------------------------------
# matter_facts is PURE MACHINE OUTPUT — a function of (document, extractor_version),
# idempotently rebuildable. Human judgment lives ONLY in fact_review, keyed by a
# stable content hash so it survives re-extraction of the same fact. Absent review
# row = "proposed". The answer path never reads these tables (test_digest_fencing).

def replace_facts(doc_id, matter_slug, facts, extractor_version, db_path=None):
    """Atomically replace one document's facts and stamp documents.digest_version.
    Zero facts is a legitimate outcome (the stamp still records the doc as digested)."""
    if not matter_slug:
        raise ValueError("matter_slug is required")
    conn = _connect(db_path)
    try:
        conn.execute("DELETE FROM matter_facts WHERE doc_id = ?", (doc_id,))
        for f in facts:
            conn.execute(
                "INSERT INTO matter_facts (matter_slug, doc_id, fact_key, fact_type, "
                "value_json, page, char_start, char_end, span, extractor_version, created) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (matter_slug, doc_id, f["fact_key"], f["fact_type"],
                 json.dumps(f["value"]), f["page"], f["char_start"], f["char_end"],
                 f["span"], extractor_version, _now()))
        conn.execute("UPDATE documents SET digest_version = ? WHERE id = ?",
                     (extractor_version, doc_id))
        conn.commit()
    finally:
        conn.close()


def facts_for_matter(matter_slug, db_path=None):
    """All fact rows for one matter (joined with the document filename). The
    explicit matter_slug is the fence — there is no all-matters accessor."""
    if not matter_slug:
        raise ValueError("matter_slug is required")
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            "SELECT f.*, d.filename FROM matter_facts f "
            "JOIN documents d ON d.id = f.doc_id "
            "WHERE f.matter_slug = ? ORDER BY f.doc_id, f.page, f.char_start",
            (matter_slug,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def set_fact_review(matter_slug, fact_key, status, confirmed_date=None, db_path=None):
    """Upsert the attorney's judgment on one fact. status None deletes the row
    (revert to proposed)."""
    if not matter_slug:
        raise ValueError("matter_slug is required")
    if status not in ("confirmed", "dismissed", None):
        raise ValueError("status must be 'confirmed', 'dismissed', or None")
    conn = _connect(db_path)
    try:
        if status is None:
            conn.execute("DELETE FROM fact_review WHERE matter_slug = ? AND fact_key = ?",
                         (matter_slug, fact_key))
        else:
            conn.execute(
                "INSERT INTO fact_review (matter_slug, fact_key, status, confirmed_date, created) "
                "VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(matter_slug, fact_key) DO UPDATE SET "
                "status = excluded.status, confirmed_date = excluded.confirmed_date",
                (matter_slug, fact_key, status, confirmed_date, _now()))
        conn.commit()
    finally:
        conn.close()


def reviews_for_matter(matter_slug, db_path=None):
    if not matter_slug:
        raise ValueError("matter_slug is required")
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            "SELECT fact_key, status, confirmed_date FROM fact_review WHERE matter_slug = ?",
            (matter_slug,)).fetchall()
        return {r["fact_key"]: {"status": r["status"],
                                "confirmed_date": r["confirmed_date"]} for r in rows}
    finally:
        conn.close()


def prune_orphan_reviews(matter_slug, db_path=None):
    """Delete reviews whose fact no longer exists (changed on re-extraction)."""
    if not matter_slug:
        raise ValueError("matter_slug is required")
    conn = _connect(db_path)
    try:
        cur = conn.execute(
            "DELETE FROM fact_review WHERE matter_slug = ? AND fact_key NOT IN "
            "(SELECT fact_key FROM matter_facts WHERE matter_slug = ?)",
            (matter_slug, matter_slug))
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


def digest_progress(matter_slug, extractor_version, db_path=None):
    """How much of this matter is digested at the current extractor version."""
    if not matter_slug:
        raise ValueError("matter_slug is required")
    conn = _connect(db_path)
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS total, "
            "SUM(CASE WHEN digest_version = ? THEN 1 ELSE 0 END) AS done "
            "FROM documents WHERE matter_slug = ? AND status IN ('ready', 'needs_review')",
            (extractor_version, matter_slug)).fetchone()
        return {"done": row["done"] or 0, "total": row["total"] or 0}
    finally:
        conn.close()


def get_document(doc_id, db_path=None):
    conn = _connect(db_path)
    try:
        row = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_documents(matter_slug=None, db_path=None):
    conn = _connect(db_path)
    try:
        if matter_slug:
            rows = conn.execute("SELECT * FROM documents WHERE matter_slug = ? ORDER BY updated DESC",
                                (matter_slug,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM documents ORDER BY updated DESC").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def move_document_row(doc_id, matter_slug, filename, stored_path, db_path=None):
    """Re-file a document under another matter (UX-7 Document Hub filing): update the
    scope key + managed-copy location in one statement. Status resets to 'queued' —
    the caller re-ingests so the KB chunks land under the new matter scope."""
    conn = _connect(db_path)
    try:
        conn.execute(
            "UPDATE documents SET matter_slug = ?, filename = ?, stored_path = ?, "
            "status = 'queued', reason = NULL, updated = ? WHERE id = ?",
            (matter_slug, filename, str(stored_path), _now(), doc_id),
        )
        conn.commit()
    finally:
        conn.close()


def update_document(doc_id, status, reason=None, db_path=None):
    conn = _connect(db_path)
    try:
        conn.execute("UPDATE documents SET status = ?, reason = ?, updated = ? WHERE id = ?",
                     (status, reason, _now(), doc_id))
        conn.commit()
    finally:
        conn.close()


def delete_document(doc_id, db_path=None):
    conn = _connect(db_path)
    try:
        conn.execute("DELETE FROM matter_facts WHERE doc_id = ?", (doc_id,))
        conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
        conn.commit()
    finally:
        conn.close()


# --- threads / messages (chat history) ---------------------------------------

def create_thread(matter_slug, title, db_path=None):
    conn = _connect(db_path)
    try:
        now = _now()
        cur = conn.execute(
            "INSERT INTO threads (matter_slug, title, created, updated) VALUES (?, ?, ?, ?)",
            (matter_slug, title[:120], now, now),
        )
        conn.commit()
        return dict(conn.execute("SELECT * FROM threads WHERE id = ?", (cur.lastrowid,)).fetchone())
    finally:
        conn.close()


def add_message(thread_id, role, content, citations_json=None, db_path=None):
    conn = _connect(db_path)
    try:
        conn.execute(
            "INSERT INTO messages (thread_id, role, content, citations_json, created) "
            "VALUES (?, ?, ?, ?, ?)",
            (thread_id, role, content, citations_json, _now()),
        )
        conn.commit()
    finally:
        conn.close()


def touch_thread(thread_id, db_path=None):
    conn = _connect(db_path)
    try:
        conn.execute("UPDATE threads SET updated = ? WHERE id = ?", (_now(), thread_id))
        conn.commit()
    finally:
        conn.close()


def list_threads(db_path=None):
    conn = _connect(db_path)
    try:
        rows = conn.execute("SELECT * FROM threads ORDER BY updated DESC").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_thread_messages(thread_id, db_path=None):
    conn = _connect(db_path)
    try:
        rows = conn.execute("SELECT * FROM messages WHERE thread_id = ? ORDER BY id",
                            (thread_id,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# --- retention: legal holds + hash-chained audit log (Move 4, D-72) -----------------

def place_hold(matter_slug, reason, db_path=None):
    """Create a legal hold on a matter. While ANY unreleased hold exists, disposition
    and document deletion are refused (FRCP 37(e) preservation)."""
    conn = _connect(db_path)
    try:
        conn.execute("INSERT INTO legal_holds (matter_slug, reason, created) VALUES (?, ?, ?)",
                     (matter_slug, reason, _now()))
        conn.commit()
    finally:
        conn.close()
    audit_append("hold_placed", matter_slug, reason, db_path=db_path)


def release_hold(matter_slug, reason, db_path=None):
    """Release all active holds on a matter (with the release reason recorded)."""
    conn = _connect(db_path)
    try:
        conn.execute("UPDATE legal_holds SET released = ?, released_reason = ? "
                     "WHERE matter_slug = ? AND released IS NULL",
                     (_now(), reason, matter_slug))
        conn.commit()
    finally:
        conn.close()
    audit_append("hold_released", matter_slug, reason, db_path=db_path)


def active_hold(matter_slug, db_path=None):
    """The oldest unreleased hold row for a matter, or None."""
    conn = _connect(db_path)
    try:
        row = conn.execute("SELECT * FROM legal_holds WHERE matter_slug = ? AND "
                           "released IS NULL ORDER BY id LIMIT 1", (matter_slug,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def audit_append(event, matter_slug=None, detail=None, db_path=None):
    """Append a tamper-EVIDENT audit entry: entry_hash = sha256(prev_hash | ts | event |
    matter | detail). Editing or deleting any prior row breaks every later hash
    (RFC 6962-style chain) — verifiable locally with no server. Returns the entry hash."""
    conn = _connect(db_path)
    try:
        row = conn.execute("SELECT entry_hash FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
        prev = row["entry_hash"] if row else "genesis"
        ts = _now()
        material = "|".join([prev, ts, event, matter_slug or "", detail or ""])
        entry = hashlib.sha256(material.encode("utf-8")).hexdigest()
        conn.execute("INSERT INTO audit_log (prev_hash, entry_hash, ts, event, "
                     "matter_slug, detail) VALUES (?, ?, ?, ?, ?, ?)",
                     (prev, entry, ts, event, matter_slug, detail))
        conn.commit()
        return entry
    finally:
        conn.close()


def audit_entries(matter_slug=None, db_path=None):
    conn = _connect(db_path)
    try:
        if matter_slug:
            rows = conn.execute("SELECT * FROM audit_log WHERE matter_slug = ? ORDER BY id",
                                (matter_slug,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM audit_log ORDER BY id").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def verify_audit_chain(db_path=None):
    """(ok, first_bad_id): recompute every hash in order; any edited/removed/reordered
    entry breaks the chain at the first affected row."""
    conn = _connect(db_path)
    try:
        rows = conn.execute("SELECT * FROM audit_log ORDER BY id").fetchall()
    finally:
        conn.close()
    prev = "genesis"
    for r in rows:
        material = "|".join([prev, r["ts"], r["event"], r["matter_slug"] or "",
                             r["detail"] or ""])
        if r["prev_hash"] != prev or \
                hashlib.sha256(material.encode("utf-8")).hexdigest() != r["entry_hash"]:
            return False, r["id"]
        prev = r["entry_hash"]
    return True, None


def threads_for_matter(matter_slug, db_path=None):
    conn = _connect(db_path)
    try:
        rows = conn.execute("SELECT * FROM threads WHERE matter_slug = ? ORDER BY id",
                            (matter_slug,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def messages_for_thread(thread_id, db_path=None):
    conn = _connect(db_path)
    try:
        rows = conn.execute("SELECT * FROM messages WHERE thread_id = ? ORDER BY id",
                            (thread_id,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def delete_threads_for_matter(matter_slug, db_path=None):
    """Remove a matter's chat threads + messages (disposition path only)."""
    conn = _connect(db_path)
    try:
        ids = [r["id"] for r in conn.execute(
            "SELECT id FROM threads WHERE matter_slug = ?", (matter_slug,)).fetchall()]
        if ids:
            q = ",".join("?" * len(ids))
            conn.execute(f"DELETE FROM messages WHERE thread_id IN ({q})", ids)
            conn.execute(f"DELETE FROM threads WHERE id IN ({q})", ids)
        conn.commit()
        return len(ids)
    finally:
        conn.close()
