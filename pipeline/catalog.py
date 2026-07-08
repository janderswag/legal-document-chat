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
    try:
        conn.execute("ALTER TABLE documents ADD COLUMN doc_type TEXT NOT NULL DEFAULT 'document'")
        conn.commit()
    except Exception as e:  # sqlite3 and sqlcipher3 raise distinct OperationalErrors
        if type(e).__name__ != "OperationalError":
            raise
        pass  # column already present
    return conn


def slugify(name):
    """Path-safe slug: lowercase, non-alphanumeric -> '-', collapsed, trimmed."""
    return re.sub(r"[^a-z0-9]+", "-", (name or "").strip().lower()).strip("-")


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


def delete_matter(slug, db_path=None):
    """Remove a matter row (catalog only). Callers must remove its documents + chunks
    first; this never touches a vector store or any document file."""
    conn = _connect(db_path)
    try:
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
                 doc_type="document", checksum=None, size_bytes=None):
    """Insert a documents row (default status 'parsing'); returns the row dict.
    doc_type: 'document' or 'transcript' (user-designated at upload, D-70).
    checksum/size_bytes: callers whose on-disk file is DEK-encrypted (D-73) pass the
    PLAINTEXT sha256/size here — manifests and certificates always describe the
    document, never the ciphertext. Default: hashed/stat'ed from disk, as before."""
    file_path = Path(file_path)
    name = filename or file_path.name
    conn = _connect(db_path)
    try:
        cur = conn.execute(
            "INSERT INTO documents (matter_slug, filename, stored_path, checksum, size_bytes, "
            "status, reason, updated, doc_type) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (matter_slug, name, str(file_path), checksum or _sha256(file_path),
             size_bytes if size_bytes is not None else file_path.stat().st_size,
             status, None, _now(), doc_type),
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
