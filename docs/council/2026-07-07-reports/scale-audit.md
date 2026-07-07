# Scale Audit — legal-doc-intelligence @ thousands of docs (measured, M4 Pro 24GB)

_Agent report, 2026-07-07. Verbatim. All numbers measured on the dev machine (Apple M4 Pro, 12
cores, 24GB, macOS 26.5), Python 3.14.6, lancedb 0.33.0, pyarrow 24.0.0, against synthetic
LanceDB stores with random unit-norm 1024-dim float32 vectors (bge-m3 dim confirmed at
`embed_store.py:23`, `EMBED_DIM = 1024`), 900-char text payloads, 40 matters, 150 chunks/doc.
Scale mapping: 1,000 x 50-page docs ~= 150k chunks; ~3,000 docs ~= 450k chunks._

## 1. Retrieval at scale — the headline

**The vector search is not the problem. The matter-allowlist check is.** `retrieval.py:36`
(`_matter_filter`) runs `table.to_arrow().to_pylist()` — it materializes the ENTIRE store (all
vectors + all text) into Python dicts on **every matter-scoped query** just to build the set of
known matter names. Same pattern at `retrieval.py:28` (`known_matters`, served at `api.py:120`).

Component timings (top-5, ms):

| store | open_table/call | allowlist as written (retrieval.py:36) | matter-col-only scan | brute vec p50/p95 no filter | brute vec p50/p95 prefilter 2.5% |
|---|---|---|---|---|---|
| 10k | 0.48 | **1,477** | 1.4 | 3.8 / 4.1 | 3.9 / 4.6 |
| 100k | 0.46 | **15,643** (4.7GB peak RSS) | 10.0 | 19.9 / 20.6 | 18.8 / 19.6 |
| 500k | 0.41 | not run — `to_arrow()` alone = 1,014ms / 2.53GB; `to_pylist` extrapolates to **~78s and >20GB RSS -> swap death** on a 24GB box with 12GB held by Ollama | 48.8 | 96.3 / 102.0 | 86.6 / 99.0 |

End-to-end with the repo's actual `retrieve()` (includes ~130ms question embed):

| store | retrieve(matter=X) — the only path /chat uses | retrieve(matter=None) |
|---|---|---|
| 10k | **1,567ms** | 129ms |
| 100k | **15,674ms** | 153ms |
| 500k | not runnable safely | ~230ms (est) |

**Crossings, as written (matter-scoped):** >300ms at **~2k chunks (~13 fifty-page docs)**; >2s
"unusable" at **~13k chunks (~90 docs)**. The current KB has 7 rows — that is the only reason
this hasn't been felt. **Crossings after the allowlist is fixed, brute force kept:** search alone
hits 300ms at ~1.5M chunks (linear: 96ms/500k); total retrieve stays under 300ms to ~900k chunks.

**Precise fix:** validate `matter` against the SQLite catalog (`catalog.get_matter`,
parameterized, <1ms — `routes_chat.py:35` already does exactly this before calling answer,
making the store-side re-scan redundant validation), or scan only the matter column
(`table.search().select(["matter"]).limit(n)` — measured 10ms @100k, 49ms @500k) with a cached
result invalidated on ingest. The D-18 `prefilter=True` isolation at `retrieval.py:89` is
untouched either way — the allowlist is input validation, not the isolation mechanism.

**ANN index: not needed at the stated target.** Brute force at 500k = 87-96ms p50. Measured
IVF_PQ (512 partitions, 64 subvectors) on 500k: **30.4s build**, 3.0ms p50 query, prefilter
identical (3.04ms) with a BITMAP scalar index on matter (0.1s build). Adopt IVF_PQ only past ~1M
chunks or if grid concurrency needs headroom — and only after re-running the eval golden set,
since PQ is lossy recall. **The matter pre-filter helps, not hurts:** at 2.5% selectivity
brute-force prefilter was slightly *faster* (86.6 vs 96.3ms).

## 2. Embedding / ingestion throughput

bge-m3 via local Ollama `/api/embed` (900-char SAC-prefixed chunks, exactly as
`embed_store.embed_texts` sends them):

| batch | time | throughput |
|---|---|---|
| 1 | 0.14s | 7.1 chunks/s (p50 139ms — also the per-query embed floor in retrieve) |
| 8 | 0.36s | 22.3/s |
| 32 | 1.07s | 30.0/s |
| 128 | 3.94s | 32.5/s |
| 256 | 7.75s | **33.0/s ceiling (model-bound)** |

`add_chunks` (`embed_store.py:88`) sends one whole document per HTTP request — for a 150-chunk
doc that's effectively optimal batching (~4.5s/doc). Fine as-is.

