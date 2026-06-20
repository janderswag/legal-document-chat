# RUN_STATE.md — Current project status

> Single source of truth for "where are we right now." Update this after every working session.
> Read at the start of each session alongside `CLAUDE.md`.

_Last updated: 2026-06-20_

## Status

**🎉 MILESTONE 1 COMPLETE — M1-13 = PASS (filename level); M2-3 build AUTHORIZED (owner, 2026-06-20,
D-33).** Full 72-question run done + independently reproduced, egress-monitored (0 non-loopback, SC-6,
D-31). Final metrics: **citation 63/63 = 100%** (filename, D-29/D-32), **0 fabricated**, **NF refusal
9/9 = 100%** (substance, D-30), **DRM 2/2**. The turnkey AnythingLLM+Ollama stack is validated for
grounded local RAG + filename grounding + not-found refusal; verifiable **page+span** citation is
proven impossible on it → reassigned to the now-authorized **M2-3 custom pipeline** (D-13..D-20). No
hardware purchase yet (M4-5). **Next: M2-3 planning** (custom FastAPI + LlamaIndex + Docling +
Qdrant/LanceDB + reranker + mechanical span verification) — see `BUILDER_STATE.md` §7 carry-forwards;
M2 writes application code + needs new installs, each owner-gated. ✅ RESOLVED (owner, D-29): M1-7c proved AnythingLLM 1.14.1's PDF parser flattens pages
(empty chunk metadata) → verifiable page-level citation is impossible on the turnkey stack. M1 is now
scored at **filename level** (answer-correctness + filename grounding + DRM + refusal); **verifiable
page+span citation is reassigned to M2-3** (Docling + mechanical span check, per D-19). The page-level
miss is itself a primary M1-13 go/no-go input justifying the M2-3 build — not a silent pass.**

The CE_PLAN is finalized and validated. No application code exists and none should be written until
the Milestone 1 turnkey pilot proves citation accuracy. The repo holds planning/governance docs plus
the tracked `eval/` golden manifest; synthetic source documents live only under the git-ignored
`documents/synthetic_corpus/`.

Project lives at `~/projects/legal-doc-intelligence/` (moved out of `~/Desktop/` on 2026-06-19 so no
unrelated parent `CLAUDE.md` bleeds in) and is now a git repo. The proposal-agent on the Desktop is
untouched.

## Active milestone

**Milestone 1 — Turnkey pilot, citation accuracy proven (fake docs).**
Ollama + AnythingLLM, `qwen3:14b` + `bge-m3`, sanitized corpus, 50+ golden eval questions, measure
citation accuracy + not-found refusal. This milestone is the go/no-go gate before any custom code or
hardware purchase. See `TASKS.md` for the M1 checklist.

## Completed tasks

- Read and confirmed `README.md` and `CE_PLAN.md` (17 sections) as source of truth.
- Created `CLAUDE.md` (project governance + safety rules + M1 scope).
- Created `TASKS.md` (Milestone 1 checklist only).
- Created `DECISIONS.md` (decisions locked from CE_PLAN).
- Created this `RUN_STATE.md`.
- **Governance fix (Reviewer-required):** corrected the M1-6 corpus path. Synthetic source
  documents must live under the git-ignored `documents/synthetic_corpus/` (never an unignored
  `corpus/`); only metadata/templates are tracked under `eval/`. Recorded as decision **D-28**;
  defined the M1 ground-truth manifest schema in **`eval/README.md`** with a tracked template
  `eval/manifest.template.jsonl`.
- **M1-6 — Sanitized corpus assembled.** Authored 6 synthetic documents under the git-ignored
  `documents/synthetic_corpus/` (MSA, commercial lease, complaint, summary-judgment order,
  public-domain statute excerpts, demand letter) covering all four required `document_type`s, each
  with the page-1 banner and explicit `===== PAGE N =====` markers. Built the tracked ground-truth
  manifest **`eval/golden_manifest.jsonl`**: **63 present-fact records** (each verified to appear on
  its cited file+page) + **9 not-found records**, including a **DRM pair** (identical indemnification
  clause in two different matters, F-009/F-025). A verification script confirmed all spans resolve,
  absent topics are truly absent, corpus bodies are git-ignored, and only `eval/` metadata is
  tracked.

