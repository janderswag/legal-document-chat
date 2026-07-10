# Matter Digest (M-2) — Design Spec

_Date: 2026-07-10. Status: approved by owner (brainstorm session, layout + confirm
model chosen via visual companion). Source draft: `docs/2026-07-10-memory-design-draft.md`
§M-2. Strategy context: `docs/2026-07-10-next-cycle-plan.md` item 1 (keystone)._

## Goal

At ingest, extract span-verified facts (parties, dated items, amounts, defined terms,
key references) from each document into a per-matter structured layer. That layer
renders an **instant matter overview** (deadlines, timeline, parties & amounts) the
moment a matter opens — zero LLM calls at read time — with every row cited to a
verbatim source span and click-through to the highlighted PDF page.

## Owner decisions (settled — do not relitigate)

1. **Cycle scope:** digest extraction + `matter_facts` + matter overview UI +
   deadline extraction with confirm/dismiss. All read-side. The **fact router**
   (feeding retrieval candidates) is a LATER, separately 63/63-gated diff. Aggregate
   answers, cross-matter "due this week", `/deadlines` command: out of scope.
2. **Deadline model:** one dated-item lane. `fact_type='date_event'` carries a
   `kind` field (`event | obligation | deadline`); no separate deadline fact type.
   A misclassified deadline still appears in the timeline (graceful degradation).
3. **Review state:** separate `fact_review` table keyed by a stable content hash.
   `matter_facts` stays a pure function of (document, extractor_version) —
   idempotently rebuildable machine output. Human judgment lives only in
   `fact_review` and survives re-extraction.
4. **Overview layout:** "digest above the fold, one page" — the existing matter
   page reordered; no new navigation.
5. **Deadline confirmation:** **the attorney supplies the date.** docuchat never
   computes a due date. Explicit dates offer "Confirm as written"/"Edit date";
   relative/conditional deadlines show source language + an empty date field.

## Trust rules (inherited, non-negotiable)

- Memory steers retrieval or carries a re-verifiable span pointer; it never asserts
  content. This cycle it does neither steering nor asserting — display only.
- **Mechanical write gate:** no row enters `matter_facts` unless its span passes the
  same normalization-substring check as the D-19 verifier against the clean page
  text, with offsets located mechanically. LLM proposes, check disposes. Failures
  are dropped and counted. Extraction error ⇒ recall loss, never precision loss.
- `date_iso` is stored only when the date is explicit in the verified span. The
  model never infers, computes, or chains a date.
- `answering.py` has no import path to any digest module (fencing test).

## Architecture

| Unit | Purpose | Depends on |
|---|---|---|
| `pipeline/digest.py` | Extraction pass + mechanical write gate + fact accessors | catalog, verifier normalization, chunking page text |
| `pipeline/routes_digest.py` | API: read overview, confirm/dismiss, digest progress | digest.py, catalog |
| `catalog.py` additions | `matter_facts`, `fact_review` tables + accessors | — |
| `ingest_worker` hook | Run extraction after a doc's chunks commit; backfill job for pre-existing docs | digest.py, activity.mark_chat priority |
| `app.js` matter detail | Overview render (layout B), confirm/dismiss UI | routes_digest API, existing pdf_view citation viewer |

Extraction runs at background priority (existing chat-outranks-background yield).
Backfill: on startup, any ingested doc lacking facts at the current
`extractor_version` is queued behind live ingest work.

## Schema (catalog.py, `CREATE TABLE IF NOT EXISTS` + idempotent style)

```sql
CREATE TABLE IF NOT EXISTS matter_facts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    matter_slug TEXT NOT NULL,          -- the fence: every read requires it
    doc_id INTEGER NOT NULL,            -- FK documents(id); delete doc -> delete facts
    fact_type TEXT NOT NULL,            -- 'party'|'date_event'|'amount'|'defined_term'|'key_ref'
    value_json TEXT NOT NULL,
    page INTEGER NOT NULL,
    char_start INTEGER NOT NULL,        -- offsets into clean page text (chunk space)
    char_end INTEGER NOT NULL,
    span TEXT NOT NULL,                 -- verbatim; mechanically verified at write
    extractor_version TEXT NOT NULL,    -- prompt+model version; re-extract on bump
    created TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_matter_facts ON matter_facts (matter_slug, fact_type);

CREATE TABLE IF NOT EXISTS fact_review (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    matter_slug TEXT NOT NULL,
    fact_key TEXT NOT NULL,             -- sha256(doc_id|fact_type|page|span_norm)
    status TEXT NOT NULL,               -- 'confirmed' | 'dismissed'
    confirmed_date TEXT,                -- attorney-entered ISO date (deadlines)
    created TEXT NOT NULL,
    UNIQUE (matter_slug, fact_key)
);
```

