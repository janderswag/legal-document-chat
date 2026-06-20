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
- [ ] **M2-7 — FastAPI HTTP surface** (D-13), loopback-only.
- [x] **M2-8 — Full-72 page+span golden re-run (the headline M2 proof, D-39).** _Done 2026-06-20 =
      **CONDITIONAL PASS** (capability proven; 3/4 gates clean). Egress-monitored (D-31); raw →
      git-ignored `eval/results/run-2026-06-20-m2.jsonl`. **Displayed fabrications 0** (hard-zero holds —
      the verifier fails **conservatively**, the safe direction), **NF refusal 9/9**, **DRM 2/2** (no
      cross-matter, both verified). **Page+span 93.7% strict** (under the ≥95% gate) solely from
      **verifier false-rejects of truthful, correctly-grounded answers** whose spans use escapes the
      normalization didn't cover: **F-014** backslash `\"…\"`, **F-016** HTML entity `&quot;…&quot;`.
      Both flip to PASS under `html.unescape` + backslash-strip → **≥96.8%**. FINAL PASS pending M2-8a._
- [ ] **M2-8a — Normalization fix + targeted re-run → FINAL PASS.** Extend the M2-6 verifier
      normalization to **decode HTML entities (`html.unescape`) + strip backslash-escaped quotes** (on
      top of collapse-ws / `-\n`→`-`) — confirmed to resolve F-014 (`\"`) and F-016 (`&quot;`). Apply the
      Reviewer's **F-042 alternate-page** scoring clarification into TEST_PLAN §6. Then a **targeted
      re-run** of the affected facts (F-014, F-016, F-042 + any other entity/backslash false-rejects
      across the 72) to flip CONDITIONAL → **FINAL PASS ≥95%**. The verifier must still **fail
      conservatively** (never false-accept a fabrication). **⛔ F-026 is a GENUINE miss — EXCLUDE it
      from the fix:** retrieval surfaced only the page-3 counsel occurrence (not the page-1 caption) →
      the model **falsely refused a present fact** (a recall gap, not a verifier issue). Do **NOT**
      weaken the verifier or force-pass it. Expected FINAL ≈ **62/63 (≥95%)** with F-026 the lone real
      miss; revisit F-026 later (top_k / reranker / chunking — see Risks). **[NEXT]**
- [ ] **M2-9 — Docker Compose deployment** (D-20) — later.

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
