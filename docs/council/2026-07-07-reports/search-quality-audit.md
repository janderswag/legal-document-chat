# Retrieval-Quality Audit — legal-doc-intelligence (adversarial, 2026-07-07)

_Agent report, verbatim. Read-only probes were run against the dev stores (`.lancedb` dense;
`.lancedb_hyb` for hybrid, already FTS-indexed)._

**Scope verified in code.** Dense-only bge-m3 retrieval, `top_k=5`, `rerank=False`,
`hybrid=False` (`pipeline/retrieval.py:67-68`; `answering.py:263` hardcodes `rerank=False` and no
route ever passes `top_k`, `hybrid`, or `rerank` — production is pinned to dense top-5). Matter
pre-filter is a hard LanceDB `prefilter=True` allowlisted filter (`retrieval.py:31-39, 88-89`) —
genuinely sound. Verifier is mechanical normalized-substring span overlap (`verifier.py:1-23`) —
genuinely sound. Golden set: 63 present-fact + 9 refusal questions over 22 synthetic docs /
**50 chunks** in `.lancedb`. Hybrid was measured neutral-to-negative on that store and left off
(`eval/HYBRID_LIFT.md:15-31`).

## 1. Recall at scale: the "hybrid off" decision does not transfer

**(a) The regime is degenerate.** `top_k=5` over 50 chunks = the top **10%** of the entire store;
after the matter pre-filter a matter has ~8-15 chunks, so top-5 is a third to half of the
candidate set. Recall@5 is near-saturated for *any* ranker. At 5,000 docs (~150k-400k chunks),
top-5 is ~0.002% of the store. Dense recall@k monotonically decays as distractor count grows
(extreme-value statistics — the standard reason small-corpus retrieval evals don't transfer).

**(b) The golden set is dense retrieval's home turf.** 54+ of 63 questions *name the document*
("In the Nimbus-Pemberton MSA, ..."), lexically mirroring the SAC prefix baked into every
embedding (`chunking.py:150`), and were authored from the spans. Attorneys type **exact
anchors**: party names, case numbers, bar numbers, dollar amounts, statute cites, defined terms.

**(c) Measured on the actual store, exact-term queries already fail dense-only at 50 chunks:**

| query | dense top-5 (literal hit rank) | hybrid (RRF) |
|---|---|---|
| `388214` (bar number) | rank 4 | rank 1 |
| `$18,550` | rank 4 | rank 1 |
| `18,550` (no `$`) | **NONE in top-5** | rank 2 |
| `Sabrina Voss` | rank 1 | rank 1 |

**Failure order at scale:** (1) bare identifiers, (2) statute/clause cites, (3) rare proper
nouns, (4) exact defined-term phrases, (5) last, genuinely paraphrased conceptual questions — the
only class the golden set really tests.

Caution: `"What fee is $18,550?"` got a literal hit in **neither** arm — the BM25 arm is fed the
raw question (`retrieval.py:95`), so question words dilute the exact term and the FTS tokenizer
mangles `$18,550`. Hybrid needs query-side term extraction (numbers, quoted strings, capitalized
names) fed to the FTS arm. Also: a near-miss probe `$18,500` (absent; corpus has `$18,550`)
returned five plausible fee chunks with zero "no exact match" signal.

## 2. The refusal trade-off: false-refusal rate grows mechanically with corpus size

Refusal fires when the top-5 chunks don't support the answer (`answering.py:46-49`), so
**false-refusal rate ~= 1 - recall@5** on present-fact queries. Right trade (a refusal is
recoverable, a fabrication is not), steep cost curve:

- At 50 chunks: 1/63 = **1.6%** false refusal (F-026, D-40).
- A matter growing from ~10 chunks to ~2,000 increases the distractor pool ~200x. **10-25% false
  refusal on real attorney query mixes is the realistic range at scale** — a mechanism-grounded
  estimate to be measured, not asserted.

**Mitigations that don't touch the verifier** (all reorder/expand *candidates*):

1. **`candidate_k` up + cross-encoder rerank — already built, already measured to recover F-026**
   (`retrieval.py:101-107`; D-55/C1: candidate_k=20 + rerank recovers the caption chunk
   None->rank 3). Cheapest lever: `candidate_k=50-100`, rerank to 5.
2. **Hybrid on + query-term extraction** (flag exists; RRF preserves the pre-filter on both
   arms). Directly fixes the identifier class a reranker can't fix (it can't rescue a chunk dense
   never retrieved).
3. **Adaptive top_k / two-pass escalation:** on refusal, re-run once with `top_k=10-12,
   candidate_k=100, hybrid+rerank` before showing the refusal. Refusal only strengthens.
