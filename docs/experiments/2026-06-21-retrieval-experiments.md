# Retrieval experiments — C1 (top-k×N + rerank) & C2 (sentence-window)

_2026-06-21, Builder. SCRATCH/READ-ONLY against the eval baseline `.lancedb` — no mutation,
no re-embed, no M2-8 re-run (those are `[GATE]`). Baseline hash `13b242de…` unchanged
before/after. Harnesses: `experiments/exp_c1_topk_rerank.py`, `experiments/exp_c2_sentence_window.py`._

## C1 — top-k×N-before-rerank vs current dense top-k=5 (F-026 hypothesis)

**Setup:** for each question, compare the rank of the *correct* chunk (right file+page,
contains the golden span) under (a) current dense `top_k=5`, vs (b) `candidate_k=20` dense
→ local `bge-reranker-v2-m3` → top-5.

**F-026 (the documented recall miss — counsel named in the page-1 caption):**

| path | rank of the page-1 caption chunk |
|------|----------------------------------|
| dense top-5 | **not retrieved** (None) |
| top-k×N (20) + rerank → 5 | **rank 3** (within top-5) |

→ **Hypothesis CONFIRMED: top-k×N-before-rerank RECOVERS F-026.** The page-1 caption chunk
is in the dense top-20 but below rank 5; pulling a wider candidate pool before reranking
surfaces it into the answerable top-5. (D-51 framed this as a *hypothesis, measure don't
assert* — now measured: it fixes this specific recall miss.)

**Present-fact aggregate (8 facts across matters), rank@1:**

| path | rank@1 |
|------|--------|
| dense top-5 | 5/8 |
| top-k×N + rerank | 4/8 |

→ The reranker is **not a free win on rank@1** at this corpus scale: it reorders a couple of
already-rank-1 facts down to rank 2 (still top-5) while pulling F-026 from None→3. This
matches **D-36** (reranker = neutral lift on the 6-doc corpus). Net: it trades a little
top-1 precision on easy facts for recall on the hard caption miss.

**Recommendation (for the owner/Planner — not self-adopted):** the recall fix is real but
comes with a reranker-reorder cost; both are *within top-5* so answerability improves for
F-026 without losing the others from the retrieved set. A production-scale corpus is the
right place to re-measure before flipping the default (`rerank=False` stays, D-36). Turning
this on is a baseline-affecting change → owner decision, not a Builder default.

## C2 — sentence-window retrieval (kotaemon pattern)

**Setup:** retrieve the top chunk, then measure a sentence-window (matched sentence ±1
neighbor) vs the full chunk — context size reduction while still containing the golden span.

| fact | chunk chars | window chars | reduction | span retained |
|------|------------|--------------|-----------|---------------|
| F-001 | 306 | 306 | 0% | ✓ |
| F-004 | 310 | 309 | 0.3% | ✓ |
| F-005 | 295 | 204 | **30.8%** | ✓ |
| F-007 | 286 | 285 | 0.3% | ✓ |
| F-009 | 482 | 482 | 0% | ✓ |
| F-010 | 165 | 165 | 0% | ✓ |
| F-046 | 285 | 100 | **64.9%** | ✓ |

**avg context reduction 13.8%; span retained 7/7.**

→ **Marginal at the current chunk granularity.** Our chunks are already small + section-aware
(M2-2 SAC), so the window usually equals the chunk; the win concentrates where a chunk holds
several sentences (F-005, F-046). Sentence-window pays off mainly with *larger* chunks — same
reasoning that deferred hybrid/RRF at this scale (D-49). Span is always retained (fail-open).

**Recommendation:** defer; revisit if/when chunk size grows (e.g. table-heavy or
long-section real PDFs). No change to the verifier or offsets — the window is a context-
shaping idea, not a verification change.

## Invariants

- READ-ONLY: baseline `.lancedb` = `13b242de…` before and after (canon fold).
- No re-embed, no re-index, no M2-8 re-run. No new install (reranker already present, D-36).
- These are measurements + recommendations; adopting either is an owner decision (a default
  change is baseline-affecting). Never-false-accept is untouched (retrieval ranking only).
