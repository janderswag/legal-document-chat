"""M2-3 — Embed the M2-2 chunks with bge-m3 (system Ollama) and store in LanceDB.

Each chunk's ``embedding_text`` (the SAC-prefixed text — the D-18 anti-DRM signal)
is embedded via the system Ollama at 127.0.0.1:11434 (bge-m3, 1024-dim, D-11), NOT
the bare ``text``. Vectors + full payload {source_filename, matter, page_number,
section, char_start, char_end, text} are written to an embedded LanceDB table. The
text + offsets are retained in the payload because M2-6 needs them for mechanical
span-level citation verification.

The LanceDB store contains document text -> it must live under a git-ignored path
(D-28). Scope (M2-3): embed + store + a basic similarity sanity check only — no
metadata-filter, reranker, answering LLM, or HTTP surface (those are M2-4..M2-7).
"""

import json
import os
import urllib.request
from pathlib import Path

import lancedb
import pyarrow as pa

EMBED_DIM = 1024


def ollama_url():
    """Base URL for the Ollama server, resolved at CALL time.

    Default = the host loopback ``http://127.0.0.1:11434`` (D-11) — the
    non-containerized path is unchanged. The container overrides it via the
    ``LDI_OLLAMA_URL`` env (compose sets ``http://host.docker.internal:11434``) to
    reach the SAME host Ollama; this never changes Ollama's bind and is deliberately
    NOT named ``OLLAMA_HOST`` (Ollama's own server-bind var, which must stay unset)."""
    return os.environ.get("LDI_OLLAMA_URL", "http://127.0.0.1:11434")

_SCHEMA = pa.schema([
    pa.field("vector", pa.list_(pa.float32(), EMBED_DIM)),
    pa.field("source_filename", pa.string()),
    pa.field("matter", pa.string()),
    pa.field("page_number", pa.int64()),
    pa.field("section", pa.string()),
    pa.field("char_start", pa.int64()),
    pa.field("char_end", pa.int64()),
    pa.field("text", pa.string()),
    # Move 1d (D-69): real metadata for filtering/search. document_type is the DOCUMENT
    # kind (contract/pleading/transcript/document...); provenance is the extractor path
    # (pymupdf/tesseract/txt) that previously squatted document_type; doc_date is an
    # explicitly-stated document date when known ("" otherwise — never inferred).
    pa.field("document_type", pa.string()),
    pa.field("provenance", pa.string()),
    pa.field("doc_date", pa.string()),
])


def embed_texts(texts, model="bge-m3", host=None):
    """Embed a list of strings via the Ollama embed API -> list of vectors. ``host``
    defaults to ``ollama_url()`` (host loopback, or the container override)."""
    host = host or ollama_url()
    payload = json.dumps({"model": model, "input": list(texts)}).encode("utf-8")
    req = urllib.request.Request(
        f"{host}/api/embed", data=payload, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req) as resp:
        return json.load(resp)["embeddings"]


def build_store(chunks_path, db_path, table_name="chunks"):
    """Embed every chunk's embedding_text and (over)write a LanceDB table. Returns the table."""
    chunks = [json.loads(l) for l in open(chunks_path, encoding="utf-8") if l.strip()]
    vectors = embed_texts([c["embedding_text"] for c in chunks])
    if any(len(v) != EMBED_DIM for v in vectors):
        raise ValueError("embedding dimension mismatch (expected 1024 from bge-m3)")

    rows = [_row(c, vec) for c, vec in zip(chunks, vectors)]

    db = lancedb.connect(str(db_path))
    return db.create_table(table_name, data=rows, schema=_SCHEMA, mode="overwrite")


def open_table(db_path, table_name="chunks"):
    """Open an existing LanceDB table."""
    return lancedb.connect(str(db_path)).open_table(table_name)


def _row(c, vec):
    return {
        "vector": vec, "source_filename": c["source_filename"], "matter": c["matter"],
        "page_number": c["page_number"], "section": c["section"],
        "char_start": c["char_start"], "char_end": c["char_end"], "text": c["text"],
        "document_type": c.get("document_type", "document"),
        "provenance": c.get("provenance", c.get("source", "")),
        "doc_date": c.get("doc_date", ""),
    }


def _rows_from_chunks(chunks):
    vectors = embed_texts([c["embedding_text"] for c in chunks])
    if any(len(v) != EMBED_DIM for v in vectors):
        raise ValueError("embedding dimension mismatch (expected 1024 from bge-m3)")
    return [_row(c, vec) for c, vec in zip(chunks, vectors)]


def add_chunks(chunks, db_path, table_name="chunks"):
    """Embed and APPEND chunks to a LanceDB table (created if absent). Used by the KB
    so one document's chunks are added without overwriting others (unlike build_store)."""
    if not chunks:
        return
    rows = _rows_from_chunks(chunks)
    db = lancedb.connect(str(db_path))
    if table_name in db.table_names():
        table = db.open_table(table_name)
        if "document_type" not in [f.name for f in table.schema]:
            # Pre-1d store: appending new-schema rows would corrupt/fail. Fail loud
            # with the migration path instead (D-69).
            raise RuntimeError(
                f"store at {db_path} predates the 1d schema (no document_type column); "
                "rebuild it via reingest_kb.py before adding documents")
        table.add(rows)
    else:
        db.create_table(table_name, data=rows, schema=_SCHEMA)


def delete_doc(db_path, source_filename, matter, table_name="chunks"):
    """Delete one document's chunks from a table, scoped to (source_filename, matter).
    Values are single-quote-escaped (they come from the catalog, not raw user text)."""
    db = lancedb.connect(str(db_path))
    if table_name not in db.table_names():
        return
    fn = source_filename.replace("'", "''")
    mt = matter.replace("'", "''")
    db.open_table(table_name).delete(f"source_filename = '{fn}' AND matter = '{mt}'")
