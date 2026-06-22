# Transcripts v1 — line-aware Cited Q&A (design) — ⏸️ DEFERRED / HELD IN RESERVE

> **Status: design complete, BUILD DEFERRED (2026-06-21).** Brainstormed with the owner; we decided NOT
> to build on spec. Depositions already work today as ordinary Document-Hub uploads (grounded, verified,
> **page-level** cited answers) — ~80% of the value for free. This feature adds the last 20% (court-grade
> **page:line** precision). **Trigger to build:** a real deposition shows page-level citation is not
> precise enough for how the attorney works (i.e. the attorney is deposition-heavy / litigation-focused).
> Until then this design sits here, ready. See `DECISIONS.md` D-56.

## Why deferred (the critical case)
- Uploading a deposition as a normal document already yields verified verbatim quotes + page cites.
- The marginal gain is the `:line` (court-citation format) — high value **only** if depositions are
  central to this attorney's practice; gold-plating otherwise.
- Real risk: a mis-parsed line number is *confidently wrong* (the quote stays honest via the verifier,
  but the line label could mislead) — the worst failure mode for a precision-citation feature.
- Cheap interim win available without this build: **strip the line-number gutter** so it stops polluting
  retrieval when a transcript is uploaded as a normal document.

## Scope (when built)
Born-digital deposition/hearing PDFs (full-size, ~25 numbered lines/page, line numbers in a left gutter
as text). Ask plain-English questions → grounded answer with exact **page:line** citations (e.g.
"45:12–18"), every cited quote mechanically verified at those lines. New `document_type="transcript"`,
user-designated at upload (no auto-detect in v1).

## Design
1. **Ingestion** (`transcript_extract.py`): PyMuPDF per page detects the numbered-line gutter and captures
   each line as `{page_number, line_number, text, char_start, char_end}` into the page text → page text +
   ordered **line-map**. (Our PyMuPDF page extraction + a line dimension.)
2. **Chunking** (`transcript_chunk.py`): one chunk per transcript page (retrieval unit, ~25 lines), keeping
   our **existing** `char_start/char_end` offset model (verifier unchanged) **plus** the per-line map, page
   number, `document_type=transcript`. A few trailing lines of the prior page ride along as context to
   survive cross-page-break answers; citations only ever use true page:line. Embedded via bge-m3.
3. **Retrieval + Answering**: reused unchanged (matter pre-filter → similarity → grounded qwen3 §10
   cite/refuse). T-CLAUSE `doc_id` post-filter gives "ask within this one transcript."
4. **Keystone — page:line is CHUNK-DERIVED + mechanically verified (no verifier loosening, D-19/D-38):**
   the model quotes a span → the **existing verifier** confirms its chars overlap the retrieved chunk
   (unchanged) → we **derive** page:line by mapping the *verified* char-span through the line-map. The
   page:line is computed from verified offsets, never asserted by the model (D-38 extended page→page:line).
   A fabricated/altered quote fails the existing overlap check → 0 citations. Zero new trust surface.
5. **UI**: reuse the source viewer's char-span highlight — the same verified span lands on the cited
   line(s); the chip reads "p.45:12–18". Reuses `/kb/highlight` + thumbnails; no new viewer.
6. **Testing/invariants**: synthetic born-digital transcript with known page:line facts; test-first
   (known quote→correct verified page:line; fabricated/altered→rejected; wrong-line→not credited there;
   prose docs unaffected; baselines byte-identical, KB/scratch; loopback + PID-scoped egress). Reuse
   verifier/answering — no fork.

## Deferred to v2 (YAGNI)
Q/A & speaker attribution · scanned/ASCII/E-Transcript formats · cross-page-exchange chunking · summaries
· navigation/search · transcript auto-detection · deponent short-name in cites (v1 = filename + page:line).
