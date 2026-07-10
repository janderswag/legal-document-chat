# Matter Digest (M-2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** At ingest, extract span-verified facts (parties, dated items, amounts, defined terms, key refs) per document into `matter_facts`, and render an instant matter overview (deadlines with attorney-supplies-the-date confirmation, timeline, parties & amounts) with zero LLM calls at read time.

**Architecture:** New `pipeline/digest.py` (page reconstruction from the chunk store → one qwen3:14b JSON-schema call per ~2–4-page group → mechanical write gate via `verifier.locate_span`) hooked into `ingest_worker._run` after a successful ingest, plus a one-shot startup backfill thread. New `pipeline/routes_digest.py` serves the overview and confirm/dismiss API. `app.js` renders layout B (overview above the fold). The answer engine is untouched; fencing tests prove it.

**Tech Stack:** Python 3 / FastAPI / SQLite (SQLCipher in prod) / LanceDB / Ollama qwen3:14b structured output. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-07-10-matter-digest-design.md` — owner decisions there are settled.

## Global Constraints

- Hard rules (project CLAUDE.md): loopback only; no cloud calls; synthetic documents only; no new dependencies; surgical diffs; secrets never committed.
- The answer path (`answering.py`, `verifier.py`, `retrieval.py`) must not import or read any digest code or table. This cycle adds NO retrieval behavior.
- `date_iso` is stored only when `date_kind == "explicit"` and the value matches `^\d{4}-\d{2}-\d{2}$`. docuchat never computes, infers, or chains a date.
- No fact row is written unless its span mechanically locates in the reconstructed page text (`verifier.locate_span`); failures are dropped and counted.
- Every new catalog accessor takes `matter_slug` (or `doc_id`) explicitly; empty `matter_slug` raises `ValueError`.
- Kill switch: env `LDI_MATTER_DIGEST=0` disables extraction (hook + backfill). Read-side routes still serve whatever exists.
- The UI id `matter-digest` is TAKEN (deposition digest). The new container is `matter-overview`.
- Tests: `unittest` style, `pipeline/tests/test_*.py`, run with `python3 -m pytest tests/<file> -v` from `pipeline/`. Follow the `test_move_document.py` setUp pattern (swap `catalog.DEFAULT_DB` to a tmp path).
- Commit after every task with a `feat:`/`test:` message ending in the Claude co-author line.

---

### Task 1: Catalog — `matter_facts` + `fact_review` schema, accessors, deletion cascades

**Files:**
- Modify: `pipeline/catalog.py` (schema block `_SCHEMA` ~line 65-153; migrations in `_connect` ~line 176; new accessor section after the transcript_lines section ~line 520; `delete_document` ~line 575; `delete_matter` ~line 443)
- Test: `pipeline/tests/test_digest_catalog.py` (create)

**Interfaces:**
- Consumes: existing `catalog._connect`, `_now()`, `sqlite3.Row` dict-style rows.
- Produces (Task 2/4 rely on these exact signatures):
  - `catalog.replace_facts(doc_id, matter_slug, facts, extractor_version, db_path=None)` — `facts` items: `{"fact_type","value","page","char_start","char_end","span","fact_key"}` (`value` is a dict, stored as `value_json`). Deletes the doc's old rows, inserts new ones, stamps `documents.digest_version`, all in one transaction.
  - `catalog.facts_for_matter(matter_slug, db_path=None) -> list[dict]` — fact rows joined with `documents.filename`, ordered by doc_id, page, char_start. Empty `matter_slug` → `ValueError`.
  - `catalog.set_fact_review(matter_slug, fact_key, status, confirmed_date=None, db_path=None)` — upsert; `status` must be `"confirmed"`, `"dismissed"`, or `None` (None deletes the row = revert to proposed); anything else → `ValueError`.
  - `catalog.reviews_for_matter(matter_slug, db_path=None) -> dict[fact_key, {"status","confirmed_date"}]`
  - `catalog.prune_orphan_reviews(matter_slug, db_path=None) -> int` (rows deleted)
  - `catalog.digest_progress(matter_slug, extractor_version, db_path=None) -> {"done": int, "total": int}` — total = this matter's docs with status in ('ready','needs_review'); done = those with `digest_version == extractor_version`.

- [ ] **Step 1: Write the failing tests**

```python
"""M-2 matter digest — catalog layer: span-pointered fact rows (pure machine output,
rebuildable), attorney review state that survives re-extraction, hard deletion
cascades (doc delete -> facts die; matter delete -> facts + reviews die)."""

import sys
import tempfile
import unittest
from pathlib import Path

PIPELINE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPELINE_DIR))
import catalog  # noqa: E402


def _fact(key="k1", ftype="date_event", page=1):
    return {"fact_type": ftype, "value": {"kind": "deadline", "label": "Answer due",
            "date_text": "within 30 days", "date_iso": None,
            "date_kind": "relative", "anchor": "service"},
            "page": page, "char_start": 10, "char_end": 25,
            "span": "within 30 days", "fact_key": key}


