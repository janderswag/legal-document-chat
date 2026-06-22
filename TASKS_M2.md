# TASKS_M2.md — Milestone 2-3 Checklist (custom citation-grade pipeline)

> Authorized by **M1-13 PASS (D-33)**. Separate from the M1-only `TASKS.md`. Each task is small,
> tested, and **owner-gated** (installs/new deps approved one step at a time, same as M1).
> Build decisions are locked in `DECISIONS.md` D-13..D-20; constraints in `BUILDER_STATE.md` §5/§7 and
> `CLAUDE.md`; architecture in `CE_PLAN.md` §5–§10.
>
> **Goal:** deliver the verifiable **page + span** citation the turnkey stack proved impossible (M1),
> plus matter-scoped retrieval + reranking that fixes the M1 cross-matter noise.

## Sequence

- [x] **M2-1 — Project scaffold + PyMuPDF page-accurate ingestion proof.** _Done 2026-06-20: pipeline
      Python project + isolated venv (PyMuPDF only). `extract_pages` returns per-page
      `{source_filename, page_number, page_text}` for all 6 PDFs (contiguous 1-based; counts
      3/3/3/2/2/2). **Span-on-page verified vs manifest** (incl. F-019 hyphen-wrap normalization);
      spans land on their `page_number` and nowhere else (page-specific). Egress: socket-guard test +
      live `lsof` = zero network sockets (SC-6 at ingestion). The M1 page-metadata gap (D-29) is closed
      at ingestion — the substrate for M2-6 span verification._
- [x] **M2-2 — Structure + chunking with page/section metadata.** _Done 2026-06-20: 50 chunks, each
      carrying `{source_filename, matter, page_number, section, char_start, char_end}` +
      `embedding_text` (SAC prefix). **Offset integrity:** `page_text[char_start:char_end] == chunk.text`
      for all 50 (offsets index M2-1 page text → substrate for M2-6). **Span→one-chunk** verified
      (F-019/F-009/F-025/F-047 each resolve to exactly one chunk on the manifest page; matter matches).
      **DRM (D-18):** F-009 vs F-025 identical clause carries DISTINCT SAC prefixes (Pemberton MSA Art.9
      vs Castellano lease §14) — the M1 cross-matter fix taking shape. Docling model fetch gated
      (`DOCLING_ALLOW_MODEL_FETCH` unset → offline default, zero sockets). **Real-PDF heading risk: see
      Risks below.**_
- [x] **M2-3 — Vector store: LanceDB** (embedded, D-34) with matter + page payloads; embed via
      **system Ollama `bge-m3`** (D-11 pinned). _Done 2026-06-20: 50 chunks embedded from
      `embedding_text` (SAC), all **1024-dim**, into a git-ignored `pipeline/.lancedb/` table; payload
      `{source_filename, matter, page_number, section, char_start, char_end, text}` round-trips
      (`page_text[char_start:char_end]==text`). Similarity sanity: F-001→MSA p1 @rank0, F-046→Tessaro p2
      @rank0. Loopback-only (embedding hits only `:11434`), zero non-loopback egress._
      **⚠ M2-4 finding:** plain vector search + SAC handles matter-NAMED queries, but matter-AGNOSTIC
      queries still interleave both matters' boilerplate → **hard metadata pre-filter (filter-before-
      similarity on `matter`) is REQUIRED** (D-18); SAC alone is insufficient.
- [x] **M2-4 — Retrieval: metadata-filter-before-similarity (D-18, D-35).** _Done 2026-06-20: `retrieve(
      question, matter=None, top_k)` embeds via `bge-m3` (loopback) and hard-pre-filters LanceDB on an
      allowlist-validated `matter` BEFORE similarity. **Cross-matter KILLED both directions** (scoped
      Pemberton→only F-009/Nimbus file; scoped Castellano→only F-025/Greenfield file). `matter=None` =
      honest search-all (returns both). Pre-filter is before similarity (not top-k-then-drop); matter
      value allowlist-validated (no injection); zero non-loopback egress._
