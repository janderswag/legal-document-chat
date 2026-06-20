# BUILDER_STATE.md — Builder handoff (pre-context-clear)

_Regenerated 2026-06-20 at the **M2-8a boundary**. Snapshot of the Builder tab's state in the
Planner→Builder→Reviewer→Tester relay. Read alongside **`RELAY.md`** (loop operating manual) and the
canonical files it lists: `CLAUDE.md`, `RUN_STATE.md` (source of truth + "Next task"), `TASKS_M2.md`,
`DECISIONS.md` (D-1…D-39), `eval/TEST_PLAN.md` (§3/§4 = M1 filename bar D-29; §6 = M2 page+span bar D-39)._

## 1. Current task

**M2-8 is COMPLETE — recorded as a CONDITIONAL PASS.** The Builder ran all 72 golden questions
through the M2 pipeline (`retrieve → answer → verify_answer`, `rerank=False`) under a continuous
egress monitor and graded manually at the page+span bar (TEST_PLAN §6 / D-39). No task is mid-edit;
the Builder is **idle at a clean between-task boundary**, awaiting the relay.

**Next task = M2-8a (queued, NOT started):** a small verifier-normalization fix to convert the
conditional pass into a FINAL page+span PASS (≥95%):
- `html.unescape` the model's cited span before the overlap check (recovers **F-016**, whose span
  carried `&quot;` HTML entities),