class TestDigestCatalog(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._cat, catalog.DEFAULT_DB = catalog.DEFAULT_DB, self.tmp / "cat.db"
        catalog.create_matter("Nimbus Dispute")
        self.doc = catalog.add_document("nimbus-dispute", "msa.pdf",
                                        self.tmp / "msa.pdf", status="ready")

    def tearDown(self):
        catalog.DEFAULT_DB = self._cat

    def test_replace_facts_is_idempotent_and_stamps_version(self):
        catalog.replace_facts(self.doc["id"], "nimbus-dispute", [_fact("a"), _fact("b")], "v1")
        catalog.replace_facts(self.doc["id"], "nimbus-dispute", [_fact("a")], "v2")
        rows = catalog.facts_for_matter("nimbus-dispute")
        self.assertEqual([r["fact_key"] for r in rows], ["a"])          # replaced, not appended
        self.assertEqual(rows[0]["extractor_version"], "v2")
        self.assertEqual(rows[0]["filename"], "msa.pdf")                # join works
        d = catalog.get_document(self.doc["id"])
        self.assertEqual(d["digest_version"], "v2")

    def test_facts_require_matter_slug(self):
        with self.assertRaises(ValueError):
            catalog.facts_for_matter("")

    def test_review_upsert_survives_reextraction_and_prunes_orphans(self):
        catalog.replace_facts(self.doc["id"], "nimbus-dispute", [_fact("a"), _fact("gone")], "v1")
        catalog.set_fact_review("nimbus-dispute", "a", "confirmed", "2026-07-24")
        catalog.set_fact_review("nimbus-dispute", "gone", "dismissed")
        # re-extraction: fact "gone" no longer produced
        catalog.replace_facts(self.doc["id"], "nimbus-dispute", [_fact("a")], "v1")
        pruned = catalog.prune_orphan_reviews("nimbus-dispute")
        self.assertEqual(pruned, 1)
        reviews = catalog.reviews_for_matter("nimbus-dispute")
        self.assertEqual(reviews["a"], {"status": "confirmed", "confirmed_date": "2026-07-24"})
        self.assertNotIn("gone", reviews)

    def test_review_status_validated_and_none_reverts(self):
        catalog.replace_facts(self.doc["id"], "nimbus-dispute", [_fact("a")], "v1")
        with self.assertRaises(ValueError):
            catalog.set_fact_review("nimbus-dispute", "a", "approved")
        catalog.set_fact_review("nimbus-dispute", "a", "dismissed")
        catalog.set_fact_review("nimbus-dispute", "a", None)   # undo -> proposed
        self.assertEqual(catalog.reviews_for_matter("nimbus-dispute"), {})

    def test_delete_document_cascades_facts(self):
        catalog.replace_facts(self.doc["id"], "nimbus-dispute", [_fact("a")], "v1")
        catalog.delete_document(self.doc["id"])
        self.assertEqual(catalog.facts_for_matter("nimbus-dispute"), [])

    def test_delete_matter_cascades_facts_and_reviews(self):
        catalog.replace_facts(self.doc["id"], "nimbus-dispute", [_fact("a")], "v1")
        catalog.set_fact_review("nimbus-dispute", "a", "confirmed", "2026-07-24")
        catalog.delete_matter("nimbus-dispute")
        conn = catalog._connect()
        try:
            for table in ("matter_facts", "fact_review"):
                n = conn.execute(f"SELECT COUNT(*) c FROM {table} WHERE matter_slug = ?",
                                 ("nimbus-dispute",)).fetchone()["c"]
                self.assertEqual(n, 0, table)
        finally:
            conn.close()

    def test_digest_progress(self):
        p = catalog.digest_progress("nimbus-dispute", "v1")
        self.assertEqual(p, {"done": 0, "total": 1})
        catalog.replace_facts(self.doc["id"], "nimbus-dispute", [], "v1")  # zero facts still counts done
        p = catalog.digest_progress("nimbus-dispute", "v1")
        self.assertEqual(p, {"done": 1, "total": 1})


if __name__ == "__main__":
    unittest.main(verbosity=2)
```

Note: check `catalog.add_document`'s actual signature first (`grep -n "def add_document" catalog.py`) and adjust the call in `setUp` to match (it may take keyword args like `checksum`/`size_bytes`; pass the minimum it requires, status "ready" possibly via a follow-up `update_document`).

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ~/legal-document-chat/pipeline && python3 -m pytest tests/test_digest_catalog.py -v`
Expected: FAIL — `no such table: matter_facts` / `AttributeError: module 'catalog' has no attribute 'replace_facts'`

- [ ] **Step 3: Implement**

Append to `_SCHEMA` in `catalog.py` (before the closing `"""`):

```sql
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
```

Add to the migration tuple in `_connect` (alongside `doc_type` / `source_json`):

```python
        # M-2 matter digest: extractor version this doc's facts were built with.
        # NULL = not yet digested at any version.
        "ALTER TABLE documents ADD COLUMN digest_version TEXT",
```

New accessor section (place after the transcript_lines helpers, following the module's conn/try/finally style):

```python
# --- matter digest (M-2) -------------------------------------------------------
# matter_facts is PURE MACHINE OUTPUT — a function of (document, extractor_version),
# idempotently rebuildable. Human judgment lives ONLY in fact_review, keyed by a
# stable content hash so it survives re-extraction of the same fact. Absent review
# row = "proposed". The answer path never reads these tables (test_digest_fencing).

def replace_facts(doc_id, matter_slug, facts, extractor_version, db_path=None):
    """Atomically replace one document's facts and stamp documents.digest_version.
    Zero facts is a legitimate outcome (the stamp still records the doc as digested)."""
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
```

Cascades — add one line inside `delete_document` (before commit):

```python
        conn.execute("DELETE FROM matter_facts WHERE doc_id = ?", (doc_id,))
```

and two inside `delete_matter` (before commit):

```python
        conn.execute("DELETE FROM matter_facts WHERE matter_slug = ?", (slug,))
        conn.execute("DELETE FROM fact_review WHERE matter_slug = ?", (slug,))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_digest_catalog.py -v`
Expected: all PASS

- [ ] **Step 5: Run the full existing suite (schema change touches every _connect)**

Run: `python3 -m pytest tests/ -x -q`
Expected: no regressions

- [ ] **Step 6: Commit**

```bash
git add pipeline/catalog.py pipeline/tests/test_digest_catalog.py
git commit -m "feat(digest): matter_facts + fact_review schema, accessors, deletion cascades"
```

---

### Task 2: `digest.py` — page reconstruction, extraction call, mechanical write gate

**Files:**
- Create: `pipeline/digest.py`
- Test: `pipeline/tests/test_digest_gate.py` (create)

**Interfaces:**
- Consumes: `verifier.locate_span(chunk_text, span)`, `verifier._norm_map(text) -> (normalized, offset_map)`, `embed_store.open_table(db_path)` / `ollama_url()`, `catalog.replace_facts` / `prune_orphan_reviews` / `get_document` (Task 1), `activity.chat_recent()`.
- Produces (Tasks 3/4/7 rely on):
  - `digest.EXTRACTOR_VERSION` — `"digest-v1 " + DIGEST_MODEL` (bump the `v1` on any prompt/schema change).
  - `digest.enabled() -> bool` — env `LDI_MATTER_DIGEST` != "0".
  - `digest.fact_key(doc_id, fact_type, page, span) -> str` — sha256 hex over `f"{doc_id}|{fact_type}|{page}|{norm(span)}"`.
  - `digest.pages_from_store(db_path, filename, matter) -> list[{"page_number": int, "page_text": str}]`
  - `digest.gate_facts(raw_facts, group_pages, doc_id) -> (verified: list, dropped: int)` — verified items are `replace_facts`-shaped.
  - `digest.extract_for_document(doc_id, db_path, catalog_db=None) -> {"extracted": int, "dropped": int} | None` — None if doc missing/disabled.
  - `digest._extract_call(group_text) -> list[dict]` — the ONLY function tests monkeypatch (raw LLM output).

- [ ] **Step 1: Write the failing tests**

```python
"""M-2 write gate: the LLM proposes, verifier.locate_span disposes. A fabricated
span never becomes a row; a truthful span lands with mechanical page offsets.
date_iso survives only when explicit. Page reconstruction round-trips chunk tiling."""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PIPELINE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPELINE_DIR))
import catalog  # noqa: E402
import digest  # noqa: E402

PAGE1 = ("MASTER SERVICE AGREEMENT dated March 1, 2026 between Nimbus Analytics LLC "
         "(“Provider”) and Pemberton Logistics Inc. Recipient may cure within "
         "thirty (30) days after receipt of written notice of termination.")


def _raw(**kw):
    base = {"fact_type": "date_event", "span": "within thirty (30) days after receipt",
            "page": 1, "kind": "deadline", "label": "Cure period",
            "date_text": "within thirty (30) days after receipt",
            "date_iso": "", "date_kind": "relative", "anchor": "receipt of notice"}
    base.update(kw)
    return base


class TestGate(unittest.TestCase):
    def setUp(self):
        self.pages = [{"page_number": 1, "page_text": PAGE1}]

    def test_verified_span_becomes_fact_with_mechanical_offsets(self):
        verified, dropped = digest.gate_facts([_raw()], self.pages, doc_id=7)
        self.assertEqual(dropped, 0)
        f = verified[0]
        self.assertEqual(f["page"], 1)
        self.assertEqual(PAGE1[f["char_start"]:f["char_end"]].lower()[:12], "within thirt")
        self.assertEqual(f["value"]["kind"], "deadline")
        self.assertEqual(f["fact_key"], digest.fact_key(7, "date_event", 1, f["span"]))

    def test_fabricated_span_dropped_and_counted(self):
        verified, dropped = digest.gate_facts(
            [_raw(span="the fee shall be ten million dollars")], self.pages, doc_id=7)
        self.assertEqual((verified, dropped), ([], 1))

    def test_date_iso_only_when_explicit(self):
        raw = _raw(span="dated March 1, 2026", date_text="March 1, 2026",
                   date_kind="relative", date_iso="2026-03-01")
        verified, _ = digest.gate_facts([raw], self.pages, doc_id=7)
        self.assertIsNone(verified[0]["value"]["date_iso"])   # relative -> stripped
        raw = _raw(span="dated March 1, 2026", date_text="March 1, 2026",
                   date_kind="explicit", date_iso="2026-03-01")
        verified, _ = digest.gate_facts([raw], self.pages, doc_id=7)
        self.assertEqual(verified[0]["value"]["date_iso"], "2026-03-01")
        raw = _raw(date_kind="explicit", date_iso="March next year")
        verified, _ = digest.gate_facts([raw], self.pages, doc_id=7)
        self.assertIsNone(verified[0]["value"]["date_iso"])   # malformed -> stripped

    def test_wrong_reported_page_recovers_by_search(self):
        pages = [{"page_number": 1, "page_text": "nothing here"},
                 {"page_number": 2, "page_text": PAGE1}]
        verified, dropped = digest.gate_facts([_raw(page=1)], pages, doc_id=7)
        self.assertEqual(dropped, 0)
        self.assertEqual(verified[0]["page"], 2)              # page is where it was FOUND

    def test_required_value_fields_enforced(self):
        verified, dropped = digest.gate_facts(
            [{"fact_type": "party", "span": "Nimbus Analytics LLC", "page": 1}],
            self.pages, doc_id=7)                              # party without a name
        self.assertEqual((verified, dropped), ([], 1))


class TestExtractForDocument(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._cat, catalog.DEFAULT_DB = catalog.DEFAULT_DB, self.tmp / "cat.db"
        catalog.create_matter("Nimbus Dispute")
        self.doc = catalog.add_document("nimbus-dispute", "msa.pdf",
                                        self.tmp / "msa.pdf", status="ready")

    def tearDown(self):
        catalog.DEFAULT_DB = self._cat

    def test_extracts_writes_and_stamps(self):
        with mock.patch.object(digest, "pages_from_store",
                               return_value=[{"page_number": 1, "page_text": PAGE1}]), \
             mock.patch.object(digest, "_extract_call",
                               return_value=[_raw(), _raw(span="not in the doc at all")]), \
             mock.patch.object(digest, "_yield_to_chat"):
            out = digest.extract_for_document(self.doc["id"], self.tmp / "kb")
        self.assertEqual(out, {"extracted": 1, "dropped": 1})
        rows = catalog.facts_for_matter("nimbus-dispute")
        self.assertEqual(len(rows), 1)
        self.assertEqual(catalog.get_document(self.doc["id"])["digest_version"],
                         digest.EXTRACTOR_VERSION)

    def test_disabled_by_env(self):
        with mock.patch.dict("os.environ", {"LDI_MATTER_DIGEST": "0"}):
            self.assertIsNone(digest.extract_for_document(self.doc["id"], self.tmp / "kb"))


class TestPageGrouping(unittest.TestCase):
    def test_groups_respect_page_and_char_budget(self):
        pages = [{"page_number": i, "page_text": "x" * 3000} for i in range(1, 8)]
        groups = digest._groups(pages, max_chars=6000, max_pages=4)
        self.assertTrue(all(len(g) <= 4 for g in groups))
        self.assertTrue(all(sum(len(p["page_text"]) for p in g) <= 6000 or len(g) == 1
                            for g in groups))
        self.assertEqual(sum(len(g) for g in groups), 7)       # every page exactly once


if __name__ == "__main__":
    unittest.main(verbosity=2)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_digest_gate.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'digest'`

- [ ] **Step 3: Implement `pipeline/digest.py`**

```python
"""M-2 matter digest — span-verified fact extraction at ingest (design spec
docs/superpowers/specs/2026-07-10-matter-digest-design.md).

The LLM proposes facts; verifier.locate_span disposes. Nothing enters matter_facts
on the model's word alone: every span must mechanically locate in the reconstructed
clean page text, so extraction errors become recall loss, never precision loss.
date_iso is kept only when the date is explicit — docuchat never computes a date.
Read-side only: answering.py/retrieval.py have no import path here (test_digest_fencing).
"""

import hashlib
import json
import logging
import os
import re
import threading
import time
import urllib.request

import activity
import catalog
import verifier
from embed_store import ollama_url, open_table

log = logging.getLogger("docuchat.digest")

DIGEST_MODEL = os.environ.get("LDI_CHAT_MODEL", "qwen3:14b")
EXTRACTOR_VERSION = "digest-v1 " + DIGEST_MODEL   # bump v1 on any prompt/schema change
KEEP_ALIVE = "30m"
NUM_CTX = 8192
_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Minimum payload per fact type — a fact missing its defining field is dropped.
_REQUIRED = {"party": ("name",), "date_event": ("kind", "label", "date_text"),
             "amount": ("value",), "defined_term": ("term",), "key_ref": ("ref_value",)}
_VALUE_KEYS = {
    "party": ("name", "role", "org_form"),
    "date_event": ("kind", "label", "date_text", "date_iso", "date_kind", "anchor"),
    "amount": ("value", "currency", "purpose"),
    "defined_term": ("term",),
    "key_ref": ("ref_type", "ref_value"),
}

_SYSTEM = """You extract facts from legal documents into JSON. Rules:
- For EVERY fact, copy the source sentence fragment VERBATIM into "span" — exactly as
  written, including punctuation. A fact whose span is not an exact quote is discarded.
- "page" is the number from the "=== page N ===" marker the span appears under.
- fact_type "party": name, role (e.g. provider/client/plaintiff/defendant/landlord),
  org_form (LLC/Inc/individual/...).
- fact_type "date_event": kind is "event" (something that happened), "obligation"
  (a duty with a due date), or "deadline" (a cutoff after which rights are lost).
  label is a short neutral description. date_text is the verbatim date language.
  date_kind is "explicit" (a complete calendar date is written), "relative"
  (counted from another event), or "conditional". date_iso (YYYY-MM-DD) ONLY when
  date_kind is "explicit" — NEVER compute, infer, or convert a relative date.
  anchor is what a relative date counts from.
- fact_type "amount": value (as written), currency, purpose.
- fact_type "defined_term": term (the defined phrase).
- fact_type "key_ref": ref_type (invoice/claim/case/section/...), ref_value.
- Extract facts stated in the text only. Do not add, summarize, or conclude."""

_FORMAT = {
    "type": "object",
    "properties": {"facts": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "fact_type": {"type": "string",
                          "enum": ["party", "date_event", "amount",
                                   "defined_term", "key_ref"]},
            "span": {"type": "string"}, "page": {"type": "integer"},
            "name": {"type": "string"}, "role": {"type": "string"},
            "org_form": {"type": "string"}, "kind": {"type": "string"},
            "label": {"type": "string"}, "date_text": {"type": "string"},
            "date_iso": {"type": "string"}, "date_kind": {"type": "string"},
            "anchor": {"type": "string"}, "value": {"type": "string"},
            "currency": {"type": "string"}, "purpose": {"type": "string"},
            "term": {"type": "string"}, "ref_type": {"type": "string"},
            "ref_value": {"type": "string"},
        },
        "required": ["fact_type", "span", "page"]}}},
    "required": ["facts"],
}


def enabled():
    return os.environ.get("LDI_MATTER_DIGEST", "1") != "0"


def _span_norm(span):
    return verifier._norm_map(span)[0].strip()


def fact_key(doc_id, fact_type, page, span):
    """Stable identity for fact_review: survives re-extraction of the same fact."""
    raw = f"{doc_id}|{fact_type}|{page}|{_span_norm(span)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def pages_from_store(db_path, filename, matter):
    """Rebuild clean page texts from the doc's PROSE chunks (they tile each page's
    text with page-relative offsets — kb_ingest._chunk_pages contract). Table chunks
    are excluded: their offsets index the table markdown, not the page."""
    fn = str(filename).replace("'", "''")
    mt = str(matter).replace("'", "''")
    try:
        rows = (open_table(db_path).search()
                .where(f"source_filename = '{fn}' AND matter = '{mt}' "
                       f"AND document_type != 'table'")
                .select(["page_number", "char_start", "char_end", "text"])
                .limit(100000).to_arrow().to_pylist())
    except Exception:
        log.exception("digest: chunk read failed for %s", filename)
        return []
    by_page = {}
    for r in rows:
        by_page.setdefault(r["page_number"], []).append(r)
    pages = []
    for pno in sorted(by_page):
        chunks = by_page[pno]
        buf = [" "] * max(c["char_end"] for c in chunks)
        for c in chunks:
            buf[c["char_start"]:c["char_end"]] = list(c["text"])
        pages.append({"page_number": pno, "page_text": "".join(buf)})
    return pages


def _groups(pages, max_chars=6000, max_pages=4):
    """Split pages into extraction groups: <= max_pages pages and (except for a
    single oversized page) <= max_chars of text per group."""
    groups, cur, size = [], [], 0
    for p in pages:
        n = len(p["page_text"])
        if cur and (len(cur) >= max_pages or size + n > max_chars):
            groups.append(cur)
            cur, size = [], 0
        cur.append(p)
        size += n
    if cur:
        groups.append(cur)
    return groups


def _extract_call(group_text):
    """One structured-output extraction call. Returns the raw facts list ([] on any
    model/transport/JSON failure — extraction is best-effort; the doc just yields
    fewer facts and the drop is visible in the audit counts)."""
    payload = {"model": DIGEST_MODEL, "stream": False, "think": False,
               "keep_alive": KEEP_ALIVE, "format": _FORMAT,
               "options": {"temperature": 0, "num_ctx": NUM_CTX},
               "messages": [{"role": "system", "content": _SYSTEM},
                            {"role": "user", "content": group_text}]}
    req = urllib.request.Request(
        f"{ollama_url()}/api/chat", data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            content = json.load(resp)["message"]["content"]
        return json.loads(content).get("facts", []) or []
    except Exception:
        log.exception("digest: extraction call failed")
        return []


def gate_facts(raw_facts, group_pages, doc_id):
    """The mechanical write gate. A raw fact survives iff (a) its type is known and
    its defining fields are present, and (b) its span locates via the verifier's
    normalization in some page of the group (reported page tried first; page and
    offsets come from where the span was FOUND, never from the model's claim)."""
    by_no = {p["page_number"]: p["page_text"] for p in group_pages}
    verified, dropped = [], 0
    for raw in raw_facts:
        ftype = raw.get("fact_type")
        span = (raw.get("span") or "").strip()
        if ftype not in _REQUIRED or not span or \
                any(not (raw.get(k) or "").strip() for k in _REQUIRED[ftype]):
            dropped += 1
            continue
        candidates = [raw.get("page")] + [n for n in by_no if n != raw.get("page")]
        hit = None
        for pno in candidates:
            pt = by_no.get(pno)
            if not pt:
                continue
            loc = verifier.locate_span(pt, span)
            if loc is not None:
                hit = (pno, loc)
                break
        if hit is None:
            dropped += 1
            continue
        pno, (start, end) = hit
        value = {k: (raw.get(k) or "").strip() or None for k in _VALUE_KEYS[ftype]}
        if ftype == "date_event" and not (
                value.get("date_kind") == "explicit"
                and _ISO.match(value.get("date_iso") or "")):
            value["date_iso"] = None   # never store a date the document didn't state
        verified.append({"fact_type": ftype, "value": value, "page": pno,
                         "char_start": start, "char_end": end, "span": span,
                         "fact_key": fact_key(doc_id, ftype, pno, span)})
    return verified, dropped


def _yield_to_chat():
    """Interactive priority (same stance as ingest_worker): digest extraction defers
    to an in-flight chat on shared local compute."""
    while activity.chat_recent():
        time.sleep(0.5)


def extract_for_document(doc_id, db_path, catalog_db=None):
    """Extract, gate, and store one document's facts. Returns counts, or None when
    disabled / the doc vanished. Never raises (callers must not fail ingest)."""
    if not enabled():
        return None
    row = catalog.get_document(doc_id, db_path=catalog_db)
    if row is None:
        return None
    matter = row["matter_slug"]
    pages = pages_from_store(db_path, row["filename"], matter)
    extracted, dropped, facts = 0, 0, []
    for group in _groups(pages):
        _yield_to_chat()
        text = "\n\n".join(f"=== page {p['page_number']} ===\n{p['page_text']}"
                           for p in group)
        ok, bad = gate_facts(_extract_call(text), group, doc_id)
        facts.extend(ok)
        extracted += len(ok)
        dropped += bad
    catalog.replace_facts(doc_id, matter, facts, EXTRACTOR_VERSION, db_path=catalog_db)
    catalog.prune_orphan_reviews(matter, db_path=catalog_db)
    catalog.audit_append("matter_digest", matter,
                         json.dumps({"doc_id": doc_id, "extracted": extracted,
                                     "dropped": dropped}), db_path=catalog_db)
    log.info("digest doc=%s extracted=%d dropped=%d", doc_id, extracted, dropped)
    return {"extracted": extracted, "dropped": dropped}
```

Note: check `catalog.audit_append`'s exact signature (`sed -n '680,700p' catalog.py`) and match its parameter names/order.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_digest_gate.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add pipeline/digest.py pipeline/tests/test_digest_gate.py
git commit -m "feat(digest): extraction core — page reconstruction, LLM call, mechanical write gate"
```

---

### Task 3: Ingest hook + startup backfill

**Files:**
- Modify: `pipeline/ingest_worker.py` (`_run`, ~line 88-118)
- Modify: `pipeline/digest.py` (add `backfill_async`)
- Modify: `pipeline/api.py` (startup section — find where `preload_model` is launched: `grep -n "preload" api.py` — add the backfill thread beside it)
- Test: `pipeline/tests/test_digest_ingest_hook.py` (create)

**Interfaces:**
- Consumes: `digest.extract_for_document`, `digest.enabled`, `digest.EXTRACTOR_VERSION`, `catalog.digest_progress`.
- Produces: `digest.backfill_async(db_path, catalog_db=None, initial_delay=20.0) -> threading.Thread` — one-shot daemon thread; digests every ready/needs_review doc whose `digest_version != EXTRACTOR_VERSION`, oldest first, yielding to chat.

- [ ] **Step 1: Write the failing tests**

```python
"""Ingest hook: a successful ingest triggers digest extraction; a failed one does
not; a digest crash never fails the ingest. Backfill finds stale docs."""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PIPELINE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPELINE_DIR))
import catalog  # noqa: E402
import digest  # noqa: E402
import ingest_worker  # noqa: E402