- [x] **M2-4b — Reranker `bge-reranker-v2-m3` (D-16, D-36).** _Done 2026-06-20: local in-process
      cross-encoder (FlagEmbedding; `HF_HUB_OFFLINE`/`TRANSFORMERS_OFFLINE` after one-time fetch;
      revision pinned `RERANKER_REVISION` in `reranker.py`). Reorders **only** the matter-filtered set —
      no cross-matter regression (F-009/F-025 both ways). **Lift NEUTRAL on the 6-doc corpus** (3/4
      facts stay rank0, F-046 0→1; ΔMRR ~-0.006, rank@1 48→46) — honest finding, not a regression.
      Offline + zero non-loopback egress. **Defaults `rerank=False`** (D-36 refinement); opt-in
      `rerank=True`._
- [x] **M2-5 — Answering (hand-rolled, D-37; no LlamaIndex).** _Done 2026-06-20: `answer(question,
      matter)` → matter-filtered (`rerank=False`) context with per-chunk source labels → §10
      grounded+cite+refuse → `qwen3:14b` (loopback, `<think>` stripped). Verified: present facts cite
      correct **filename + REAL page** (M1 page gap closed); not-found returns the exact D-30 sentence +
      footer with empty citations; DRM F-009 answers only from Pemberton docs; structured result exposes
      `{chunk_id, source_filename, page_number, char_start, char_end, text}` grounding; loopback-only.
      **🐛 Known bug → fix as M2-6 precondition:** `_parse_citations` structured-tag branch emits the
      **model-asserted** page, not the chunk-derived one — can surface a wrong page. Citations must be
      **chunk-derived** (D-38)._
- [x] **M2-6 — Mechanical span-level citation verification (D-19).** _Done 2026-06-20: precondition
      D-38 landed (displayed filename+page now **chunk-derived** — asserted page:9 on a true-p2 chunk →
      verified page=2; the M2-5 leak is FIXED). `verify_answer` mechanically checks each cited span
      overlaps a retrieved chunk's `char_start..char_end` on its page (normalized: reflow ws / `-\n`→`-`);
      `answer()` now returns `{…, rejected_claims}`. True positives verify (F-004/F-046/F-009);
      fabricated span + right-text/wrong-chunk pointer both → 0 citations + 1 surfaced `rejected_claim`
      with an offset reason (not silently dropped); reflow spans still verify; verifier imports no
      network module; loopback-only. **Verifiable PAGE+SPAN citation — the M1-impossible capability —
      works in code.**_
- [x] **M2-7 — FastAPI HTTP surface** (D-13, D-41), loopback-only. _Done 2026-06-20, independently
      Tester-confirmed (live uvicorn + curl over HTTP, not TestClient/cache). Thin app (`pipeline/api.py`)
      over the existing `answer()`: **`POST /answer`** (`{question, matter|null}` → answer +
      **chunk-derived, span-verified** citations + `rejected_claims`; `matter` validated against the
      D-35 allowlist — injection-shaped value → 400, raw text never interpolated) + **`GET /health`**.
      **HTTP body byte-identical to a direct `answer()` call** (pure pass-through, no model-asserted page
      reintroduced) for F-004 (present → `nimbus_pemberton_msa.pdf` p2, span-verified, `rejected_claims`
      []) and NF-001 (exact D-30 refusal, citations []). **Bind `127.0.0.1:8000` only** (`lsof`: one IPv4
      LISTEN, no `0.0.0.0`/IPv6); **no auth** (D-41); **no action route** (only GET/POST above + read-only
      `/openapi.json`; PUT/DELETE/PATCH → 405); **no egress** beyond the loopback Ollama call — continuous
      `lsof` monitor over live requests → git-ignored `eval/results/egress-2026-06-20-m2-7.log`, **0
      non-loopback**; clean shutdown (port released). Install: FastAPI + uvicorn, pinned. (D-2/D-4/D-25)._