- **M1-8 / M1-9 — Golden eval question set + test plan.** Authored `eval/golden_questions.jsonl`
  (72 questions, one per `fact_id` — 63 present + 9 not-found, validated 1:1 with the manifest) and
  the tracked `eval/TEST_PLAN.md` (run procedure, scoring rubric, thresholds, go/no-go). Added
  `eval/results/` to `.gitignore` so raw run outputs are never committed.
- **Refusal-scoring decision (owner-approved).** The not-found safety gate scores on substance
  (refuses + cites nothing); the exact CE_PLAN §10 / D-5 sentence is pinned via the M1-5 workspace
  prompt and tracked as a separate UX flag `refusal_wording_exact`, not a hard-zero fail. Encoded in
  `eval/TEST_PLAN.md` §3.2. (Promote to a DECISIONS.md entry once the prior agent's uncommitted edits
  are committed.)
- **M1-1 — Ollama installed and verified.** Installed via Homebrew (native formula, no Docker;
  Ollama 0.30.10). Server confirmed on `127.0.0.1:11434` (`/api/version` round-trip) and bound to
  **loopback only** (`lsof`/`netstat` show `127.0.0.1:11434 LISTEN`, not `0.0.0.0`); `OLLAMA_HOST`
  unset. No public exposure.
- **M1-2 — AnythingLLM installed and launched (owner-approved fresh install).** `brew install
  --cask anythingllm` 1.14.1 (native macOS app, no Docker) → `/Applications/AnythingLLM.app`.
  Launches cleanly (Electron main PID 12860 + GPU/Renderer helpers). On launch it opened **three
  listeners, all loopback-only**: `127.0.0.1:3001` (internal server), `127.0.0.1:8888` (collector),
  and a **bundled `llm serve`** at `127.0.0.1:64562` — **no `0.0.0.0/*`**. Scope held: no workspace,
  no document load, no model pulled by us, no Ollama wiring. **Note for M1-5:** AnythingLLM ships its
  own embedded Ollama/llm runtime; wiring must point at the SYSTEM Ollama (`127.0.0.1:11434`,
  `qwen3:14b`/`bge-m3`), not the bundled engine.
- **M1-3 — `qwen3:14b` pulled to the SYSTEM Ollama (owner-approved).** `ollama pull qwen3:14b` on the
  system instance (`:11434`, not the bundled `:64562` engine). `ollama list` shows `qwen3:14b`
  (digest `bdbd181c33f2`, 9.3 GB; models dir ~8.6 GB on disk). Trivial `/api/generate` returned
  exactly `ok` (`done_reason: stop`); first call 5.89s total (5.47s model load, sub-second eval) —
  warm first-token comfortably under the <3s target. Binding re-verified **loopback-only**
  (`127.0.0.1:11434`), `OLLAMA_HOST` unset. The model-registry download was the only outbound traffic.
- **M1-4 — `bge-m3` pulled to the SYSTEM Ollama (owner-approved).** `ollama pull bge-m3` on the
  system instance (`:11434`, not the bundled `:64562` engine). `ollama list` shows `bge-m3:latest`
  (digest `790764642607`, 1.2 GB; models dir ~9.7 GB on disk with both models). `/api/embed`
  round-trip returned a genuine **1024-dim numeric vector** (not chat text) — confirms it works as an
  embedding model. Binding re-verified **loopback-only**, `OLLAMA_HOST` unset. Registry download was
  the only outbound traffic.

- **M1-EH (app-level) — AnythingLLM telemetry disabled + egress characterized.** Set
  `DISABLE_TELEMETRY='true'` in AnythingLLM's own `storage/.env` (backup `.env.m1eh.bak`); did not
  touch the bundled-engine wiring. Restart **log-confirmed** `[TELEMETRY DISABLED] … no events will
  send` (before: `[TELEMETRY SENT]` server_boot/onboarding/workspace_created, leaking config
  metadata to Mintplex over Cloudflare — now stopped). Measured before/after launch egress: the
  data-bearing **anonymous-telemetry HTTPS (Cloudflare)** is gone, but a **residual at launch
  remains — Chromium DoH/encrypted DNS to the ISP** (`doh-01/02.spectrum.com`, Charter), which **no
  AnythingLLM setting controls**. No document-bearing egress (no docs loaded); system Ollama
  (`:11434`) zero outbound; loopback listeners (`:3001/:8888` + bundled `llm` on an ephemeral
  loopback port) intact. **Zero app-outbound was NOT achieved by app-level alone.**