class TestIngestHook(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._cat, catalog.DEFAULT_DB = catalog.DEFAULT_DB, self.tmp / "cat.db"
        catalog.create_matter("M")
        self.doc = catalog.add_document("m", "a.txt", self.tmp / "a.txt", status="queued")

    def tearDown(self):
        catalog.DEFAULT_DB = self._cat

    def _run(self, ingest_result):
        with mock.patch.object(ingest_worker.kb_ingest, "ingest_document",
                               return_value=ingest_result), \
             mock.patch.object(ingest_worker, "digest") as dg:
            ingest_worker._run(self.doc["id"], str(self.tmp / "a.txt"), "m",
                               str(self.tmp / "kb"), None)
        return dg

    def test_ready_triggers_digest(self):
        dg = self._run("ready")
        dg.extract_for_document.assert_called_once_with(
            self.doc["id"], str(self.tmp / "kb"), catalog_db=None)

    def test_failed_does_not_trigger(self):
        dg = self._run("failed")
        dg.extract_for_document.assert_not_called()

    def test_digest_crash_never_fails_ingest(self):
        with mock.patch.object(ingest_worker.kb_ingest, "ingest_document",
                               return_value="ready"), \
             mock.patch.object(ingest_worker.digest, "extract_for_document",
                               side_effect=RuntimeError("boom")):
            ingest_worker._run(self.doc["id"], str(self.tmp / "a.txt"), "m",
                               str(self.tmp / "kb"), None)   # must not raise
        self.assertEqual(catalog.get_document(self.doc["id"])["status"], "queued")
        # (status is whatever kb_ingest left; the point is no 'failed' overwrite)


class TestBackfill(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._cat, catalog.DEFAULT_DB = catalog.DEFAULT_DB, self.tmp / "cat.db"
        catalog.create_matter("M")

    def tearDown(self):
        catalog.DEFAULT_DB = self._cat

    def test_backfill_digests_only_stale_ready_docs(self):
        d1 = catalog.add_document("m", "stale.pdf", self.tmp / "s.pdf", status="ready")
        d2 = catalog.add_document("m", "fresh.pdf", self.tmp / "f.pdf", status="ready")
        catalog.replace_facts(d2["id"], "m", [], digest.EXTRACTOR_VERSION)  # already done
        d3 = catalog.add_document("m", "broken.pdf", self.tmp / "b.pdf", status="failed")
        seen = []
        with mock.patch.object(digest, "extract_for_document",
                               side_effect=lambda i, *a, **k: seen.append(i)), \
             mock.patch.object(digest, "_yield_to_chat"):
            t = digest.backfill_async(self.tmp / "kb", initial_delay=0)
            t.join(timeout=10)
        self.assertEqual(seen, [d1["id"]])


if __name__ == "__main__":
    unittest.main(verbosity=2)
```

Note: `catalog.add_document` signature/status handling as in Task 1. If `_run`'s job tuple shape differs (it takes `(doc_id, file_path, matter_slug, db_path, catalog_db)`), match the real signature.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_digest_ingest_hook.py -v`
Expected: FAIL — `AttributeError: module 'ingest_worker' has no attribute 'digest'` / `no attribute 'backfill_async'`

- [ ] **Step 3: Implement**

`ingest_worker.py` — add `import digest` with the other imports, then in `_run`, after the `log.info("ingest doc=%s ...")` line and before `_state["processed"] += 1`:

```python
    # M-2: build the matter digest for a successfully ingested doc. Best-effort —
    # a digest failure must never fail the ingest (the doc is already searchable).
    if result in ("ready", "needs_review"):
        on_stage("digest")
        try:
            digest.extract_for_document(doc_id, db_path, catalog_db=catalog_db)
        except Exception:
            log.exception("digest failed (non-fatal): doc_id=%s", doc_id)
```

`digest.py` — append:

```python
def _stale_doc_ids(catalog_db=None):
    """Ready docs not yet digested at the current extractor version, oldest first."""
    conn = catalog._connect(catalog_db)
    try:
        rows = conn.execute(
            "SELECT id FROM documents WHERE status IN ('ready', 'needs_review') "
            "AND (digest_version IS NULL OR digest_version != ?) ORDER BY id",
            (EXTRACTOR_VERSION,)).fetchall()
        return [r["id"] for r in rows]
    finally:
        conn.close()


def backfill_async(db_path, catalog_db=None, initial_delay=20.0):
    """One-shot startup backfill: digest every already-ingested doc that predates
    the current extractor version. Daemon thread; yields to chat between docs."""
    def _loop():
        time.sleep(initial_delay)   # let startup (model preload etc.) finish first
        if not enabled():
            return
        for doc_id in _stale_doc_ids(catalog_db):
            _yield_to_chat()
            try:
                extract_for_document(doc_id, db_path, catalog_db=catalog_db)
            except Exception:
                log.exception("digest backfill failed: doc_id=%s", doc_id)
    t = threading.Thread(target=_loop, name="matter-digest-backfill", daemon=True)
    t.start()
    return t
```

`api.py` — find the startup block that launches `preload_model` in a background thread and add beside it (using the same KB db path constant `routes_kb.KB_DB`):

```python
    import digest
    digest.backfill_async(routes_kb.KB_DB)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_digest_ingest_hook.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add pipeline/ingest_worker.py pipeline/digest.py pipeline/api.py pipeline/tests/test_digest_ingest_hook.py
git commit -m "feat(digest): ingest hook + one-shot startup backfill"
```

---

### Task 4: `routes_digest.py` — overview + review API

**Files:**
- Create: `pipeline/routes_digest.py`
- Modify: `pipeline/api.py` (import + `app.include_router(routes_digest.router)` beside the others, ~lines 76-100)
- Test: `pipeline/tests/test_digest_routes.py` (create)

**Interfaces:**
- Consumes: Task 1 catalog accessors, `digest.EXTRACTOR_VERSION`.
- Produces (Task 5's UI consumes exactly this):
  - `GET /matters/{matter}/overview` → `{"building": {"done","total"}, "deadlines": [...], "timeline": [...], "parties": [...], "amounts": [...], "terms": [...], "refs": [...], "dismissed_count": int}`. Item shape: `{"fact_key","fact_type","value":{...},"page","span","doc_id","filename","review": null | {"status","confirmed_date"}}`. Dismissed facts appear in NO list; `dismissed_count` reports them. Deadlines = date_events with `kind in ("deadline","obligation")`; timeline = ALL non-dismissed date_events.
  - `POST /matters/{matter}/facts/{fact_key}/review` body `{"status": "confirmed"|"dismissed"|null, "confirmed_date": "YYYY-MM-DD"|null}` → `{"ok": true}`. 404 unknown matter; 422 bad status or malformed date.

- [ ] **Step 1: Write the failing tests**

```python
"""M-2 overview API: grouped verified facts + review state; confirm/dismiss flow;
matter fence (404 on unknown matter); date format validation."""

import sys
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

PIPELINE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPELINE_DIR))
import catalog  # noqa: E402
import api  # noqa: E402

client = TestClient(api.app)


def _fact(key, ftype="date_event", value=None, page=1):
    return {"fact_type": ftype,
            "value": value or {"kind": "deadline", "label": "Answer due",
                               "date_text": "within 30 days", "date_iso": None,
                               "date_kind": "relative", "anchor": "service"},
            "page": page, "char_start": 0, "char_end": 14,
            "span": "within 30 days", "fact_key": key}


class TestOverviewRoutes(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._cat, catalog.DEFAULT_DB = catalog.DEFAULT_DB, self.tmp / "cat.db"
        catalog.create_matter("Nimbus Dispute")
        self.doc = catalog.add_document("nimbus-dispute", "msa.pdf",
                                        self.tmp / "msa.pdf", status="ready")
        catalog.replace_facts(self.doc["id"], "nimbus-dispute", [
            _fact("dl"),                                                     # deadline
            _fact("ev", value={"kind": "event", "label": "MSA executed",
                               "date_text": "March 1, 2026", "date_iso": "2026-03-01",
                               "date_kind": "explicit", "anchor": None}),
            _fact("pt", ftype="party", value={"name": "Nimbus Analytics LLC",
                                              "role": "provider", "org_form": "LLC"}),
        ], "v1")

    def tearDown(self):
        catalog.DEFAULT_DB = self._cat

    def test_overview_groups_and_review_join(self):
        r = client.get("/matters/nimbus-dispute/overview")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual([i["fact_key"] for i in body["deadlines"]], ["dl"])
        self.assertEqual(sorted(i["fact_key"] for i in body["timeline"]), ["dl", "ev"])
        self.assertEqual(body["parties"][0]["value"]["name"], "Nimbus Analytics LLC")
        self.assertEqual(body["deadlines"][0]["filename"], "msa.pdf")
        self.assertIsNone(body["deadlines"][0]["review"])
        self.assertEqual(body["building"], {"done": 0, "total": 1})

    def test_unknown_matter_404(self):
        self.assertEqual(client.get("/matters/nope/overview").status_code, 404)

    def test_confirm_with_date_then_undo(self):
        r = client.post("/matters/nimbus-dispute/facts/dl/review",
                        json={"status": "confirmed", "confirmed_date": "2026-07-24"})
        self.assertEqual(r.status_code, 200)
        body = client.get("/matters/nimbus-dispute/overview").json()
        self.assertEqual(body["deadlines"][0]["review"],
                         {"status": "confirmed", "confirmed_date": "2026-07-24"})
        client.post("/matters/nimbus-dispute/facts/dl/review", json={"status": None})
        body = client.get("/matters/nimbus-dispute/overview").json()
        self.assertIsNone(body["deadlines"][0]["review"])

    def test_dismissed_leaves_lists_and_counts(self):
        client.post("/matters/nimbus-dispute/facts/ev/review",
                    json={"status": "dismissed"})
        body = client.get("/matters/nimbus-dispute/overview").json()
        self.assertEqual([i["fact_key"] for i in body["timeline"]], ["dl"])
        self.assertEqual(body["dismissed_count"], 1)

    def test_bad_status_and_bad_date_rejected(self):
        r = client.post("/matters/nimbus-dispute/facts/dl/review",
                        json={"status": "approved"})
        self.assertEqual(r.status_code, 422)
        r = client.post("/matters/nimbus-dispute/facts/dl/review",
                        json={"status": "confirmed", "confirmed_date": "July 24"})
        self.assertEqual(r.status_code, 422)


if __name__ == "__main__":
    unittest.main(verbosity=2)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_digest_routes.py -v`
Expected: FAIL — 404 on `/matters/.../overview` (route absent)

- [ ] **Step 3: Implement `pipeline/routes_digest.py`**

```python
"""Matter overview API (M-2). Serves ONLY mechanically verified fact rows plus the
attorney's review state — zero LLM calls at read time. Deadline dates are the
attorney's: docuchat surfaces source language; the human supplies/confirms the date."""

import json
import re

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import catalog
import digest

router = APIRouter()

_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class ReviewBody(BaseModel):
    status: str | None = None
    confirmed_date: str | None = None


def _require_matter(matter):
    if catalog.get_matter(matter) is None:
        raise HTTPException(status_code=404, detail="unknown matter")


@router.get("/matters/{matter}/overview")
def overview(matter: str):
    _require_matter(matter)
    reviews = catalog.reviews_for_matter(matter)
    out = {"building": catalog.digest_progress(matter, digest.EXTRACTOR_VERSION),
           "deadlines": [], "timeline": [], "parties": [], "amounts": [],
           "terms": [], "refs": [], "dismissed_count": 0}
    buckets = {"party": "parties", "amount": "amounts",
               "defined_term": "terms", "key_ref": "refs"}
    for row in catalog.facts_for_matter(matter):
        review = reviews.get(row["fact_key"])
        if review and review["status"] == "dismissed":
            out["dismissed_count"] += 1
            continue
        item = {"fact_key": row["fact_key"], "fact_type": row["fact_type"],
                "value": json.loads(row["value_json"]), "page": row["page"],
                "span": row["span"], "doc_id": row["doc_id"],
                "filename": row["filename"], "review": review}
        if row["fact_type"] == "date_event":
            out["timeline"].append(item)
            if item["value"].get("kind") in ("deadline", "obligation"):
                out["deadlines"].append(item)
        else:
            out[buckets[row["fact_type"]]].append(item)

    def _due(i):   # unconfirmed first, then by best-known date; dateless last
        eff = (i["review"] or {}).get("confirmed_date") or i["value"].get("date_iso")
        return (0 if not (i["review"] and i["review"]["status"] == "confirmed") else 1,
                eff or "9999-99-99")
    out["deadlines"].sort(key=_due)
    out["timeline"].sort(key=lambda i: i["value"].get("date_iso") or "9999-99-99")
    return out


@router.post("/matters/{matter}/facts/{fact_key}/review")
def review_fact(matter: str, fact_key: str, body: ReviewBody):
    _require_matter(matter)
    if body.status not in ("confirmed", "dismissed", None):
        raise HTTPException(status_code=422, detail="status must be confirmed, dismissed, or null")
    if body.confirmed_date is not None and not _ISO.match(body.confirmed_date):
        raise HTTPException(status_code=422, detail="confirmed_date must be YYYY-MM-DD")
    catalog.set_fact_review(matter, fact_key, body.status, body.confirmed_date)
    catalog.audit_append("fact_review", matter,
                         json.dumps({"fact_key": fact_key, "status": body.status}))
    return {"ok": True}
```

Register in `api.py` (both lines, in alphabetical position with the others):

```python
import routes_digest  # noqa: E402
app.include_router(routes_digest.router)
```

Notes: match `catalog.get_matter` / `audit_append` real signatures. If the codebase's pydantic version predates `str | None` syntax in models, use `Optional[str]` — copy whatever `routes_profile.py` models do.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_digest_routes.py tests/test_digest_catalog.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add pipeline/routes_digest.py pipeline/api.py pipeline/tests/test_digest_routes.py
git commit -m "feat(digest): matter overview + fact review API"
```

---

### Task 5: Overview UI — layout B, deadline confirm flow, dropzone collapse

**Files:**
- Modify: `pipeline/static/app.js` (`showMatterDetail` ~line 723-760: insert container + call; new `renderMatterOverview` near the matter-detail helpers; the doc-rows render function for the dropzone collapse — find with `grep -n "matter-doc-rows" app.js`)
- Modify: `pipeline/static/app.css` (append overview styles)
- Test: `pipeline/tests/test_digest_ui.py` (create — static-content assertions in the `test_api_ui.py` style)

**Interfaces:**
- Consumes: Task 4's `GET /matters/{slug}/overview` and `POST .../review` exactly as specified; existing `esc()`, `highlightUrl({doc_id, page, span})` (app.js ~line 993), `api(path, opts)` helper (~line 32).
- Produces: `renderMatterOverview(slug)` called from `showMatterDetail`; container `<div id='matter-overview'>` placed between the tool-row and the dropzone (layout B).

- [ ] **Step 1: Write the failing static-content test**

```python
"""M-2 UI wiring: the overview container sits above the dropzone (layout B), the
renderer exists, every dynamic string passes esc(), and the confirm flow posts to
the review API. Static assertions only — behavior is smoke-tested in the app."""

import sys
import unittest
from pathlib import Path

PIPELINE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPELINE_DIR))

APP_JS = (PIPELINE_DIR / "static" / "app.js").read_text()
APP_CSS = (PIPELINE_DIR / "static" / "app.css").read_text()


class TestOverviewUI(unittest.TestCase):
    def test_container_above_dropzone(self):
        detail = APP_JS[APP_JS.index("function showMatterDetail"):]
        self.assertLess(detail.index("matter-overview"), detail.index("matter-dropzone"))

    def test_renderer_and_api_wiring(self):
        self.assertIn("function renderMatterOverview", APP_JS)
        self.assertIn("/overview", APP_JS)
        self.assertIn("/review", APP_JS)
        self.assertIn("needs your date", APP_JS)          # relative-deadline chip
        self.assertIn("confirmed by you", APP_JS)         # confirmed chip

    def test_deposition_digest_container_untouched(self):
        self.assertIn("matter-digest", APP_JS)            # transcript digest keeps its div

    def test_css_added(self):
        self.assertIn(".ov-due", APP_CSS)
        self.assertIn("#matter-dropzone.slim", APP_CSS)


if __name__ == "__main__":
    unittest.main(verbosity=2)
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_digest_ui.py -v`
Expected: FAIL on every assertion except `matter-digest`

- [ ] **Step 3: Implement the JS**

In `showMatterDetail`'s `detail.innerHTML` string, insert immediately after the tool-row `</div>` and BEFORE the dropzone div:

```javascript
        "<div id='matter-overview'></div>" +
```

At the end of `showMatterDetail` (after the existing wiring), add `renderMatterOverview(slug);`.

Add the renderer near the other matter helpers (style notes: `var`, no template literals, `esc()` on EVERY server string — match the file's conventions):

```javascript
  // M-2 matter overview: pure display of mechanically verified fact rows. Deadline
  // dates are the attorney's — the UI shows source language and takes THEIR date;
  // it never computes one. Every row cites verbatim source with a highlight link.
  var overviewPoll = null;
  async function renderMatterOverview(slug) {
    var box = document.getElementById("matter-overview");
    if (!box) return;
    var data;
    try { data = await api("/matters/" + encodeURIComponent(slug) + "/overview"); }
    catch (e) { box.innerHTML = ""; return; }

    if (overviewPoll) { clearTimeout(overviewPoll); overviewPoll = null; }
    var building = data.building.total > 0 && data.building.done < data.building.total;
    if (building) overviewPoll = setTimeout(function () { renderMatterOverview(slug); }, 5000);

    function srcLine(i) {
      return "<div class='ov-src'>“" + esc(i.span) + "” — <a class='ov-cite' " +
        "href='" + highlightUrl({ doc_id: i.doc_id, page: i.page, span: i.span }) +
        "' target='_blank'>" + esc(i.filename) + " p." + esc(String(i.page)) + "</a></div>";
    }

    function deadlineRow(i) {
      var v = i.value, r = i.review, eff = (r && r.confirmed_date) || v.date_iso;
      var html = "<div class='ov-row' data-key='" + esc(i.fact_key) + "'><div class='ov-top'>";
      html += "<span class='ov-due" + (r && r.status === "confirmed" ? " ok" : eff ? "" : " none") +
        "'>" + (eff ? esc(eff) : "No date yet") + "</span>";
      html += "<span class='ov-label'>" + esc(v.label || "") + "</span>";
      if (r && r.status === "confirmed")
        html += "<span class='ov-chip ok'>confirmed by you</span>";
      else if (v.date_iso) html += "<span class='ov-chip'>date as written — confirm?</span>";
      else html += "<span class='ov-chip'>needs your date</span>";
      html += "</div>" + srcLine(i);
      if (v.anchor && !eff)
        html += "<div class='ov-note muted'>counts from: " + esc(v.anchor) + "</div>";
      html += "<div class='ov-actions'>";
      if (r && r.status === "confirmed")
        html += "<button class='btn secondary ov-act' data-act='undo'>Unconfirm</button>";
      else {
        html += "<input type='date' class='ov-date' value='" + esc(v.date_iso || "") + "'>";
        html += "<button class='btn ov-act' data-act='confirm'>Confirm</button>";
        html += "<button class='btn secondary ov-act' data-act='dismiss'>Dismiss</button>";
      }
      return html + "</div></div>";
    }

    function tlRow(i) {
      var v = i.value;
      return "<div class='ov-tl'><span class='ov-tld'>" + esc(v.date_iso || v.date_text || "") +
        "</span><span>" + esc(v.label || "") + "</span></div>";
    }

    function groupBy(items, keyFn) {
      var m = {};
      items.forEach(function (i) { var k = keyFn(i); (m[k] = m[k] || []).push(i); });
      return m;
    }

    var html = "";
    if (building)
      html += "<div class='muted' style='font-size:13px;margin-bottom:6px'>Building matter digest — " +
        data.building.done + " of " + data.building.total + " documents…</div>";

    if (data.deadlines.length) {
      html += "<div class='panel'><div class='ov-title'>Deadlines";
      var unconf = data.deadlines.filter(function (i) {
        return !(i.review && i.review.status === "confirmed"); }).length;
      if (unconf) html += " <span class='muted'>· " + unconf + " need your confirmation</span>";
      html += "</div>" + data.deadlines.map(deadlineRow).join("") + "</div>";
    }

    if (data.timeline.length || data.parties.length || data.amounts.length) {
      html += "<div class='panel'><div class='ov-title'>Timeline · Parties · Amounts</div>";
      html += data.timeline.map(tlRow).join("");
      var parties = groupBy(data.parties, function (i) {
        return (i.value.name || "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim(); });
      var pbits = Object.keys(parties).map(function (k) {
        var v = parties[k][0].value;
        return esc(v.name) + (v.role ? " <span class='muted'>(" + esc(v.role) + ")</span>" : "");
      });
      var abits = data.amounts.map(function (i) {
        return esc(i.value.value || "") + (i.value.purpose ? " <span class='muted'>" +
          esc(i.value.purpose) + "</span>" : "");
      });
      if (pbits.length || abits.length)
        html += "<div class='ov-tl'><span>" + pbits.concat(abits).join(" · ") + "</span></div>";
      html += "</div>";
    }

    if (data.terms.length || data.refs.length) {
      html += "<details class='panel ov-terms'><summary class='ov-title'>Key terms &amp; references (" +
        (data.terms.length + data.refs.length) + ")</summary>";
      html += data.terms.map(function (i) {
        return "<div class='ov-tl'><span>" + esc(i.value.term || "") + "</span>" + srcLine(i) + "</div>";
      }).join("");
      html += data.refs.map(function (i) {
        return "<div class='ov-tl'><span>" + esc(i.value.ref_type || "") + " " +
          esc(i.value.ref_value || "") + "</span>" + srcLine(i) + "</div>";
      }).join("");
      html += "</details>";
    }

    if (data.dismissed_count)
      html += "<div class='muted' style='font-size:12px'>dismissed (" + data.dismissed_count + ")</div>";
    if (!html && !building)
      html = "<div class='panel muted'>No extractable facts yet — the digest builds " +
        "automatically when documents are added.</div>";
    box.innerHTML = html;

    box.querySelectorAll(".ov-act").forEach(function (b) {
      b.addEventListener("click", async function () {
        var row = b.closest(".ov-row"), key = row.dataset.key, body;
        if (b.dataset.act === "dismiss") body = { status: "dismissed" };
        else if (b.dataset.act === "undo") body = { status: null };
        else {
          var d = row.querySelector(".ov-date").value;
          if (!d) { row.querySelector(".ov-date").focus(); return; }
          body = { status: "confirmed", confirmed_date: d };
        }
        await api("/matters/" + encodeURIComponent(slug) + "/facts/" +
          encodeURIComponent(key) + "/review",
          { method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body) });
        renderMatterOverview(slug);
      });
    });
  }
```

Dropzone collapse — in the function that fills `matter-doc-rows` (find it via `grep -n "matter-doc-rows" app.js`), after the rows are written add:

```javascript
    var dz = document.getElementById("matter-dropzone");
    if (dz) dz.classList.toggle("slim", docs.length > 0);
```

(name the docs array whatever that function actually uses). Also call `renderMatterOverview(mattersState.open)` at the end of that refresh function so a finished ingest updates the overview.

Append to `app.css`:

```css
/* M-2 matter overview */
#matter-overview .ov-title{font-weight:600;font-size:11px;text-transform:uppercase;
  letter-spacing:.06em;color:var(--muted);margin-bottom:6px}
#matter-overview .ov-row{padding:8px 0;border-top:1px solid var(--border)}
#matter-overview .ov-row:first-of-type{border-top:none}
#matter-overview .ov-top{display:flex;gap:10px;align-items:baseline;flex-wrap:wrap}
.ov-due{font-weight:600;color:var(--err);min-width:84px;white-space:nowrap;
  font-variant-numeric:tabular-nums}
.ov-due.ok{color:var(--text)}
.ov-due.none{color:var(--warn);font-weight:500}
.ov-label{font-weight:500}
.ov-chip{background:var(--accent-soft);color:var(--accent);border-radius:3px;
  padding:1px 6px;font-size:11px;white-space:nowrap}
.ov-chip.ok{background:#e8f7ee;color:var(--ok)}
.ov-src{color:var(--muted);font-style:italic;font-size:13px;margin-top:2px}
.ov-cite{color:var(--accent);font-style:normal}
.ov-note{font-size:12px}
.ov-actions{margin-top:5px;display:flex;gap:6px;align-items:center}
.ov-date{border:1px solid var(--border-2);border-radius:4px;padding:2px 6px;
  font-size:12px;background:var(--panel);color:var(--text);font-family:var(--sans)}
.ov-tl{display:flex;gap:8px;padding:3px 0;font-size:13px}
.ov-tld{color:var(--muted);font-variant-numeric:tabular-nums;white-space:nowrap;min-width:84px}
.ov-terms summary{cursor:pointer}
#matter-dropzone.slim{padding:8px !important;font-size:12px}
```

- [ ] **Step 4: Run the static test + full suite**

Run: `python3 -m pytest tests/test_digest_ui.py tests/test_api_ui.py -v`
Expected: PASS

- [ ] **Step 5: Live smoke test in a real browser**

Start the dev server (uvicorn, loopback — check `README`/`RUN_STATE` for the exact dev-run command this repo uses), open the app, open a matter with documents, and verify: overview renders above the dropzone; a relative deadline shows "needs your date" with a date field; Confirm with a picked date flips to "confirmed by you"; Dismiss removes the row and increments "dismissed (n)"; the source citation link opens the highlighted PDF page; the dropzone is slim. **Remember (WKWebView memory): before release this must also be exercised in the packaged app, not just a browser — that's part of Task 8.**

- [ ] **Step 6: Commit**

```bash
git add pipeline/static/app.js pipeline/static/app.css pipeline/tests/test_digest_ui.py
git commit -m "feat(digest): matter overview UI — layout B, attorney-date confirm flow"
```

---

### Task 6: Fencing tests — the answer engine cannot see the digest

**Files:**
- Test: `pipeline/tests/test_digest_fencing.py` (create)

**Interfaces:**
- Consumes: `inspect.getsource` over `answering`, `verifier`, `retrieval` (mirrors `test_connectors.py`'s memory-fencing test, ~line 175).

- [ ] **Step 1: Write the test (it should PASS immediately — it pins the fence)**

```python
"""M-2 fence: matter_facts is display-layer only this cycle. The grounded answer
path must have no route to the digest — no import, no table read. If a future
fact-router diff touches this, it must come with its own full 63/63 gate run."""

import inspect
import sys
import unittest
from pathlib import Path

PIPELINE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPELINE_DIR))
import answering  # noqa: E402
import retrieval  # noqa: E402
import verifier  # noqa: E402


class TestDigestFencing(unittest.TestCase):
    def test_answer_path_never_touches_digest(self):
        for mod in (answering, verifier, retrieval):
            src = inspect.getsource(mod)
            for token in ("import digest", "matter_facts", "fact_review",
                          "routes_digest"):
                self.assertNotIn(token, src,
                                 f"{mod.__name__} references {token} — digest fence broken")

    def test_digest_accessors_require_matter(self):
        import catalog
        for fn in (catalog.facts_for_matter, catalog.reviews_for_matter,
                   catalog.prune_orphan_reviews):
            with self.assertRaises(ValueError):
                fn("")


if __name__ == "__main__":
    unittest.main(verbosity=2)
```

- [ ] **Step 2: Run it**

Run: `python3 -m pytest tests/test_digest_fencing.py -v`
Expected: PASS (if it fails, the implementation broke the fence — fix the implementation, never the test)

- [ ] **Step 3: Commit**

```bash
git add pipeline/tests/test_digest_fencing.py
git commit -m "test(digest): fence — answer path has no route to matter_facts"
```

---

### Task 7: G-DIG — extraction-quality eval script

**Files:**
- Create: `pipeline/run_digest_eval.py`
- Create: `eval/digest_inventory.example.json` (format documentation + fixture; the real hand-labeled inventory is built at gate time in the release checkout, where the eval corpus lives)
- Test: `pipeline/tests/test_digest_eval.py` (create)

**Interfaces:**
- Consumes: `digest.pages_from_store`, `digest._groups`, `digest._extract_call`, `digest.gate_facts`, `verifier._norm_map`.
- Produces: `python3 run_digest_eval.py --inventory ../eval/digest_inventory.json --db <lancedb path> --catalog <catalog path>` → per-type recall report + drop counts, exit 1 below targets (dates/amounts ≥ 0.85, parties ≥ 0.90).

- [ ] **Step 1: Define the inventory format** (`eval/digest_inventory.example.json`)

```json
{
  "_comment": "Hand-labeled extraction ground truth. One entry per fact a competent reader would put in the digest. span_contains: a distinctive normalized substring of the source span (matching is via verifier normalization). Recall = fraction of entries matched by an extracted fact of the same type on the same doc.",
  "targets": {"date_event": 0.85, "amount": 0.85, "party": 0.90},
  "facts": [
    {"doc": "nimbus_msa_v2.pdf", "matter": "nimbus-dispute",
     "fact_type": "date_event", "span_contains": "within thirty (30) days after receipt"},
    {"doc": "nimbus_msa_v2.pdf", "matter": "nimbus-dispute",
     "fact_type": "party", "span_contains": "pemberton logistics"},
    {"doc": "nimbus_msa_v2.pdf", "matter": "nimbus-dispute",
     "fact_type": "amount", "span_contains": "$28,000"}
  ]
}
```

- [ ] **Step 2: Write the failing scorer test**

```python
"""G-DIG scorer: recall per fact type against a hand-labeled inventory, matched
via the verifier's normalization; drop counts reported; exit code from targets."""

import sys
import unittest
from pathlib import Path

PIPELINE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPELINE_DIR))
import run_digest_eval  # noqa: E402