- [x] **M2-8 — Full-72 page+span golden re-run (the headline M2 proof, D-39).** _Done 2026-06-20 =
      **CONDITIONAL PASS** (capability proven; 3/4 gates clean). Egress-monitored (D-31); raw →
      git-ignored `eval/results/run-2026-06-20-m2.jsonl`. **Displayed fabrications 0** (hard-zero holds —
      the verifier fails **conservatively**, the safe direction), **NF refusal 9/9**, **DRM 2/2** (no
      cross-matter, both verified). **Page+span 93.7% strict** (under the ≥95% gate) solely from
      **verifier false-rejects of truthful, correctly-grounded answers** whose spans use escapes the
      normalization didn't cover: **F-014** backslash `\"…\"`, **F-016** HTML entity `&quot;…&quot;`.
      Both flip to PASS under `html.unescape` + backslash-strip → **≥96.8%**. **→ FINAL PASS at M2-8a
      (D-40): 62/63 = 98.4%.**_
- [x] **M2-8a — Normalization fix + targeted re-run → FINAL PASS.** _Done 2026-06-20 = **FINAL PASS**
      (D-40), independently Tester-confirmed. Verifier normalization extended to **`html.unescape` +
      strip backslash-escaped quotes**, applied **symmetrically** to span + chunk text (test-first);
      F-042 **alternate-page** rule (§6.5) encoded in the verification path. Targeted re-run flipped
      exactly **F-014** (`\"`) and **F-016** (`&quot;`) → verified (both chunk-derived **page 1**),
      **zero** other changes (no regressions / no spurious verifications). Conservative-failure
      invariant HELD (self-authored escaped-but-false span still → `rejected_claim`, no false-accept).
      **Final: page+span 62/63 = 98.4% (≥95%), 0 displayed fabrications, NF 9/9, DRM 2/2.** **F-026 the
      lone genuine miss — NOT force-passed** (recall gap, tracked in Risks). Loopback-only re-verified
      (`eval/results/egress-2026-06-20-m2a.log`, 0 non-loopback, SC-6/D-31). Raw re-run →
      git-ignored `eval/results/run-2026-06-20-m2-rerun.jsonl`._