- **M1-5 — AnythingLLM wired to the SYSTEM Ollama (owner-approved).** Via the unauthenticated
  loopback API `POST /api/system/update-env` set `LLM_PROVIDER='ollama'`,
  `OLLAMA_BASE_PATH='http://127.0.0.1:11434'`, `OLLAMA_MODEL_PREF='qwen3:14b'`
  (digest `bdbd181c33f2`), `EMBEDDING_ENGINE='ollama'`,
  `EMBEDDING_BASE_PATH='http://127.0.0.1:11434'`, `EMBEDDING_MODEL_PREF='bge-m3:latest'`
  (digest `790764642607`) — **system instance, not the bundled `:64562` engine**;
  `DISABLE_TELEMETRY='true'` preserved. Created the **`m1-golden`** workspace (chatProvider `ollama`,
  chatModel `qwen3:14b`) with the CE_PLAN §10 grounded-citation system prompt (refusal sentence
  pinned per TEST_PLAN §3.2). Round-trip via `/api/v1/workspace/m1-golden/chat` returned a coherent
  `qwen3:14b` reply and `/api/ps` on `:11434` then showed `qwen3:14b` loaded → proves the system
  instance served it. Listeners all loopback (`:11434`, `:3001`, `:8888`); telemetry still disabled.
  _Notes: (a) this AnythingLLM 1.14.1 build's HTTP `stream-chat` route swaps into agent mode, so the
  stable round-trip/eval path is the **v1 API** (`/api/v1/workspace/{slug}/chat`); a loopback-only
  API key was minted in the app DB for this (secret NOT committed). (b) `qwen3:14b` is a thinking
  model — replies include `<think>…</think>`; strip/handle at M1-10. (c) harmless stale
  `ANYTHINGLLM_MODEL_PREF='qwen3-vl:4b-instruct'` remains in `.env`, unused now that provider=ollama._
- **M1-7 — Synthetic corpus embedded into `m1-golden` (owner-approved).** D-11 digests re-verified
  before embedding. Uploaded all 6 docs from `documents/synthetic_corpus/` via the v1 API (original
  filenames preserved) and embedded via **`bge-m3` on `:11434`** (`/api/ps` showed `bge-m3:latest`
  load during the embed; before: empty). **6/6 embedded, error: None**; LanceDB namespace
  `m1-golden.lance` created; loopback-only; telemetry still disabled. **Per-doc chunk count = 1
  each (total 6)** — docs are small (317–809 tok) and the M1-5 `EMBEDDING_MODEL_MAX_CHUNK_LENGTH=8192`
  makes each whole doc one chunk. **Risk:** with 1 whole-doc chunk and Markdown having no real pages
  (the `===== PAGE N =====` markers are inline text), AnythingLLM cannot emit page-level citations as
  configured → likely fails M1-11 `page_match`. **For M1-7b:** lower chunk size and/or revisit the
  deferred PDF-render path before M1-10.
- **M1-7c — Page-faithful PDF re-ingest (owner-approved; KEEP page-level).** Rendered all 6 docs to
  paged PDFs (no-install headless Google Chrome `--print-to-pdf`, one physical page per
  `===== PAGE N =====` marker) under git-ignored `documents/synthetic_corpus/pdf/`. Fidelity: PDF
  page counts == manifest max page (3/3/3/2/2/2); **63/63 present-fact spans on the correct page** (62
  exact via PDFKit + 1 confirmed `twenty-four` hyphen-wrap artifact). Manifest filenames updated
  `.md`→`.pdf` (**extension-only**, 63 records, proven identical after stripping extension). Replaced
  the Markdown in `m1-golden`, lowered chunk size (`EMBEDDING_MODEL_MAX_CHUNK_LENGTH='1000'`),
  re-embedded the 6 PDFs via `bge-m3` on `:11434`: **6/6 clean, chunks 6→16**; loopback-only;
  telemetry disabled; no corpus bodies tracked. **🚩 Blocking finding:** AnythingLLM 1.14.1's desktop
  PDF parser **flattens pages into one `pageContent` blob; chunk metadata is empty (no page field)**,
  so chunks carry no page number — page-faithful PDFs alone do **not** make the turnkey stack emit
  page citations. M1-7b's live probe is decisive; feeds M1-13 go/no-go.