**Wall-clock for 1,000 x 50-page docs (~150k chunks):**
- PyMuPDF extract (born-digital): 3.6ms/page measured -> **3 min total**
- `has_tables` gate (`table_ingest.py:80`): 21-30ms measured, ~10-25 min total
- Embedding: 150k / 33/s -> **~76 min**
- Docling table pass: 4.6s for a 2-page table PDF (warm ~1.5-2s/page) -> if 20% of docs bear
  tables, **+3-5h**
- Tesseract OCR: **1.16s/page measured** -> a fully scanned corpus (deposition transcripts!) is
  **~16h**

So: born-digital corpus ~= **1.5-2h**; scanned transcripts dominate everything at ~16h+.
**Ingest is completely uninstrumented** — zero `logging`, zero timing, zero progress in
`kb_ingest.py`, `embed_store.py`, `ingestion.py`, `routes_kb.py` (grep confirmed); the only
signal is the per-doc catalog status flip. A 16-hour ingest is invisible.

**What breaks first:** neither memory nor Ollama — the **shared thread pool**. Every endpoint is
sync `def`, and `BackgroundTasks` with a sync fn (`routes_kb.py:78`) runs on the *same* anyio
thread pool (default capacity 40) as all request handlers. Bulk-upload 1,000 files and up to 40
concurrent `ingest_document` runs occupy the pool: 40 concurrent Docling/Tesseract/PyMuPDF parses
(CPU + GIL thrash), 40 concurrent LanceDB `delete`+`add` writers on one table (optimistic-commit
conflicts), and — worst — **every other endpoint including /chat queues behind them for hours**.

## 3. Storage / metadata

- Store sizes: 40MB @10k, 394MB @100k, **1.9GB @500k**. Trivial; mmap'd scans keep RSS low.
- `open_table` per request (`retrieval.py:85`): 0.4-0.5ms. Not a problem. Leave it.
- SQLite catalog: fully parameterized, tiny rows; fine into tens of thousands of rows.
- **Version/fragment churn, measured:** the idempotent delete+add per doc (`kb_ingest.py:63-64`)
  produced version 399 and 200 data fragments after 200 doc ingests (real KB already at v22 with
  7 rows). Write overhead only 8ms/doc; search on the fragmented 30k store was 6.8ms p50 —
  fragmentation does not hurt search at this scale — but nothing ever calls
  `optimize()`/`cleanup_old_versions` (grep: zero hits), so old versions are retained forever.
  `table.optimize()` measured 0.1s.
- Hybrid/FTS footgun in currently-dead code: `_ensure_fts_index` (`retrieval.py:47`) builds on
  first hybrid query and the native FTS index does not cover rows appended after build without an
  optimize pass.

## 4. Concurrency

- **Ollama embed vs generate: no contention, measured.** Batch-32 embed 1.13s baseline;
  1.09-1.14s during an active qwen3:14b 400-token generation. Both models resident (~12GB of
  24GB).
- **Generation is the real UX floor:** 400 tokens took 22.2s (~18 tok/s).
- **LanceDB reader vs writer:** MVCC — readers unaffected; concurrent *writers* risk commit
  conflicts — another reason for a serialized ingest queue.
- Grid (`grid.py:98`, clamp <=4 workers) runs `answer()` per cell -> today each cell pays the
  full allowlist scan: at 100k that's 4 concurrent 15.6s / 4.7GB-RSS materializations per wave.

## 5. Ranked scale bombs

1. **Full-store materialization in the matter filter — `retrieval.py:36` (and `:28`/`api.py:120`).**
   Unusable at ~90 documents. Fix: catalog validation or cached matter-column scan (~5 lines);
   isolation (prefilter) untouched.
2. **Ingest concurrency = the request thread pool — `routes_kb.py:78` + all-sync handlers.**
   Bulk upload starves every endpoint for hours. Fix: one dedicated ingest worker thread +
   `queue.Queue` (~20 lines); serial writes also end version-churn races.
3. **Zero ingest instrumentation — `kb_ingest.py` (whole file).** Fix: per-stage `perf_counter`
   logging + queued/done counters via the existing catalog (~15 lines).
4. **OCR/Docling per-page cost meets thousand-doc reality** (1.16s/page Tesseract measured).
   Inherent model cost: run in the (new) single ingest worker with 2-3 process-level OCR workers
   max; set owner expectations ("scans ingest overnight").
5. **No LanceDB maintenance, ever.** Fix: `tbl.optimize()` every N=50 ingests (measured 0.1s).
   Explicitly not urgent for search latency — measured impact today is nil.

**Explicitly fine as-is (measured, don't touch):** brute-force vector search to 500k chunks
(96ms p50 / 102ms p95); per-request `open_table` (0.5ms); the SQLite catalog; `add_chunks`
whole-doc batching (at the 33 chunks/s model ceiling); Ollama embed/generate coexistence;
the delete+add idempotency write cost (8ms/doc); reranker and hybrid staying off at current
scale (see search-quality audit for the at-scale counterargument). The span verifier and matter
prefilter need no changes for scale.