- strip stray backslash-escapes from the span (recovers **F-014**, `\"Landlord\"`),
- credit **F-042** as a valid alternate-page citation (the judge is named verbatim on the cited page 2
  as well as the manifest's page 1 — a multi-page fact, not a fabrication).
Then **M2-7** (FastAPI loopback HTTP surface, D-13), after which the M2 milestone wraps.

## 2. Decisions made (and why)

Recorded in `DECISIONS.md`; the M2 build/scoring calls, summarized:

- **D-34 — Vector store = LanceDB (embedded, pip-only).** No Docker/server; chosen over Qdrant for the
  single-tenant M2 build. Store is git-ignored (contains document text).
- **D-35 — Matter-scoping = explicit `matter` param + hard pre-filter BEFORE similarity.** Never infer
  the matter from the question (inference is the exact DRM failure). Absent matter = explicit search-all.
- **D-36 — Reranker (`bge-reranker-v2-m3`) runs LOCAL in-process (transformers+Torch), NOT Ollama**
  (Ollama can't serve cross-encoders). Measured **neutral lift** on this 6-doc corpus → **OFF by
  default** (`rerank=False`); kept behind a flag for production scale.
- **D-37 — Answering is hand-rolled; LlamaIndex dropped.** A thin retrieve→assemble→qwen3→parse
  function, for full transparency of the claim→chunk→offset citation path M2-6 needs.
- **D-38 — Displayed citations are CHUNK-DERIVED, never model-asserted.** Filename+page come from the
  matched chunk's metadata; the model's prose is only a pointer. (Fixed the M2-5 `_parse_citations`
  bug; precondition of M2-6.)
- **D-39 — M2-8 scores at the stricter page+span bar** (re-instating CE_PLAN §2/§11 that D-29 relaxed
  for the turnkey stack): present-fact citation = conveys fact AND chunk-derived `filename_match` AND
  `page_match` AND the span **mechanically verifies** (survives `verify_answer`). **Displayed
  fabrications = hard-zero.**
- **Normalization contract (M2-1/M2-2/M2-6):** collapse whitespace, `-\n`→`-` (keep the hyphen), drop
  quote chars, lowercase — applied to BOTH span and chunk text so PDF reflow never false-rejects.
  (M2-8a extends this with `html.unescape` + backslash-strip.)
- **D-31 — Air-gap = egress-MONITORED, not disconnected** (networking on; `lsof`/`nettop` prove zero
  non-loopback). **D-28 — document bodies + derived stores (`pipeline/.lancedb/`, chunks,
  `eval/results/`) are git-ignored**, never committed.

## 3. In-flight work

**None half-finished.** Confirmed at this regen: `pipeline/verifier.py` has **no** `html.unescape`
(M2-8a not started); the deterministic verifier + chunk-derived tests pass (6/6, no LLM); the full
suite was 37/37 at M2-6. The M2-8 run + grading artifacts are written. The only open items are relay
hand-offs (Reviewer audit of the M2-8 grading → Tester repro → Planner records final), not Builder code.

## 4. Next 3 steps (immediately after resume)

1. **Await the Reviewer's audit** of the M2-8 grading (sample of present-fact `citation_accurate_M2`,
   all 9 NF, the 0-displayed-fabrications claim, F-042/F-016 rulings) and the Tester's independent
   ~10-question repro.
2. **Execute M2-8a** when the Planner gates it: add `html.unescape` + backslash-strip to the verifier's
   span normalization (test-first: F-016/F-014-style synthetic spans must verify; the fabricated/
   mis-paged true-negatives must STILL be rejected — the verifier must never false-accept), credit
   F-042, re-run the 72-question set, confirm ≥95% page+span + still 0 displayed fabrications.
3. **Then M2-7** (FastAPI loopback-only HTTP surface, D-13) — owner-gated install (FastAPI/uvicorn).

## 5. Key constraints (must be respected — see `RELAY.md` "Standing constraints")

- **Local-only, loopback-only.** System Ollama `127.0.0.1:11434` (NOT AnythingLLM's bundled engine);
  never bind `0.0.0.0`; never set `OLLAMA_HOST`.
- **Synthetic/public docs only. No real attorney/client data** (real data = M6, onsite, written approval).
- **Installs are owner-gated, one step at a time** via the relay prompt. Current venv deps (pinned):
  `pymupdf==1.27.2.3`, `docling==2.104.0`, `lancedb==0.33.0` (+ transformers/Torch from docling). HF
  models (Docling layout, `bge-reranker-v2-m3`) live in `~/.cache/huggingface`, fetched once then OFFLINE.
- **D-11 pins:** `qwen3:14b=bdbd181c33f2`, `bge-m3=790764642607`, reranker
  `RERANKER_REVISION=953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e`. A change forces re-index/re-eval.
  **Reranker OFF by default** (D-36).
- **Verifier fails CONSERVATIVELY** — a false-reject of a truthful span is a precision bug; it must
  **never false-accept a fabrication**. Any M2-8a normalization loosening must preserve this.
- **Manual eval grading only** — no auto-scorer (TEST_PLAN §3/§5). Objective citation lookups are
  reading aids, not a pass/fail emitter.
- **Air-gap = egress-monitored** (D-31). **Git-ignored (D-28):** `documents/`, `pipeline/.lancedb/`,
  chunk data, `eval/results/`; never commit a body or secret.

## 6. File map

**Tracked governance/eval (committable):**
- `RELAY.md` — 4-tab loop operating manual (read first after any clear).
- `CLAUDE.md`, `CE_PLAN.md`, `README.md` — governance + plan (milestone now 2-3).
- `RUN_STATE.md` — source of truth: status + **"Next task" = M2-8a** + completed log + carry-forward.
- `TASKS_M2.md` — M2 checklist (M2-1…M2-6, M2-8 done; M2-8a/M2-7 next). `TASKS.md` = M1 (historical, PASSED).
- `DECISIONS.md` — locked decisions **D-1…D-39**.
- `eval/TEST_PLAN.md` — rubric (§3/§4 M1 filename bar; **§6 M2 page+span bar**).
- `eval/golden_manifest.jsonl` (72: 63 present + 9 NF; DRM pair F-009/F-025), `eval/golden_questions.jsonl`.
- `PLANNER_STATE.md`, `BUILDER_STATE.md` (this file).

**Pipeline code (`pipeline/`, committable — code/tests only, no bodies):**
- `ingestion.py` (M2-1 PyMuPDF per-page text + 1-based pages) · `chunking.py` (M2-2 Docling structure +
  page/section-aware chunks + deterministic SAC) · `embed_store.py` (M2-3 bge-m3 1024-d → LanceDB) ·
  `retrieval.py` (M2-4 matter pre-filter-before-similarity; `rerank` flag) · `reranker.py` (M2-4b local
  cross-encoder, OFF by default) · `answering.py` (M2-5 §10 grounded answer + D-38 chunk-derived
  resolution) · `verifier.py` (M2-6 mechanical span overlap + reject; **M2-8a edits land here**) ·
  `run_m28.py` (M2-8 run harness — loop, not a scorer) · `tests/test_*.py` (per stage; TDD) ·
  `requirements.txt`, `README.md`, `.gitignore`.

**Git-ignored artifacts (NEVER committed, D-28):**
- `pipeline/.venv/`, `pipeline/.lancedb/` (vectors+text), `documents/synthetic_corpus/{pdf,chunks}/`
  (bodies + chunk data + Docling header cache).
- `eval/results/run-2026-06-20-m2.jsonl` (72 raw M2 results), `egress-2026-06-20-m2.log` (16,148
  samples, 0 non-loopback), `grades-2026-06-20-m2.md` (manual grading record).

## 7. Blockers / flags (to escalate to Reviewer / Tester / owner)

- **🟢 M2-8 keystone PROVEN:** M1 produced ZERO verifiable page+span citations; M2 produced **59/63
  fully chunk-derived, span-verified page+span citations**, **0 displayed fabrications**, **NF 9/9 =
  100%**, **DRM 2/2 = 100%**, latency mean 6.9s/median 7.0s/max 17.5s, 2 rejected_claims (safety
  working). Egress: zero non-loopback over 16,148 samples (SC-6).
- **🟡 Page+span accuracy = 93.7% strict (< 95% gate) → CONDITIONAL pass.** Four non-fabrication misses:
  - **F-016** — model emitted `&quot;` HTML entities in its span → no overlap → rejected. **Fixable**
    via `html.unescape` (M2-8a).
  - **F-014** — model span had backslash-escaped/non-contiguous quotes (`\"Landlord\"`) → rejected.
    Targeted by M2-8a backslash-strip.
  - **F-042** — judge named on BOTH manifest page 1 AND the cited page 2; chunk-derived page 2 ≠ 1 →
    strict `page_match` miss, but a **truthful verified** citation (multi-page fact). M2-8a credits it.
  - **F-026** — GENUINE miss: retrieval surfaced only the page-3 occurrence of counsel (not the page-1
    caption) and the model falsely refused. **Not** fixed by M2-8a; revisit via reranker/top_k or a
    chunking tweak later, not a blocker for the page+span PASS.
  After M2-8a: expected **≥96.8%** (≥95% gate) with 0 displayed fabrications retained.
- **🟡 Conservative-verifier invariant (for the Reviewer of M2-8a):** the html.unescape/backslash-strip
  loosening must recover F-014/F-016 WITHOUT enabling any false-accept — the fabricated + mis-paged
  true-negative tests must stay red→rejected.
- **🟡 Reranker neutral lift** on the 6-doc corpus (D-36) — stays OFF; re-evaluate at production scale.
- **🟡 Latency** (informational): mean ~6.9s/question (no §6 gate); instrument first-token before the M4 demo.