- **M1-7b — Query mode + 32K context + validity probe (owner-approved).** Persisted **query mode**
  on `m1-golden` (DB `chatMode='query'`); raised context to **32768**, **verified effective** via
  `/api/ps` (`qwen3:14b context_length=32768`, no OOM); §10 grounded/refusal prompt active. Probe via
  v1 query chat (`<think>` stripped, sessionId per Q): F-001 → "March 14, 2024" + citation
  `nimbus_pemberton_msa.pdf` (matches manifest); F-004 → "$47,350" + same file (matches);
  NF-001/002/003 → exact **"I could not find this in the documents."** (refused, no substantive
  claim). **Query mode FIXES the M1-5 "Blue." world-knowledge leak.** Loopback-only; telemetry off.
  **🚩 M1-10 scoring note:** query mode **always** returns a `sources` array (retrieved chunks) even
  on refusal — §3.2 "cites nothing" must be judged on the **answer's asserted** citations, not the
  `sources` array, else every NF false-fails. Present-fact answers self-assert a page in prose but
  page is unverifiable (D-29) → score **filename only**.
- **M1-10/11/12 — Full golden run + measurement (owner-approved).** Posed all **72** questions via v1
  query chat (fresh sessionId/Q, single-turn, `<think>` stripped); 72/72 captured, 0 errors →
  git-ignored `eval/results/run-2026-06-20-qwen3-14b.jsonl`. **Egress-monitored (D-31, networking ON):
  74 snapshots, 0 non-loopback, max established=2 (loopback only)** → SC-6 met
  (`egress-2026-06-20.log`). **Manual grading** (no auto-scorer; read each answer vs the manifest,
  per D-29/D-30 → `grades-2026-06-20-qwen3-14b.md`): **citation accuracy 63/63 = 100%** (≥95%),
  **fabricated filenames 0**, **NF refusal 9/9 = 100%** (exact D-30 sentence; no asserted citation),
  **DRM 2/2 = 100%** (F-009→Pemberton MSA, F-025→Castellano lease; no cross-matter). Perf
  (informational): mean 19.2s, max 77.9s total/Q (thinking model; first-token not separately
  instrumented), no OOM at 32K. **All four §4 gates met → Builder RECOMMENDS M1-13 PASS.**

_Synthetic/public-domain content only; no application/pipeline code, no PDFs, no real documents.
Install + wiring chain (M1-1…M1-5) complete and verified loopback-only; M1-EH app-level telemetry
disable done; M1-10 air-gap is **egress-monitored** (D-31), not physical disconnect._

## Next task

**M2-8a — Normalization fix + targeted re-run → FINAL PASS.** Milestone 2-3 underway (`TASKS_M2.md`).
**M2-8 = CONDITIONAL PASS (capability proven):** full-72 page+span run, egress-monitored (D-31) →
**0 displayed fabrications** (hard-zero holds; verifier fails **conservatively**), **NF 9/9**, **DRM
2/2**; **page+span 93.7% strict**, under the ≥95% gate **only** from verifier **false-rejects of
truthful** answers using uncovered escapes (**F-014** `\"`, **F-016** `&quot;`). **Next (M2-8a, no new
install):** extend the M2-6 verifier normalization to **`html.unescape` + strip backslash-escaped
quotes** (confirmed to fix F-014/F-016 → ≥96.8%); apply the Reviewer's **F-042 alternate-page** note
into TEST_PLAN §6 (added §6.5); **targeted re-run** of F-014/F-016/F-042 + any other entity/backslash
false-rejects across the 72 → flip to **FINAL PASS ≥95%**; verifier must still fail conservatively
(never false-accept a fabrication). **⛔ F-026 is a GENUINE miss — do NOT force-pass it:** retrieval
surfaced only the page-3 counsel occurrence → the model falsely refused a present fact (a **recall**
gap, not a verifier bug). Expected FINAL ≈ **62/63 (≥95%)** with F-026 the lone real miss; revisit
later via top_k/reranker/chunking (see `TASKS_M2.md` Risks). Then **M2-7** (FastAPI loopback surface,
D-13). **Carry-forward risk:** real-PDF section detection before M6.
_(M2 pipeline latency is much better than M1's AnythingLLM path — mean ~6.9s/median 7.0s/max 17.5s in
the M2-8 run; the ~19s figure below is the M1-10/turnkey number.)_