class TestScorer(unittest.TestCase):
    def test_recall_by_type(self):
        inventory = [
            {"doc": "a.pdf", "fact_type": "party", "span_contains": "pemberton logistics"},
            {"doc": "a.pdf", "fact_type": "party", "span_contains": "nimbus analytics"},
            {"doc": "a.pdf", "fact_type": "amount", "span_contains": "$28,000"},
        ]
        extracted = {("a.pdf", "party"): ["Pemberton Logistics Inc. (“Client”)"],
                     ("a.pdf", "amount"): []}
        recall = run_digest_eval.score(inventory, extracted)
        self.assertEqual(recall["party"], {"hit": 1, "total": 2})
        self.assertEqual(recall["amount"], {"hit": 0, "total": 1})

    def test_targets_gate(self):
        self.assertTrue(run_digest_eval.meets_targets(
            {"party": {"hit": 9, "total": 10}}, {"party": 0.90}))
        self.assertFalse(run_digest_eval.meets_targets(
            {"party": {"hit": 8, "total": 10}}, {"party": 0.90}))


if __name__ == "__main__":
    unittest.main(verbosity=2)
```

- [ ] **Step 3: Run to verify it fails, then implement `run_digest_eval.py`**

```python
"""G-DIG (M-2 gate): extraction recall against a hand-labeled fact inventory.
Runs the REAL extractor over the eval store, gates mechanically, and scores
recall per fact type. Precision is enforced by construction (the write gate);
value correctness is spot-graded per extractor_version, per the design spec.
Usage:
  python3 run_digest_eval.py --inventory ../eval/digest_inventory.json \
      --db ../eval/.lancedb_eval --catalog ../eval/.kb_catalog_eval.db
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import digest  # noqa: E402
import verifier  # noqa: E402


def _norm(s):
    return verifier._norm_map(s)[0]


def score(inventory, extracted):
    """extracted: {(doc, fact_type): [span, ...]}. An inventory entry is a hit when
    its normalized span_contains is a substring of any extracted span's norm."""
    recall = defaultdict(lambda: {"hit": 0, "total": 0})
    for entry in inventory:
        t = entry["fact_type"]
        recall[t]["total"] += 1
        needle = _norm(entry["span_contains"])
        spans = extracted.get((entry["doc"], t), [])
        if any(needle in _norm(s) for s in spans):
            recall[t]["hit"] += 1
    return dict(recall)


