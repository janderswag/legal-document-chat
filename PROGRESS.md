# PROGRESS.md — Builder backlog (M-ENRICH, D-54 protocol)

> Senior-engineer backlog. One task at a time, top→bottom. Each: test-first → green → mark [x]
> with a one-line note + files. [GATE] = HARD-STOP (install/dep/model-fetch/real-data/hardware/
> non-loopback/verifier-weaken/baseline-reindex). [BLOCKED] = missing info / failing dep.
>
> Invariants (DoD): never-false-accept (D-19/D-38, reuse verifier.py/clauses.py — no fork);
> baselines byte-identical (canon fold from pipeline/: `.lancedb=13b242de .lancedb_full=0df0525c
> .lancedb_hyb=51e13b31`); loopback-only + PID-scoped egress; no new install.

## A. T-GRID — tabular review grid (headline, end-to-end)
- [x] **A0a** code-enforce `TABLEFORMER_REVISION` — `cached_model_revision()`+`assert_model_revision()` in extract_tables (offline path); mismatch→RuntimeError. 5 tests green. _table_extract.py, test_table_revision.py_
- [x] **A0b** pruned all 4 accumulated matters → recreated ONE clean `demo-matter` (MSA + fee exhibit); KB-only, baselines intact, 0 non-loopback. 3 tests green. _catalog.delete_matter, kb_maintenance.py, test_kb_maintenance.py_
- [x] **A1** `grid.py` + `routes_grid.py`: `POST /grid` SSE (meta→cell…→done); per cell answer()+`clauses._classify` (reused, not forked); bounded ThreadPool ≤4; allowlist 400 / verbs 405; doc_id post-filter no-leak. _grid.py, routes_grid.py, api.py, test_api.py allowlist_
- [x] **A2** columns default to clause_taxonomy.json; `clause_ids` subset + `questions` custom override (`grid.resolve_columns`).
- [x] **A3** Review Grid UI: SSE fetch-stream, sticky header+first col, skeleton cells, badge+value+`/kb/highlight` chip, CSV export (local Blob), esc() XSS. _app.html, app.js, app.css_
- [x] **A4** tests every layer: backend matrix (9, incl. never-false-accept + bounded-concurrency + no-leak) + API/SSE (4) + UI/CSV (9) + live 2-doc matrix (5, real Ollama) + A0 (8). All green.

## B. Small wins (local, no new install)
- [x] **B1** `answering._norm` now html.unescape + backslash-strip (verifier-aligned); precision-only, fabricated span still won't resolve. 5 tests. _answering.py, test_norm_align.py_
- [x] **B2** `openapi_url=None` (+docs/redoc already None); `/openapi.json`,`/docs`,`/redoc`→404. _api.py, test_api.py_
- [x] **B3** deploy README prominent compose-only ⚠ block (never `docker run -p`, D-43a); guard test. _deploy/README.md, test_deploy_scripts.py_
- [x] **B4** `confidence_from_logprobs`=exp(mean logprob); opt-in `answer(with_confidence)` (default byte-identical); chat route + UI pill; display-only (citations unchanged). 4 tests. _answering.py, routes_chat.py, app.js/css, test_confidence.py_
- [x] **B5** `fuzzy_fallback.probable_sources` (difflib) — verified=False hints only, never a citation; fuzzy-only → 0 verified. 5 tests. _fuzzy_fallback.py, test_fuzzy_fallback.py_
- [x] **B6** `/chat/stream` SSE (token…→done); verifier runs on COMPLETE text; streamed fabrication → 0 citations. 2 tests. _answering.answer_stream/_stream_tokens, routes_chat.py, test_chat_stream.py_

## C. Retrieval experiments (SCRATCH + measured — baseline-protected)
- [x] **C1** measured read-only: **F-026 RECOVERED** by top-k×N(20)+rerank (dense None→rank 3, within top-5); aggregate rank@1 5/8→4/8 (reranker reorder cost, matches D-36). Report + recommend owner-decide. _experiments/exp_c1_topk_rerank.py, docs/experiments/…md, test_experiments.py_
- [x] **C2** measured read-only: sentence-window avg −13.8% context, span retained 7/7; marginal at current chunk size (wins on multi-sentence chunks F-005/F-046). Defer; report. _experiments/exp_c2_sentence_window.py, docs/experiments/…md_
  - Baseline `.lancedb`=13b242de unchanged before/after (read-only). Adopting either default = owner decision (baseline-affecting) → NOT self-adopted.

## D. Real-PDF robustness (M6-prep — PUBLIC docs only)
- [x] **D1** `pdf_forms.py` (PyMuPDF, no new dep): `horizontal_rule_lines` (get_drawings), `text_above_rule` crop, `iter_spans`+`is_input_span` font/size filtering, `normalize_checkbox` Wingdings→[√]/[ ]. Synthetic form fixture + **3 real public PACER fixtures** smoke (found rule-lines+spans, no crash). 7 tests. _pdf_forms.py, build_form_corpus.py, documents/fixtures/court/ (git-ignored), test_pdf_forms.py_

## Pre-flagged GATE
- [GATE] **eyecite** (case/statute citation extraction) = **new pip dependency** → NOT installed (D-54 GATE: no new install). Proposed for owner approval: pure-Python, offline, Free Law Project; would extract/normalize case+statute citations for retrieve-by-authority. Build held pending owner sign-off.

---

## FINAL STATE — all non-gated tasks [x]; one [GATE] surfaced; zero [BLOCKED]
- **Suite: 240/240 OK** (was 175; +65 new tests across A0/A1/A2/A4 grid, B1–B6, C helpers, D1).
- **Egress (PID-scoped, audit-canon format):** full suite `lsof -a -p PID` → 734 samples, **0 non-loopback**, 510 caught the Ollama loopback (real, not empty). Plus live A0b prune (15 samples, 0). Logs: `eval/results/egress-2026-06-21-{a0b-prune,backlog-suite}.log` (git-ignored).
- **Baselines byte-identical (canon fold from pipeline/, 0 modified):** `.lancedb=13b242de`, `.lancedb_full=0df0525c`, `.lancedb_hyb=51e13b31` — before and after everything. No re-embed / no M2-8 re-run.
- **Never-false-accept preserved** across grid cells, fuzzy fallback, confidence, and streaming — verifier.py/clauses.py reused, never forked.
- **No new install.** Reranker (C1) + Docling TableFormer (A0) already present. eyecite = the only [GATE].
- **Not committed** (Planner commits at record).