**Perf carry-forward (M2-3 / pre-M4 demo):** per-question latency was high (mean ~19s, max ~78s,
qwen3 "thinking"); first-token (<3s CE_PLAN §2 target) not separately instrumented. Size a
thinking-mode/latency tuning pass on the custom pipeline + production hardware. **Pinned digests
(D-11):** `qwen3:14b=bdbd181c33f2`, `bge-m3=790764642607`.

**⚠ Key go/no-go risk (M1-5 Tester flag — read before M1-10).** On the EMPTY `m1-golden` workspace a
non-legal trivia prompt returned "Blue." **with a fabricated citation** ("Weather Conditions, p.3")
instead of the §10 refusal. The turnkey stack has **no mechanical span verification** (that is M2-3 /
D-19) — the §10 prompt is the ONLY guardrail, and it already let a hallucinated citation through. This
is the exact **M1-12 (0%-hallucination refusal)** risk and likely the binding gate.
- **✅ RESOLVED in M1-7b:** root cause was **chat mode** (answers from world knowledge). `m1-golden`
  is now persisted to **query mode** and the M1-7b probe showed NF-001/002/003 all **refuse + cite
  nothing** with the exact D-30 sentence — the "Blue." leak no longer reproduces. M1-10 confirms at
  full scale. (Caveat carried to M1-10: score "cites nothing" on the answer's asserted citations, not
  AnythingLLM's always-present `sources` array.)
- **✅ Context window:** raised from **8192** to **32768** and verified effective via `/api/ps`
  (`context_length=32768`, no OOM) in M1-7b.
- **Run path / safety:** M1-10 poses questions via the **v1 query chat** (`/api/v1/workspace/
  m1-golden/chat`), single-turn, **never agent mode** (this build's `stream-chat` swaps to agent mode,
  which can use tools/web → would violate no-action/no-egress, CE_PLAN §3 #12). Strip `<think>…</think>`
  before scoring. Fabricated citations are **hard fails** (TEST_PLAN §3.1/§4).
- **Go/no-go framing:** if M1-12 cannot reach 100% after reasonable prompt/config tuning, that is
  itself the key datapoint — it would indicate the turnkey stack is insufficient WITHOUT the M2-3
  span-check, a legitimate input to the M1-13 decision (owner call), not a silent failure.

**M1-EH RESOLVED (owner decision).** App-level telemetry is disabled + log-confirmed. For zero-egress
(SC-6), the **M1-10 measurement run executes with networking OFF (air-gap)** — the loopback-only
pipeline works offline, which also moots the Chromium DoH/encrypted-DNS residual. **No host firewall
this cycle;** `pf`/Little Snitch are deferred to M5/M6 persistent-online hardening. The networking-off
step + an egress confirmation are folded into the M1-10 procedure (`eval/TEST_PLAN.md` §2).

_PDF rendering of the corpus (for true page-level citation testing) remains a follow-up that must use
a confirmed no-install path or its own approval._

**Air-gap posture (post-decision):** AnythingLLM anonymous telemetry is **disabled + log-confirmed**.
The remaining launch egress (Chromium DoH/encrypted DNS to the ISP) is handled by running M1-10 with
**networking off**, not a firewall. **Historical note (cannot be recalled):** a pre-disable
`workspace_created` event already shipped config metadata (model names / vector-db type / anon id) —
**no document content**; reinforces full air-gap from the start for M5/M6 real-data work.

## Blockers

- **None technical.** Install + wiring chain M1-1..M1-5 complete and verified loopback-only;
  **M1-EH resolved** (telemetry off; M1-10 runs air-gapped, no firewall this cycle). Next is M1-7
  (load the synthetic corpus into `m1-golden`) — synthetic docs only, no fresh install required. Per
  `CLAUDE.md`, nothing further is installed/configured without confirming the task calls for it.

## Standing reminders

- Fake/sanitized/public documents only. No real attorney/client data on this machine.
- Local-only; loopback binding; no public ports; no cloud dependencies without written approval.
- Do not scaffold the custom production pipeline (Milestones 2+) until the M1 gate passes.
