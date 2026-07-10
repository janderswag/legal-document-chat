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
    rows = (open_table(db_path).search()
            .where(f"source_filename = '{fn}' AND matter = '{mt}' "
                   f"AND document_type != 'table'")
            .select(["page_number", "char_start", "char_end", "text"])
            .limit(100000).to_arrow().to_pylist())
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
    try:
        pages = pages_from_store(db_path, row["filename"], matter)
    except Exception:
        # A store read failure must NOT stamp digest_version — the doc would be
        # recorded as digested without ever being read. Leave it unstamped so
        # the startup backfill retries it.
        log.exception("digest: chunk read failed, doc left unstamped: doc_id=%s", doc_id)
        return None
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
