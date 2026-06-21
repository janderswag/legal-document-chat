# Hybrid (dense + BM25) retrieval — measured lift (Task 5 / G-HYB)

_Reading-aid measurement (objective rank lookups, not a pass/fail scorer). 2026-06-20._

## Setup
- 63 present-fact golden questions; matter-scoped retrieval, `top_k=5`.
- A chunk is "correct" iff `source_filename` + `page_number` match the manifest AND the
  normalized `verbatim_span` is a substring of the chunk text.
- Measured on a throwaway `.lancedb_hyb` (a copy of the live store's 50 chunks) so the
  live `.lancedb` is never FTS-indexed / mutated (M2-8 baseline stays byte-identical).
- Harness: `pipeline/run_hybrid_eval.py`. Egress-monitored: 0 non-loopback.

## Result

| mode   | rank@1        | MRR    |
|--------|---------------|--------|
| dense  | 48/63 = 76.2% | 0.8524 |
| hybrid | 44/63 = 69.8% | 0.8294 |
| **delta** | **-4 (rank@1)** | **-0.0230** |

## Honest conclusion (mirrors the D-36 reranker finding)
On this 6-doc / 50-chunk synthetic corpus, **RRF hybrid does not help — it is slightly
negative**. BM25's exact-term matches occasionally outrank the semantically-correct
chunk for short, paraphrased questions, and RRF then demotes the dense winner. This is
the same "neutral-to-negative lift at small scale" honesty as the reranker (D-36).

**Decision:** `hybrid` stays **OFF by default** (`hybrid=False`), kept behind the flag
for production scale, where BM25 earns its keep on larger corpora and keyword/number-
exact queries (e.g. clause numbers, statute cites, dollar amounts). The matter
pre-filter (D-18) is applied to both arms before fusion, so enabling it never weakens
cross-matter isolation.

## Dependency note
LanceDB 0.33 **removed tantivy-based FTS upstream** ("Tantivy-based FTS has been
removed... recreate with native FTS"), and the `tantivy` wheel does not build on Python
3.14. The plan's `tantivy` install gate is therefore obsolete: hybrid uses LanceDB's
**native** BM25/inverted FTS index — **no `tantivy` dependency was installed**.
