# BUILDER_STATE.md — Builder handoff (pre-context-clear)

_Generated 2026-06-20. Snapshot of the Builder tab's state in the Planner→Builder→Reviewer→Tester
relay. Read alongside `RUN_STATE.md` (source of truth), `TASKS.md`, `DECISIONS.md`, `eval/TEST_PLAN.md`._

## 1. Current task

**M1-10 is COMPLETE.** No task is mid-edit. The Builder just finished running all 72 golden questions
through the `m1-golden` AnythingLLM workspace, captured raw output, manually graded per D-29/D-30, and
recorded a **recommended M1-13 PASS** (all four §4 gates met). The Builder is now **idle, awaiting the
relay**: Reviewer audit → Tester repro → Planner records M1-13 with owner.

No code is being written (M1 is turnkey AnythingLLM + Ollama; no application/pipeline code exists yet —
that's M2-3, gated on M1 passing).

## 2. Decisions made (and why)

These are recorded in `DECISIONS.md`; summarized here with rationale:

- **D-29 — M1 citation scored at FILENAME level, not page level.** Empirically (M1-7c) AnythingLLM
  1.14.1's desktop PDF parser flattens all pages into one `pageContent` blob and emits **empty chunk
  metadata (no page field)**, so verifiable page-level citation is mechanically impossible on the
  turnkey stack. M1 scores answer-correctness + filename grounding + DRM right-matter + refusal.
  Verifiable **page+span** citation is reassigned to **M2-3** (Docling + mechanical span check, D-19).
- **D-30 — Not-found refusal scored on substance, not exact wording.** Passes when the system declines
  + asserts no citation; the exact "I could not find this in the documents." sentence is pinned as the
  product string and tracked separately as `refusal_wording_exact` (informational UX flag).
- **D-31 — Air-gap is egress-MONITORED, not physical disconnect.** The AI-driven run needs the network;
  corpus is synthetic. Prove SC-6 by monitoring (lsof/nettop) for zero non-loopback, not by unplugging.
- **Run via the v1 API, never `stream-chat`.** This AnythingLLM 1.14.1 build routes HTTP `stream-chat`
  into **agent mode** (tools/web) — which would violate the no-action/no-egress boundary (CE_PLAN §3
  #12). The stable, grounded path is `POST /api/v1/workspace/{slug}/chat` with `mode:"query"`.
- **`update-env` requires STRING values.** The endpoint's validator calls `.includes` on values and
  500s on numbers. Always send config values as strings (e.g. `"OllamaLLMTokenLimit":"32768"`).
- **Corpus rendered to page-faithful PDFs** (M1-7c) via no-install headless Google Chrome
  `--print-to-pdf`, one physical page per `===== PAGE N =====` marker. (Kept even though the parser
  drops page metadata — preserves the page-faithful artifact for the M2-3 build.)
- **D-28 — synthetic document bodies live ONLY under git-ignored `documents/`; only metadata under
  tracked `eval/`.** Never commit a document body.

## 3. In-flight work

**None half-finished.** M1-10 ran to completion (72/72, 0 errors). All result artifacts written. Doc
updates (RUN_STATE/TASKS) applied. The only "open" items are relay hand-offs (audit/repro/decision),
not Builder work.

## 4. Next 3 steps (immediately after resume)

The Builder's own queue is empty pending the relay; if resumed as Builder these are the next actions:
1. **Wait for Reviewer's audit** of `eval/results/grades-2026-06-20-qwen3-14b.md`. The one definitional
   call to confirm: filename_match via the **returned `sources[]`** citation (Builder's reading) vs
   requiring the filename **asserted in the answer text**. If the Reviewer rules "asserted-in-answer
   only," re-grade the ~15 present facts that cited "the document"/"Context 0" without naming the `.pdf`.
2. **Support the Tester's ~10-question repro** (fresh sessionId, v1 query chat, query mode) and the
   egress re-snapshot; reconcile any nondeterminism (qwen3 thinking can vary phrasing, not the cited file).
3. **Hand the confirmed numbers to the Planner** to record the **M1-13 go/no-go** with the owner, plus
   the **M2-3 build decision** (page+span citation) and the **latency-tuning** note before any M4 demo.

(If the owner says PASS: M2 begins — custom FastAPI + LlamaIndex + Docling pipeline. Do NOT start it
until M1-13 is recorded and the owner approves.)

## 5. Key constraints (must be respected)

- **Milestone 1 ONLY.** Do not scaffold the M2-3 custom pipeline (FastAPI/LlamaIndex/Qdrant/Docling/
  reranker/mechanical span check) until M1 passes and the owner approves.
- **Installs/model-pulls/config changes are owner-gated, one step at a time.** Each prior step (M1-1..
  M1-5, M1-7c, M1-7b) was approved via its relay prompt. Do not install/pull/reconfigure without the
  task calling for it.
- **No auto-scorer.** A script that computes pass/fail is approval-gated tooling (TEST_PLAN §3). Posing
  questions via repeated API calls is fine; **grading is manual** (read each answer vs the manifest).
- **Local-only, loopback-only.** AnythingLLM `:3001`/`:8888` + system Ollama `:11434`, all `127.0.0.1`.
  Never bind `0.0.0.0`; never set `OLLAMA_HOST`. Keep `DISABLE_TELEMETRY='true'`.
- **Target the SYSTEM Ollama (`127.0.0.1:11434`), NOT AnythingLLM's bundled `llm`** (ephemeral loopback
  port, was `:64562`).
- **D-11 digests pinned:** `qwen3:14b=bdbd181c33f2`, `bge-m3=790764642607`. A digest/embedding change
  forces a full `m1-golden` re-index — re-pin before any re-embed.
- **Synthetic/public docs only. No real attorney/client data** anywhere on this machine (real data is
  Milestone 6, onsite, after written approval).
- The loopback **API key** minted for v1 calls lives in the AnythingLLM DB and `/tmp/m1key.txt`;
  **never commit the secret.**

## 6. File map

**Tracked governance/eval (committed-eligible):**
- `CLAUDE.md`, `CE_PLAN.md`, `README.md` — project governance + plan (unchanged by Builder).
- `RUN_STATE.md` — source-of-truth status; updated through M1-10 (recommended PASS recorded).
- `TASKS.md` — M1 checklist; M1-1..M1-9, M1-EH, M1-7/7c/7b, **M1-10/11/12 checked**; M1-13 = recommended
  PASS pending owner (not checked).
- `DECISIONS.md` — locked decisions incl. D-28..D-31.
- `eval/README.md` — manifest schema.
- `eval/golden_manifest.jsonl` — 72 ground-truth records (63 present + 9 NF). **Filenames are `.pdf`**
  (updated extension-only in M1-7c). DRM pair F-009/F-025.
- `eval/golden_questions.jsonl` — 72 questions keyed 1:1 by `fact_id`.
- `eval/TEST_PLAN.md` — run procedure + rubric + §4 thresholds (D-29/D-30 encoded).
- `eval/manifest.template.jsonl` — schema template.
- `BUILDER_STATE.md` — this file.

**Git-ignored run artifacts (`eval/results/`, never committed):**
- `run-2026-06-20-qwen3-14b.jsonl` — 72 raw answers + asserted citations + sources[] + latency.
- `egress-2026-06-20.log` — 74 egress snapshots (0 non-loopback).
- `grades-2026-06-20-qwen3-14b.md` — Builder's manual verdicts + the four metrics.

**Git-ignored corpus (`documents/synthetic_corpus/`, bodies never committable, D-28):**
- 6 source `.md` docs (MSA, lease, complaint, order, public-domain statutes, demand letter).
- `pdf/` — the 6 page-faithful PDFs (the live ingested corpus) + `pdf/_html/` intermediates.

**External (not in repo) — AnythingLLM state at `~/Library/Application Support/anythingllm-desktop/`:**
- `storage/.env` — `LLM_PROVIDER=ollama`, base paths `http://127.0.0.1:11434`, `OLLAMA_MODEL_PREF=
  qwen3:14b`, `EMBEDDING_*=bge-m3:latest`, `OLLAMA_MODEL_TOKEN_LIMIT=32768`,
  `EMBEDDING_MODEL_MAX_CHUNK_LENGTH=1000`, `DISABLE_TELEMETRY=true`. (Backup `.env.m1eh.bak`.)
- `storage/anythingllm.db` — workspace `m1-golden` (slug `m1-golden`, `chatMode=query`,
  `chatModel=qwen3:14b`, §10 system prompt, 1373 chars); `api_keys` has the loopback key; 6 PDFs
  embedded (16 chunks total). LanceDB at `storage/lancedb/m1-golden.lance`.

## 7. Blockers / flags (to escalate to Reviewer / Tester / owner)

- **🟡 Definitional call for the Reviewer:** filename_match scored via the returned `sources[]` citation
  (not strictly the filename asserted in the answer prose). ~15 present facts depend on this reading.
  If the Reviewer requires asserted-in-answer, re-grade those (the correct file is still the top source,
  so likely still PASS, but it's the Reviewer's ruling).
- **🟡 `sources[]` always populated, even on refusals** — NF "cites nothing" was judged on the answer's
  asserted citation (all empty), NOT the `sources` array. Reviewer must confirm this interpretation
  (else all 9 NF would false-fail).
- **🔴 Structural finding (go/no-go input, for the owner):** verifiable **page-level + mechanical span**
  citation is **impossible on the turnkey AnythingLLM stack** (parser flattens pages, empty chunk
  metadata). This is the primary justification to proceed to the **M2-3 custom build** (Docling page
  metadata + mechanical span overlap, per D-19). Not a reason to keep re-running M1.
- **🟡 Model emits confident WRONG page numbers in prose** (e.g. "page 14.1", "page 16.1") that are
  unverifiable. The UI must never present these as verified citations. Reinforces the M2-3 span-check need.
- **🟡 Latency** (informational, not an M1 §4 gate): mean ~19s, max ~78s per question (qwen3 "thinking");
  first-token (<3s CE_PLAN target) not separately instrumented (v1 is non-streaming). Recommend a
  thinking-mode / latency tuning pass before the M4 attorney demo.
- **🟡 M1-EH residual** (deferred, owner-decided): Chromium DoH/encrypted-DNS to the ISP persists at app
  launch (not telemetry, not app-controllable). Mooted for M1-10 by egress monitoring; host-level control
  (`pf`/Little Snitch) deferred to M5/M6 persistent-online hardening.