`date_event` payload:

```json
{
  "kind": "deadline",            // event | obligation | deadline
  "label": "Response to termination notice",
  "date_text": "within thirty (30) days after receipt",   // verbatim
  "date_iso": null,              // null unless explicit in the span
  "date_kind": "relative",       // explicit | relative | conditional
  "anchor": "receipt of notice"  // what a relative date counts from (nullable)
}
```

Other payloads follow the draft: `party` {name, role, org_form}, `amount`
{value, currency, purpose}, `defined_term` {term}, `key_ref` {ref_type, value}.

Review-state semantics: absent `fact_review` row = **proposed**. Rows whose
`fact_key` no longer matches any fact (after re-extraction/doc delete) are pruned
by the same job. Matter disposition deletes both tables' rows.

## Extraction pass

- Unit: chunk group of ~2–4 pages of clean page text.
- Model: qwen3:14b, temperature 0, JSON-schema-constrained output, one call per
  group, all five fact types in one pass.
- Every item must include the verbatim span; the write gate locates offsets
  mechanically and rejects non-matching spans (drop count recorded per doc run,
  surfaced in the audit log).
- `extractor_version` stamps every row; bumping it queues re-extraction
  (delete rows for doc at old version → re-extract). Confirmations survive via
  `fact_review` keys.

## Matter overview UI (layout B)

Order on the matter page: back link, title, tool row, **Deadlines panel**,
**Timeline / Parties & Amounts panel**, collapsed **Key terms & references**,
slim add-documents bar (dropzone collapses once the matter has documents),
document table, conversations.

- **Deadline rows:** due date (or "No date yet" in warn color), label,
  status chip (`needs your date` / `date as written — confirm?` /
  `confirmed by you · <date>`), verbatim source language with file+page
  citation, actions (date field + Confirm / Edit date / Dismiss). Unconfirmed
  sorts above confirmed; dismissed rows collapse into a "dismissed (n)" footer,
  never deleted.
- **Timeline:** date_event rows (all kinds) sorted by best-known date; rows with
  no date sort into an "undated" tail.
- **Parties & amounts:** grouped by normalized value at render time (raw rows
  keep provenance); each group cites its source occurrences.
- Every row click-through opens the PDF at the highlighted span via the existing
  citation viewer path.
- While extraction is pending: "Building matter digest — n of m documents." A
  matter with zero extractable facts shows an honest empty state, not blanks.

## Gates, tests, budgets

- **G-DIG (new golden class):** hand-labeled fact inventory over 3–4 corpus docs
  (one long MSA, one pleading, one correspondence set) + existing golden manifest
  spans as ground truth. Recall ≥85% dates/amounts, ≥90% parties. Value
  correctness spot-graded once per extractor_version, then frozen as expected
  rows. Drop count reported every run (rising = extractor regression alarm).
- **G-NF additions:** 3 adversarial not-found questions that tempt the digest
  (e.g., aggregate over a fact type the corpus lacks) — exact refusal, zero
  citations.
- **Full 63/63 golden run before release.** Expected grade-identical (answer path
  untouched); the run is the proof, not the assumption.
- **Fencing tests:** every `matter_facts`/`fact_review` accessor requires
  `matter_slug`; `answering.py` imports no digest module.
- **Deletion tests:** doc delete cascades its facts; matter disposition leaves
  zero rows in `matter_facts` AND `fact_review`.
- **Budgets:** overview render = zero LLM calls; ingest throughput regression
  ≤25%; extraction is background-priority and yields to chat.

## Out of scope this cycle

Fact router (later, own flag + full 63/63 + G-AGG), aggregate answers,
cross-matter "due this week" view, `/deadlines` slash command, M-1 query
rewriting (own cycle, gated by G-MT), contextual chunk headers (M-2b),
any cross-matter memory.