4. **Multi-query expansion** (local LLM paraphrases -> union -> rerank). After 1-2.
5. **UI mitigation:** attach "closest passages (unverified)" to every refusal — the `sources`
   event machinery already exists (`answering.py:363`, `routes_chat.py:94-101`); the
   fuzzy-fallback labeling discipline (`fuzzy_fallback.py:1-14`) shows how to display
   non-verified material safely.

Not recommended: lowering the refusal bar or letting confidence gate anything
(`confidence_from_logprobs` is correctly display-only).

## 3. Missing search modalities: there is no search feature at all

Every retrieval surface is QA-shaped: `/chat`, `/chat/stream`, `/answer`, `/clauses/review`,
`/grid`. **No `/search` endpoint exists.** Absent for a search-first attorney workflow:

- **Exact phrase / boolean search.** Native FTS index code exists (`retrieval.py:42-49`) but is
  reachable only inside the hybrid QA path. `GET /search?q=&matter=` doing pure BM25 with the
  same matter pre-filter is nearly free.
- **"Find every mention" (exhaustive, not top-k)** — arguably the single most-used tool in real
  document review. Nothing in the API can answer it.
- **Doc-type filter: impossible with the current schema.** Chunkers produce `document_type`
  (`chunking.py:154`, `kb_ingest.py:41`) but the LanceDB schema **drops it** —
  `embed_store.py:36-45` has no `document_type` field and `_rows_from_chunks`
  (`embed_store.py:87-95`) doesn't copy it. Filtering "contracts only" requires a schema
  migration + re-ingest.
- **Date-range filter:** no date field anywhere; no date extraction at ingest.
- **Party filter:** no party metadata; matter is the only entity axis.
- **Browse:** viewing exists (`routes_kb.py:83-127`) but no per-document chunk/section browse or
  within-document search.

## 4. Eval debt: what 63 synthetic present-facts cannot see

Validates well: span-verification correctness (never-false-accept, D-40), refusal-on-absent
(9/9), cross-matter isolation (2 DRM checks). **Cannot detect:** recall at scale; exact-term /
identifier queries (zero golden questions are bare identifiers); paraphrase robustness (questions
authored from spans, mostly doc-naming); hard-negative confusion (one contract per type — "right
clause, wrong contract" untested beyond 2 DRM questions); transcripts (none in corpus);
false-refusal rate as a tracked metric.

**Minimal next eval (needle-at-scale):** generate ~1,000-5,000 filler synthetic docs (generators
in `build_corpus.py`/`build_full_store.py` are most of this), embed into a scratch store (never
`.lancedb`), re-ask the existing 63 questions plus ~40 new ones stratified by query class
{identifier, statute-cite, party-name, defined-term-phrase, paraphrase, cross-doc}, reporting
**recall@5 / recall@k / refusal-rate per class** for dense vs dense+rerank(k=50) vs
hybrid+rerank. Add ~10 hard-negative pairs (near-identical contracts, different
matters/amounts). One script in the mold of `run_hybrid_eval.py`.

## 5. Top-5 retrieval-quality risks, ranked

All fixes leave `verifier.py` and the D-18 matter pre-filter byte-identical.

| # | Risk | Evidence | Cheapest credible fix |
|---|---|---|---|
| 1 | **Exact-term blindness** (identifiers, amounts, cites) — the highest-value attorney queries fail dense-only first | probes above; HYBRID_LIFT itself predicts BM25 "earns its keep" at scale | Flip `hybrid=True` in `_assemble_context` + extract numbers/quoted-strings/proper-nouns into the FTS arm (~30 lines); validate with the per-class eval |
| 2 | **False-refusal growth at fixed top_k=5** | D-40, D-55/C1; refusal = 1-recall@5 by construction | `rerank=True, candidate_k=50` at `answering.py:263` + refusal-triggered second pass with k=10; owner-gated baseline re-measure |
| 3 | **No exhaustive/exact search modality** | route inventory; FTS code stranded | `GET /search` (BM25 + LIKE, matter-pre-filtered, paginated); purely additive |
| 4 | **Eval cannot see any of the above** — decisions locked in on a 50-chunk corpus | §4 | The 1k-doc scratch-store per-query-class eval; one script, no new deps |
| 5 | **Production KB embeds a degraded SAC and drops metadata** — KB chunks get `[Matter: slug \| Section: ]` with empty section, no doc type (`kb_ingest.py:43` vs `chunking.py:150`); `document_type` never reaches LanceDB | eval numbers earned on the *richer* pipeline; production runs the poorer one | Port section-aware chunking + full SAC into `_chunk_pages`; add `document_type` (+ date) to `_SCHEMA`; re-ingest KB store only |

**Genuinely fine:** the mechanical span verifier and normalization contract; the matter
pre-filter design; chunk-derived citations; refusal-over-fabrication; non-gating
confidence/fuzzy hints; HYBRID_LIFT's own honesty — the measurement was correct, only its
extrapolation ("stays off") outruns the evidence.
