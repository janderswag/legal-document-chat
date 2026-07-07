# Scale retrieval eval — per-query-class recall at realistic matter sizes (D-69)

_First run 2026-07-07. Harness: `pipeline/build_scale_store.py` (store) +
`pipeline/run_scale_eval.py` (Phase A metrics). This eval is the standing [GATE] for any
claim about retrieval at scale and for future retrieval-config changes._

## Why this eval exists

The 50-chunk golden store cannot see recall at scale: top-5 there is 10% of the whole
store, and the D-66 search audit measured identifier queries already failing dense-only
at that size. Every scale decision ("hybrid off", "rerank off", "top_k=5") was
previously extrapolated from a regime where it could not be tested.

## The store (deterministic, seed 42; scratch `.lancedb_scale`, never a live store)

- **5,114 chunks** total, built through the PRODUCTION KB chunker (`kb_ingest._chunk_pages`)
  — the exact pipeline `/chat` retrieves against, not the richer eval chunker.
- The original golden corpus (22 docs), matter-mapped per the GOLDEN manifest.
- **50 large eval matters (~70-77 chunks each)**: 40 planted-fact matters + 10
  hard-negative twin matters. Each planted fact sits among ~8 SAME-GENRE distractor
  docs (other invoices/statutes/contacts/defined terms/clauses) plus ~24 generic filler
  contracts — without this, the matter pre-filter makes in-matter recall trivially
  perfect and the eval measures nothing.
- **113 questions**: 63 golden present-facts (re-asked against this store) + 50
  stratified: identifier(8), statute-cite(5), party-name(7), defined-term(6),
  paraphrase(8), cross-doc(6), hard-negative twins(10). Tracked in
  `eval/scale_questions.jsonl`.

## Results (Phase A: gold chunk in top-k, per class)

recall@5:

| class | dense | dense+rerank50 | hybrid | hybrid+rerank50 |
|---|---|---|---|---|
| identifier | 100% | 100% | 100% | 100% |
| statute-cite | 100% | 100% | 100% | 100% |
| party-name | 100% | 100% | 100% | 100% |
| defined-term | 100% | 100% | 100% | 100% |
| paraphrase | 100% | 100% | **88%** | 100% |
| cross-doc | 100% | 100% | 100% | 100% |
| hard-negative | 100% | 100% | 100% | 100% |
| golden | **98%** | 95% | 100% | 95% |

Candidate-pool recall@50: **100% every class, both arms** (dense and hybrid).

## Decisions the numbers force (D-69) — several CONTRADICT the going-in plan

1. **Default stays dense top-5.** At realistic matter sizes (~75 chunks) with the matter
   pre-filter, dense retrieval is at ceiling in every stratified class INCLUDING bare
   identifiers. The D-66 failing probes were store-wide searches; matter scoping is
   what saves dense. The plan said "flip hybrid on" — the data says don't: raw-question
   hybrid costs paraphrase 12 points (BM25 stopword pollution) for +2 on golden.
2. **Reranker stays OFF.** Post-chunking-repair, top-5 ≈ the whole reachable pool, so
   the cross-encoder can only reorder — and it demotes gold chunks (98→95, 100→95).
   The audit's "rerank recovers recall" held only for the pre-repair pool misses.
3. **The big lever was CHUNKING, not retrieval config.** Golden recall@5 under the old
   production chunker (blind 900-char window, empty SAC breadcrumb): **81%**, with 13%
   of gold chunks absent from the top-50 entirely. After 1d (section-aware cuts +
   `[Matter | Type | Section]` SAC + real document_type): **98%**, pool 100%. This
   quantifies the D-66 finding that production embedded a poorer format than the one
   the published eval numbers were earned on.
4. **The refusal second pass covers the tail.** The single dense miss@5 is in the
   pool@50 and is exactly what the 1b retry (top_k=10, candidate_k=100, hybrid with
   ANCHOR-fed FTS — numbers/quoted strings/prefixed ids/proper nouns extracted from the
   question) is built to catch, at zero cost to the happy path. The retry ends at the
   unchanged verifier and is adopted only if span-verified and non-refusal.

## Honest notes / eval bugs found while building it

- Run 1 (pre-1d chunker): golden 81% — but 8 of those misses turned out to be an EVAL
  BUG, not retrieval: the store build mapped the Renfrew demand letter to the corpus
  manifest's matter label while the golden questions scope it to the Pemberton matter
  (matching the live store). With the mapping fixed, the true pre-1d number would be
  ~93%; the post-1d comparison above (81→98) therefore OVERSTATES the chunking lift —
  the honest attribution is roughly 93→98 from chunking, the rest was the eval bug.
- Phase B (answer-level refusal rates with the LLM per config) was not run separately:
  Phase A pool metrics made the config choice unambiguous, and answer-level behavior is
  covered by the golden-set [GATE] (72 questions end-to-end, incl. 9 NF refusals) run
  against the production path with the second pass active. Record: `run-2026-07-07-m1-secondpass`.
  **Gate outcome: 63/63 (62 strict + F-042 alt-page credited) — the second pass
  RECOVERED F-026**, the false refusal open since the 2026-06-20 baseline (D-40), while
  all 9 NF questions still refuse and displayed fabrications remain 0. The prior best
  was 62/63.
- Store and questions regenerate deterministically (seed 42). Re-run cost: ~6 min store
  embed + ~7 min Phase A on the M4 Pro.