- [x] **M2-9 — Docker Compose deployment** (D-20, **D-43**). _Done 2026-06-20, independently
      Tester-confirmed + Planner-verified against `Dockerfile`/`docker-compose.yml`. Single-service
      Compose (FastAPI pipeline); **no Qdrant** (D-34), **no LlamaIndex** (D-37), **no UI**, reranker OFF.
      **Ollama on host** reached via `LDI_OLLAMA_URL=http://host.docker.internal:11434` +
      `host.docker.internal:host-gateway` — host bind unchanged, `OLLAMA_HOST` unset. Published
      **`127.0.0.1:8000:8000` only** (never `0.0.0.0`, D-4); LanceDB **volume-mounted read-only** (never
      baked, D-28); image COPYs `pipeline/*.py` + serve-only deps (no doc bodies / `.env` / `.lancedb`).
      Live: `/health` + `/answer` (F-004) over loopback **parity** with `answer()`; egress-monitored
      (D-31) **0 non-loopback** (`eval/results/egress-2026-06-20-m2-9.log`, git-ignored); clean
      teardown. **⚠ Binding constraint (D-43a): COMPOSE-ONLY** — the container CMD binds `0.0.0.0`
      in-namespace, so a bare `docker run -p 8000:8000` would expose off-host (hard rule #4); deploy via
      `docker compose` only._
      **🎉 Milestone 2-3 COMPLETE (D-44).**

## M2/M3 acceptance-gap closeout (CE_PLAN cross-reference, 2026-06-20, D-45)

> The M2-1..M2-9 checklist above proved the citation-grade **capability** (page+span eval). A
> cross-reference against **CE_PLAN §2 SC-1..SC-7** + **§14 M2/M3 acceptance** found these acceptance
> items still **open** — the honest remaining work before a *formal* CE_PLAN Milestone-4 attorney demo
> (which requires SC-1..SC-7 all green). Each is small, tested, owner-gated, same discipline.
>
> **▶ Full sequenced plan: `docs/superpowers/plans/2026-06-20-m2m3-gap-closure.md`** (7 Builder tasks,
> one per relay turn, each mapped to a CE_PLAN SC). The G-items below are the high-level gaps; the plan
> decomposes them and adds an **OCR-robustness** task (degraded synthetic scans + the two routing-edge
> fixes) to harden SC-2 short of real data (real-scan validation stays M6).

- [x] **G-SC5 — Demo source-viewer UI (SC-5).** _Done 2026-06-20 (D-45). Read-only `GET /` +
      `/matters` + path-locked `/source/{file}` on the existing loopback FastAPI app; a citation opens
      the original PDF at the cited page (`#page=N`). No new deps; `/answer` untouched (parity holds);
      traversal rejected (TDD); loopback-only; synthetic only. Closes the one M3 item that needed a UI._
- [x] **G-SC2 — OCR / scanned PDFs (SC-2 at extraction level, D-15, §8 step 3).** _Done 2026-06-20,
      Tester-confirmed. `extract_pages_ocr` per-page routes PyMuPDF text-layer pages vs. Tesseract
      (`pytesseract==0.3.13` → system `tesseract` 5.5.2, `eng.traineddata` local, **no model fetch**;
      EasyOCR/RapidOCR absent). ≥5 synthetic 300-DPI image-only PDFs under git-ignored
      `documents/synthetic_corpus/scanned/`; all present-fact spans recovered at token-coverage 1.00 on
      their **own** page (page-uniqueness holds), confidence 93–95, `ocr_failed` fail-loud flag present.
      Born-digital path **byte-identical** (OCR not invoked); **zero network egress** (socket-guard);
      live `.lancedb` + M2-8 eval artifacts **untouched** (not re-embedded / not re-run). **⚠ SC-2 closed
      only at the EXTRACTION layer — OCR text is NOT yet chunked/embedded/retrievable** (end-to-end
      "searchable" requires wiring OCR into ingest→index; folded into G-SC1). Validated on **clean
      synthetic rasters, not real scans** (re-validate at M6)._
_Closed via the 7-task gap-closure batch (D-47, Tester-confirmed + Planner-verified, commits
`89c7c66`→`c2cc89f`; baseline `.lancedb`/M2-8 untouched; new stores `.lancedb_full`/`.lancedb_hyb`
git-ignored):_
- [x] **G-SC1 — 20–50 doc multi-format corpus + SC-2 integration (SC-1).** _🟢 22 docs / 4 types /
      pdf+docx+txt(+md); per-file pass/fail report; idempotent (checksum); quarantine + `.error.txt`.
      OCR pages wired into chunk→embed→index in `.lancedb_full` — an OCR'd page (velez scan) is
      span-verified-answerable (SC-2 e2e). `python-docx` installed._
- [x] **G-OCR-ROBUST — OCR robustness (SC-2 hardening).** _🟢 degraded synthetic scans (skew/noise/
      150-DPI/JPEG) recover above the confidence floor; heavy-degrade → `ocr_failed`; sparse-digital page
      stays PyMuPDF; mixed text+image page → `source=="mixed"`, embedded text recovered. **Real-scan
      final validation = M6** (synthetic rasters ≠ real scans)._
- [x] **G-HYB — Hybrid dense+BM25 retrieval (M3).** _🟢 implemented via LanceDB **native FTS** + RRF
      behind the matter pre-filter (`tantivy` not needed — deviation accepted). **Lift NEGATIVE at
      6-matter scale (−4 rank@1) → default-off** (D-36 mirror); re-evaluate at production scale._
- [~] **G-LAT — `<3s` first-token latency.** _🟡 **instrumented but target NOT met** — independent median
      **~3.6s**; `answer()` parity preserved. Honest yellow; the "production hardware fixes it" read is a
      **hypothesis to validate on D-22 hardware**, not proven. Carry to the pre-M4 latency decision._
- [x] **G-SC7 — Redeploy-from-scripts proof (SC-7).** _🟢 `deploy/up|down|restore.sh` + README; live
      down→up→/answer→restore→down, compose-only, loopback-only, 0 egress, host Ollama bind unchanged._

## M-ENRICH — capability workstream from the OSS evaluation (D-49, D-50, 2026-06-21)

> Owner-directed adoption roadmap from the 9-repo deep dive (`docs/research/2026-06-21-oss-evaluation.md`).
> Sequence **1→3→2**, transcripts a separate track. Same discipline: small, test-first, owner-gated,
> baseline `.lancedb`/M2-8 byte-identical. Latency yellow (G-LAT) unaffected.

- [x] **T-TBL — Docling TableFormer tables, feature END-TO-END (D-50, D-53).** _🟢 DONE 2026-06-21,
      Tester GREEN ×7 + Planner-verified + committed. Tables span-verifiably citable; never-false-accept
      holds on table chunks; offsets never mixed (self-relative); prose path byte-identical; `has_tables`
      gating; 175/175; baselines untouched; PID-scoped 0 non-loopback. Carry-forwards: TABLEFORMER_REVISION
      code-enforce (a); KB prune (c). Step-0 landed (T-CLAUSE regression test + 2 commits)._ Original scope:
      **Step-0 (close T-CLAUSE gaps, D-52):** add the doc_id post-filter regression test;
      commit the T-CLAUSE feature + the pending governance/docs edits (coherent history). **Then** the
      tables feature: TableFormer extraction (model fetch owner-approved, offline after, pin revision) →
      markdown-per-table chunks w/ page(+bbox) → chunk/embed/index into a KB/scratch store → table-chunk
      verbatim-span semantics preserving D-19/D-38 never-false-accept → answer a table-value question
      span-verified → UI surfacing. **Offset-routing (D-51):** heavy Docling path for tabular/scanned docs
      ONLY; never mix PyMuPDF/Docling offsets on one chunk. Test-first; baseline `.lancedb`/M2-8
      byte-identical; loopback-only + PID-scoped real egress samples (D-47/D-52).
      `extract_tables(pdf)` → per-table `{source_filename, page_number, bbox, markdown}` via Docling
      `do_table_structure=True` (TableFormer, **one-time model fetch owner-approved**, offline after;
      pin model revision). Markdown-table-per-table (D-50). Synthetic table-bearing doc authored
      (fee-schedule/exhibit). **Test-first:** known cells land in the markdown on the correct page,
      page-unique; born-digital text path **byte-identical** (tables not double-counted); baseline
      `.lancedb`/M2-8 **untouched** (no re-embed/re-eval); zero non-loopback egress (socket-guard + live
      `lsof`). Extraction only — NOT yet chunked/embedded/retrievable.
- [x] **T-CLAUSE — Clause-extraction feature END-TO-END (#3, D-49/D-51, D-52).** _🟢 DONE 2026-06-21,
      Tester-confirmed GREEN ×6 + Planner-verified (dirty tree confirmed). All 5 layers complete, no stubs;
      never-false-accept held on every path incl. wrong-file doc_id post-filter; 159/159 suite; baseline
      byte-identical; 0 non-loopback (PID-scoped). **2 yellows → T-TBL step-0:** add doc_id post-filter
      regression test; commit the untracked files. KB matter slug = `pemberton-demo`._ Original scope:
      (a) CUAD-informed clause taxonomy (tracked data, our own questions, provenance noted); (b)
      `pipeline/clauses.py` `extract_clauses(matter, doc_id?)` driving the existing `answer()`+verifier per
      clause — "found" ONLY with a span-verified citation (D-19/D-38), refused → advisory "potentially
      missing" (non-citable, separated), prose-but-rejected → not-confirmed (never false-accept); (c)
      loopback API route exposing it (no action routes); (d) a **Contract Review** panel in the SAM-style
      UI reusing the existing cited-span highlight + page-thumbnail + escape-before-render assets (product
      boundary: locate/summarize only, no advice/drafting/actions); (e) tests at every layer (unit + API +
      UI). **No new install; pure data + orchestration + UI.** Test-first; baseline `.lancedb`/M2-8
      byte-identical (read-only); loopback-only + **real** egress samples (D-47).
- [x] **T-GRID + B1–B6 + C1/C2 + D1 — M-ENRICH backlog (#2 + small wins, D-54/D-55).** _🟢 DONE 2026-06-21,
      Tester GREEN 240/240 + Planner closeouts + committed (`38d12ae` feat, `484e08a` gov)._ Grid =
      `POST /grid` SSE doc×question matrix, bounded concurrency, reuses `clauses._classify`; B-series small
      wins; **C1 proved the F-026 fix** (top-k×N+rerank None→rank3, **owner decision to adopt** — baseline-
      affecting); C2 sentence-window deferred; D1 form-robustness on PyMuPDF (no new dep). Closeouts:
      canonical `scripts/baseline_hash.sh` + re-pinned audit canon; A0 import-time air-gap fix; leftover dir
      removed. `eyecite` held `[GATE]`. Never-false-accept across grid/stream/fuzzy; baselines byte-identical.
- [ ] **T-TRANS (separate track) — Transcripts page:line + Q/A chunking.** Net-new, **brainstorm-first**
      (page:line ripples into verifier + UI). Skeletons: RAGFlow `qa.py`, Docling `PageChunker`, PyMuPDF
      per-line y-coords. Not bundled with the tables arc.
- _**Small wins (fold into whatever we touch next, D-49/D-51):** `eyecite` case/statute-citation
  extraction (retrieve-by-authority); kotaemon **logprob** answer-confidence (prefer over LLM-grader);
  sentence-window retrieval; top-k×N-before-rerank recall fix (**hypothesis** for F-026 — measure);
  **non-gating** fuzzy span-verify fallback (UI "probable/unverified" only, never enters verified set);
  streaming-token SSE UX (perceived latency); Docling `OcrMac` / `-MPS` (Apple-Silicon OCR/ingestion
  speedups). Real-PDF robustness (bankruptcy-parser line-geometry / font-band / checkbox-glyph + real
  court PDF fixtures) folds into the M6-readiness track._

## Future / parked work (not scheduled — owner will trigger)

- [ ] **⏸️ Transcripts — page:line Cited Q&A (DESIGN DONE, build HELD IN RESERVE, D-56).** Full design at
      `docs/superpowers/specs/2026-06-21-transcripts-design.md`. Depositions already work as normal
      Document-Hub uploads (verified, **page-level** cites). This adds court-grade **page:line** precision.
      **Trigger:** a real deposition shows page-level isn't precise enough (attorney is deposition-heavy).
      Cheap interim option meanwhile: strip the line-number gutter so it doesn't pollute retrieval.
- [ ] **⏸️ Agent personality for attorney-facing communication (PARKED, D-56).** Give the assistant a warmer/
      more human voice when talking to the attorney. **Not now — low priority.** ⚠️ Design constraint when
      picked up: personality must NOT erode the product boundary (CLAUDE.md — not an AI lawyer, no advice,
      locate/summarize only) or the conservative/grounded/verifiable tone, and must avoid AI-slop framing
      (`[[feedback-no-ai-built-this]]`). Tone only; never changes what the system asserts or cites.

## Constraints (carry-forward from M1)

- Local-only, **loopback-only**; no cloud; **synthetic/public docs only**, no real data (real data is M6).
- New installs/deps are **owner-gated, one step at a time**. System Ollama `127.0.0.1:11434` (not the
  bundled engine). **D-11 digests pinned** (`qwen3:14b=bdbd181c33f2`, `bge-m3=790764642607`); a change
  forces re-index.
- Document bodies stay **git-ignored** (D-28); never commit secrets/API keys; never bind `0.0.0.0`.

## Risks / carry-forward

- **🟡 Real-PDF section detection (M6 robustness gap, surfaced at M2-2).** Section metadata currently
  leans on the synthetic corpus's `#`/`##` markdown headings; **real attorney PDFs won't have them.**
  Docling's `section_header` detection is the intended real-PDF path but is presently the fallback
  (offline default uses cached/marker headings). **Before real data (M6), validate section detection
  on heading-less, real-style PDFs** or section metadata may degrade. Not an M2-synthetic blocker.
- **🟡 Span normalization (folded into M2-6).** `verbatim_span` ≠ raw PDF text byte-for-byte (reflow);
  the D-19 overlap check must normalize. See M2-6.
- **🟡 F-026 retrieval-recall gap (M2-8 finding).** A present fact (counsel named in the page-1
  caption) was **falsely refused** because retrieval surfaced only its page-3 occurrence. **Not** a
  safety issue (no hallucination) and **not** a verifier bug — a **recall** gap. Revisit via `top_k` /
  reranker / chunking tuning; tracked, not an M2-8a blocker. Do not force-pass it.
- **🟡 `answering._norm` ≠ verifier normalization contract (M2-8a Tester finding).** M2-8a aligned the
  **verifier** (`verify_answer` / `_norm_map`) to the `html.unescape` + backslash-strip contract, but
  `answering._extract_and_resolve`'s local `_norm` does **not** yet decode entities / strip backslash
  escapes. Didn't bite in M2-8 (qwen3 emitted a `chunk:` tag → resolved by id), but a tag-less escaped
  span from a looser future output could **false-reject**. **Precision only — never a false-accept.**
  Consider aligning `answering._norm` with the verifier's normalization contract when a future task
  touches that path. (M2-7 left the answering path untouched — deferred, still open.)
- **🟢 Optional API hardening (M2-7 Tester note (c)).** `docs_url`/`redoc_url` are already `None`, but
  `openapi_url` is default so `GET /openapi.json` serves the schema (no document data; loopback
  single-tenant → low risk). Consider `openapi_url=None` as defense-in-depth if/when the API path is
  revisited. Not a blocker.
- **🟠 Compose-only deploy boundary (M2-9 / D-43a).** The image is loopback-safe **only** via
  `docker compose` (publishes `127.0.0.1:8000:8000`); a bare `docker run -p 8000:8000` would publish to
  `0.0.0.0` and expose the service off-host (**hard rule #4**). Mitigation today = documentation +
  compose discipline (a clean in-container guard isn't feasible). Optional follow-up: a short deploy
  `README`/warning making compose-only explicit. **Never `docker run -p` this image.**
- **🟢 Image leanness (M2-9 Tester note (d)).** The image COPYs all `pipeline/*.py` (incl.
  ingestion/run-harness **source** — code only, no data) though only the serving modules run. Optional:
  COPY only the serving modules. Cosmetic; not a blocker.
- **🟡 Linux/CUDA portability (M2-9 / D-43b).** `host.docker.internal:host-gateway` is a Docker-Desktop
  convenience; a native-Linux deploy must **re-prove** container→host-Ollama reachability **and** egress
  (D-31) before use. Relevant only if a future M4-5 hardware path (D-22) is Linux/CUDA rather than the
  recommended Mac Studio.
- **🟢 OCR: synthetic-raster ≠ real-scan (G-SC2 Tester note).** OCR validated on clean 300-DPI synthetic
  renders (no skew/noise, 93–95% conf), **not real scans** — re-validate accuracy on real scanned docs
  at **M6** (owner-gated, written approval).
- **🟢 OCR routing edge cases — FIXED (G-OCR-ROBUST, D-47).** The `_MIN_TEXT_LAYER_CHARS` sparse-page
  misroute and the mixed text+image page are now handled (sparse-digital stays PyMuPDF; mixed →
  `source=="mixed"` with embedded text OCR'd). Real-scan validation still M6.
- **🟠 `<3s` first-token latency NOT met (G-LAT, D-47).** Independent median ~3.6s on the M4 Pro;
  instrumented honestly. Likely a production-hardware (D-22) / model-choice lever, but that is a
  **hypothesis** — validate on real hardware before claiming it. Lone open §2/M3 quantitative target.
- **🟡 Egress-log discipline (process, G-LAT/D-47).** The t2–t7 egress logs were first committed **empty**
  then remediated. **Every network-bearing run must write real `lsof`/`nettop` samples**, not a header —
  a header is not proof. Verify log line-counts when recording any future run.
- **🟡 Uncommitted prior-milestone code (git hygiene).** M2-7 (`api.py`), M2-9 (`Dockerfile`/
  `docker-compose.yml`), and the SC-5 UI (`static/`, `test_api_ui.py`) are **untracked** in the working
  tree (the gap-closure batch committed on top of them). Land them in a commit so history is coherent and
  the deploy task's dependencies are tracked.