def meets_targets(recall, targets):
    for t, floor in targets.items():
        r = recall.get(t, {"hit": 0, "total": 0})
        if r["total"] and r["hit"] / r["total"] < floor:
            return False
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inventory", required=True)
    ap.add_argument("--db", required=True)
    ap.add_argument("--catalog", required=True)
    args = ap.parse_args()

    manifest = json.loads(Path(args.inventory).read_text())
    inventory, targets = manifest["facts"], manifest.get("targets", {})
    extracted, drops = defaultdict(list), 0
    for key in sorted({(e["doc"], e["matter"]) for e in inventory}):
        doc, matter = key
        pages = digest.pages_from_store(args.db, doc, matter)
        for group in digest._groups(pages):
            text = "\n\n".join(f"=== page {p['page_number']} ===\n{p['page_text']}"
                               for p in group)
            ok, bad = digest.gate_facts(digest._extract_call(text), group, doc_id=0)
            drops += bad
            for f in ok:
                extracted[(doc, f["fact_type"])].append(f["span"])

    recall = score(inventory, extracted)
    print(f"G-DIG — extractor {digest.EXTRACTOR_VERSION} — dropped {drops} spans at the gate")
    for t in sorted(recall):
        r = recall[t]
        pct = (r["hit"] / r["total"] * 100) if r["total"] else 0
        print(f"  {t:14s} {r['hit']}/{r['total']}  ({pct:.0f}%)  target "
              f"{targets.get(t, 0) * 100:.0f}%")
    ok = meets_targets(recall, targets)
    print("G-DIG:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the scorer test**

Run: `python3 -m pytest tests/test_digest_eval.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pipeline/run_digest_eval.py eval/digest_inventory.example.json pipeline/tests/test_digest_eval.py
git commit -m "feat(digest): G-DIG extraction-quality eval script + inventory format"
```

(If `eval/` does not exist in this checkout, put the example next to the script as `pipeline/digest_inventory.example.json` and note it in the commit message — the real inventory lives in the release checkout's eval tree.)

---

### Task 8: Gate — full suite, G-DIG labeling + run, 63/63 golden, throughput, packaged-app smoke

This is the release gate, not a code task. It runs partly in the RELEASE checkout (`~/projects/legal-doc-intelligence` — eval corpus + golden gate live there; sync the diff there first, per that repo's established release recipe).

- [ ] **Step 1: Full dev suite green**

Run: `cd ~/legal-document-chat/pipeline && python3 -m pytest tests/ -q`
Expected: 0 failures

- [ ] **Step 2: Hand-label the G-DIG inventory** (release checkout)

Pick 3–4 eval-corpus docs (one long MSA, one pleading, one correspondence set). Read each and list every party / dated item / amount a competent reader would put in the digest, as `eval/digest_inventory.json` entries (format per Task 7's example, ~30–60 entries). Seed date/amount/party entries from the existing golden manifest's verbatim spans where they overlap these docs.

- [ ] **Step 3: Run G-DIG** (release checkout, Ollama up)

Run: `python3 run_digest_eval.py --inventory ../eval/digest_inventory.json --db <eval lancedb> --catalog <eval catalog>`
Expected: PASS (dates/amounts ≥85%, parties ≥90%). If FAIL: iterate the prompt (bump `EXTRACTOR_VERSION`), never loosen the gate. Record the drop count in the run log.

- [ ] **Step 4: Value-correctness spot grade**

For ~20 random verified facts, compare `value_json` against the cited span by eye; record the result in the run log and freeze the expected rows for this `extractor_version` (per spec §gates).

- [ ] **Step 5: Full 63/63 golden run** (release checkout, per its golden-gate recipe)

Run `run_golden.py` + `score_golden.py` exactly as the v0.3.0 gate did.
Expected: **63/63 present + 9/9 not-found + 0 rejected claims** — the answer path is untouched, so anything else means the fence leaked; stop and investigate.

- [ ] **Step 6: Ingest throughput check**

Time a re-ingest of the same multi-doc sample twice: `LDI_MATTER_DIGEST=0` vs enabled (wall time per doc through the worker queue, using the per-stage timings already in the ingest log). Expected: digest stage present, and end-to-end doc-ready time (extract+embed_write+tables stages, which gate searchability) unchanged — the digest stage runs after ready. Record total background time; the ≤25% budget applies to time-to-searchable, and searchability precedes digest by construction.

- [ ] **Step 7: Packaged-app smoke (WKWebView, not browser)**

Build/run the packaged app per the release recipe and exercise: matter overview renders, date picker works in WKWebView, confirm/dismiss round-trips, citation highlight opens. (Browser QA missed WKWebView-only bugs before — this step is mandatory.)

- [ ] **Step 8: Update docs + commit**

Update `RUN_STATE.md` top entry (digest shipped, gate results incl. drop counts + G-DIG recall) and mark plan-doc item 1 in `docs/2026-07-10-next-cycle-plan.md`. Commit.

---

## Self-review notes

- Spec coverage: schema (T1), extraction+gate (T2), ingest hook+backfill (T3), API (T4), UI layout B + confirm model A + dropzone collapse + building state + empty state (T5), fencing+deletion (T1/T6), G-DIG + G-NF-adjacent adversarial coverage (T7/T8), 63/63 + throughput (T8). G-NF's three new adversarial not-found questions ship with the fact-router cycle (they test answer-path temptation, which doesn't exist read-side) — noted deviation from spec, deliberate.
- Deadline-panel membership (`kind in ("deadline","obligation")`) matches the approved mockup (Q3 payment obligation appeared in Deadlines).
- Signatures cross-checked: `replace_facts` fact dict = `gate_facts` output; route payloads = JS `api()` calls; `digest_progress` consumed by route `building` = JS `data.building`.
