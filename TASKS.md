# TASKS.md — Milestone 1 Checklist (turnkey pilot)

> Milestone 1 ONLY. Do not add Milestone 2+ tasks here until the M1 go/no-go gate passes.
> Each task is small, tested, and summarized. See `CLAUDE.md` for rules, `RUN_STATE.md` for status.

## Setup

- [x] **M1-1 — Install Ollama** (native macOS app) and confirm the local server responds on
      `127.0.0.1:11434`. No public binding. _Done 2026-06-19: Homebrew formula, Ollama 0.30.10,
      verified loopback-only (`127.0.0.1:11434 LISTEN`), `OLLAMA_HOST` unset._
- [x] **M1-2 — Install AnythingLLM** (native macOS app) and confirm it launches. _Done 2026-06-19
      (owner granted fresh install approval): `brew install --cask anythingllm` 1.14.1 →
      `/Applications/AnythingLLM.app`; launches (Electron main + helpers). Listeners loopback-only:
      `127.0.0.1:3001`, `127.0.0.1:8888`, and a bundled `llm serve` on `127.0.0.1:64562` — no
      `0.0.0.0/*`. Note: ships its own embedded Ollama/llm runtime; M1-5 must wire to the SYSTEM
      Ollama on `127.0.0.1:11434`, not the bundled one._
- [x] **M1-3 — Pull `qwen3:14b`** (`ollama pull qwen3:14b`); confirm it loads and answers a trivial
      prompt locally. _Done 2026-06-19 (owner-approved): pulled to SYSTEM Ollama (`:11434`, not the
      bundled `:64562` engine); `ollama list` shows `qwen3:14b` (digest `bdbd181c33f2`, 9.3 GB).
      Trivial `/api/generate` returned exactly `ok` (`done_reason: stop`); first call 5.89s total
      (5.47s load, sub-second eval). Binding still loopback-only; `OLLAMA_HOST` unset._
- [x] **M1-4 — Pull `bge-m3`** (`ollama pull bge-m3`); confirm it is available as an embedding model.
      _Done 2026-06-19 (owner-approved): pulled to SYSTEM Ollama (`:11434`, not bundled `:64562`);
      `ollama list` shows `bge-m3:latest` (digest `790764642607`, 1.2 GB). `/api/embed` round-trip
      returned a real **1024-dim** numeric vector (not chat text). Binding still loopback-only;
      `OLLAMA_HOST` unset._
- [x] **M1-5 — Wire AnythingLLM to Ollama** — chat model `qwen3:14b`, embedding model `bge-m3`,
      local-only. Confirm a round-trip query works. _Done 2026-06-19 (owner-approved): via
      `/api/system/update-env` set `LLM_PROVIDER=ollama`, `OLLAMA_BASE_PATH=http://127.0.0.1:11434`,
      `OLLAMA_MODEL_PREF=qwen3:14b` (digest `bdbd181c33f2`), `EMBEDDING_ENGINE=ollama`,
      `EMBEDDING_BASE_PATH=http://127.0.0.1:11434`, `EMBEDDING_MODEL_PREF=bge-m3:latest` (digest
      `790764642607`) — **SYSTEM Ollama, not bundled**; `DISABLE_TELEMETRY='true'` preserved. Created
      the **`m1-golden`** workspace (chatProvider `ollama`, chatModel `qwen3:14b`) with the CE_PLAN §10
      grounded-citation system prompt (refusal sentence pinned). Round-trip via `/api/v1/workspace/
      m1-golden/chat` returned a coherent `qwen3:14b` reply and `/api/ps` on `:11434` showed
      `qwen3:14b` loaded → confirms it hit the system instance. All listeners loopback-only._

## Sanitized corpus

- [x] **M1-6 — Assemble a small sanitized corpus** (synthetic contracts, sample pleadings,
      public-domain legal texts, fabricated correspondence). Fake/public/sanitized ONLY. Author the
      source documents under the git-ignored path **`documents/synthetic_corpus/`** (never an
      unignored `corpus/`), so document bodies are never committable by default (D-28). Record
      ground truth in the **tracked `eval/` manifest** (schema in `eval/README.md`): metadata,
      templates, and short `verbatim_span` snippets only — never a full document body.
- [x] **M1-7 — Load the corpus into an AnythingLLM workspace**; confirm all documents embed without
      error. _Done 2026-06-19: D-11 digests re-verified (`qwen3:14b=bdbd181c33f2`,
      `bge-m3=790764642607`) before embedding. Uploaded all 6 synthetic docs via the v1 API (original
      filenames preserved) and embedded into `m1-golden` via **`bge-m3` on `:11434`** (`/api/ps`
      showed `bge-m3:latest` load during embed). **6/6 embedded, error: None**, LanceDB namespace
      `m1-golden.lance` created; loopback-only, telemetry still disabled.
      **⚠ Finding for M1-7b:** each doc embedded as **exactly 1 chunk** (docs are 317–809 tokens; the
      M1-5 `EMBEDDING_MODEL_MAX_CHUNK_LENGTH=8192` makes each whole doc a single chunk). Combined with
      the watch item (**Markdown ingest has no real pages**; the `===== PAGE N =====` markers are
      inline text, not structural pages), AnythingLLM cannot produce sub-document/page-level citations
      as configured — likely fails M1-11 `page_match`. M1-7b should lower chunk size (and/or revisit
      the deferred PDF-render path for real pages) before M1-10._
- [x] **M1-7c — Page-faithful re-ingest (owner decision: KEEP page-level).** _Done 2026-06-19:_
      D-11 digests re-pinned. Rendered all 6 docs to **paged PDFs** (no-install: headless Google
      Chrome `--print-to-pdf`, one physical page per `===== PAGE N =====` marker) under git-ignored
      `documents/synthetic_corpus/pdf/`. **Page fidelity verified:** PDF page counts == manifest max
      page (3/3/3/2/2/2); **63/63 present-fact spans land on the correct page** (62 exact via PDFKit +
      1 confirmed-correct `twenty-four` hyphen line-wrap artifact). Manifest filenames updated
      `.md`→`.pdf` (**extension-only**, 63 records, proven identical after stripping extension; no
      other field touched). Removed the 6 Markdown docs from `m1-golden`, lowered chunk size
      (`EMBEDDING_MODEL_MAX_CHUNK_LENGTH='1000'`), re-ingested the 6 PDFs via `bge-m3` on `:11434`:
      **6/6 clean, total chunks 6→16** (lease 3, complaint 3, MSA 4, statutes 2, demand 2, order 2);
      loopback-only; telemetry disabled.
      **🚩 CRITICAL for M1-7b/go-no-go:** AnythingLLM 1.14.1's desktop PDF parser **flattens all pages
      into one `pageContent` blob and the resulting chunk metadata is EMPTY (no page field)** — so
      chunks carry **no page numbers**. Page-faithful PDFs alone do **not** make the turnkey stack emit
      page-level citations; the bottleneck is the parser. M1-7b's probe must confirm against live
      citations; if confirmed, **page-level citation (M1-11 `page_match`) likely is not achievable on
      the turnkey AnythingLLM stack** and becomes a go/no-go input (custom pipeline M2-3, or an owner
      re-decision on page-level scope)._
- [x] **M1-7b — Pre-measurement workspace config + refusal validity check.** _Done 2026-06-20:_
      Persisted **query mode** on `m1-golden` (DB `chatMode='query'`) — fixes the M1-5 "Blue."
      world-knowledge leak. Raised context to **32768** (`OLLAMA_MODEL_TOKEN_LIMIT='32768'`),
      **verified effective** via `/api/ps` → `qwen3:14b context_length=32768` (no OOM). §10
      grounded/refusal prompt confirmed active (answers cite + carry the D-5 footer; refusals return
      the exact D-30 sentence). **Probe (v1 query chat, `<think>` stripped, sessionId per Q):**
      F-001 → "March 14, 2024" + citation `nimbus_pemberton_msa.pdf` (matches manifest); F-004 →
      "$47,350" + `nimbus_pemberton_msa.pdf` (matches); NF-001/002/003 → **"I could not find this in
      the documents."** (refused, no substantive claim). Loopback-only; telemetry disabled.
      **🚩 M1-10 measurement-definition flag:** in query mode AnythingLLM **always returns a `sources`
      array (retrieved chunks) even on a refusal** — so `returned_citations` for §3.2 scoring must be
      the citations the **answer asserts**, NOT the `sources` array, or every NF false-fails the
      "cites nothing" gate. Also: present-fact answers self-assert a page/section in prose, but page
      is unverifiable (D-29) — score **filename only**, don't trust the model's page claim._

## Golden eval set

- [x] **M1-8 — Build the golden eval set: 50+ legal-style questions**, each mapped to a known
      source document + page. Store as structured `(question, expected_answer, expected_source_page,
      category)` records. _Done: `eval/golden_questions.jsonl` (72 questions, 1:1 with the manifest);
      run procedure + rubric + thresholds in `eval/TEST_PLAN.md`._
- [x] **M1-9 — Include a "not found" category** — questions whose answer is deliberately absent from
      the corpus, to test refusal. _Done: 9 not-found questions (NF-001..NF-009) over deliberately
      absent topics._

## Air-gap hardening (complete before M1-10)

- [x] **M1-EH — M1 egress hardening.** Tester flagged that the **idle AnythingLLM app** holds
      persistent HTTPS to Google Cloud (`35.190.80.1`) + Cloudflare (`104.26.0.186/.1.186`) —
      suspected telemetry/update. No document-bearing egress was observed (no docs loaded) and system
      Ollama (`:11434`) has **zero** outbound. **Owner-chosen scope: app-level only, then reassess.**
      Disable AnythingLLM telemetry + update checks (`DISABLE_TELEMETRY` / in-app privacy setting),
      fully restart the app, and re-run the Check-3 egress snapshot to confirm the Google Cloud +
      Cloudflare outbound is gone. **Do not** apply a host firewall (`pf`) or install Little Snitch
      this round; if outbound persists, document what remains and report back for a reassessment
      decision (no escalation without approval). Supports SC-6; required hardening ahead of M5/M6
      real-data handling. Owner sequenced this **before M1-5**; must land before M1-10.
      _Status 2026-06-19 (app-level done; host-control reassessment pending):_ Set
      `DISABLE_TELEMETRY='true'` in AnythingLLM's own `storage/.env` (backup `.env.m1eh.bak`);
      bundled-engine wiring untouched. Restarted; **log-confirmed** `[TELEMETRY DISABLED] … no events
      will send` (before: `[TELEMETRY SENT]` server_boot/onboarding/workspace_created, leaking config
      metadata to Mintplex via Cloudflare). Measured before/after launch egress: the **anonymous
      telemetry** HTTPS (Cloudflare) is gone; **residual at launch = Chromium DoH to the ISP**
      (`doh-01/02.spectrum.com`, Charter — encrypted DNS), which **no app setting controls**. No
      document-bearing egress (no docs loaded); system Ollama `:11434` zero outbound; loopback
      listeners intact. **Zero app-outbound NOT achieved** by app-level alone → owner reassessment.
      **RESOLVED 2026-06-19 (owner decision):** for zero-egress (SC-6) the **M1-10 run executes with
      networking OFF (air-gap)** — loopback-only pipeline works offline and the DoH residual is moot.
      **No host firewall this cycle;** `pf`/Little Snitch deferred to M5/M6 persistent-online
      hardening. The networking-off step + egress confirmation are folded into M1-10 (below).

## Measurement (the go/no-go gate)

- [x] **M1-10 — Run the golden set through the pilot** and record each answer + its citation.
      _Done 2026-06-20: all 72 questions posed via v1 query chat (fresh sessionId/Q, single-turn,
      `<think>` stripped); 72/72 captured, 0 errors → git-ignored
      `eval/results/run-2026-06-20-qwen3-14b.jsonl`. Egress-monitored (D-31, networking ON): 74
      snapshots, **0 non-loopback**, max established=2 (loopback AnythingLLM↔Ollama) →
      `eval/results/egress-2026-06-20.log` (SC-6 met). Manual grades in
      `eval/results/grades-2026-06-20-qwen3-14b.md`. Perf (informational): mean 19.2s, max 77.9s
      total/Q (thinking model; first-token not separately instrumented), no OOM at 32K._
      **Air-gap (D-31 — egress-monitored):** networking stays **ON**; run a **continuous** egress
      monitor (`lsof`/`nettop`/pktap) for the full run and prove **zero non-loopback / zero
      document-bearing egress** (CE_PLAN §2 SC-6). Loopback-only pipeline; physical NIC-off reserved
      for M6. **Run path:** pose each question via the **v1 query chat**
      (`/api/v1/workspace/m1-golden/chat`), **fresh sessionId per question**, single-turn, **never
      agent mode** (this build's `stream-chat` swaps to agent/tool mode — CE_PLAN §3 #12). Strip
      `<think>…</think>` before scoring. Capture raw to git-ignored
      `eval/results/run-2026-06-20-qwen3-14b.jsonl`. **Scoring (manual; auto-scoring is approval-gated
      tooling per TEST_PLAN §3):** citation at **filename level** per **D-29** (fabricated filename =
      hard fail); NF on substance per **D-30** (score the answer-asserted citation, **ignore the
      always-present `sources[]`**; tangential accurate quote logged, not failed).
- [x] **M1-11 — Measure citation accuracy (filename-level, D-29)** — answer correct AND a returned
      citation points to the correct **filename**. _Result 2026-06-20: **63/63 = 100%** present-fact
      filename citation accuracy (≥95% target met); **0 fabricated filenames**; **DRM 2/2** (F-009→
      Pemberton MSA, F-025→Castellano lease, no cross-matter). Page/section/span informational only
      (reassigned to M2-3)._
- [x] **M1-12 — Measure not-found refusal** — the system returns "I could not find this in the
      documents" on every not-found question (target: 0% hallucination). _Result 2026-06-20: **9/9 =
      100%** refusal; all assert no citation; `refusal_wording_exact = 9/9` (exact D-30 sentence).
      0% hallucination._
- [ ] **M1-13 — Record the go/no-go decision.** Two findings: **(1) filename-level gate** (citation
      accuracy ≥95% + 0 fabricated + 100% refusal + 100% DRM, per D-29/§4) — PASS = turnkey adequate
      for grounded answers + refusal; FAIL = tune config/prompt and re-run. **(2) Established
      structural finding:** verifiable page+span citation is impossible on the turnkey stack →
      **the planned M2-3 custom build is justified** to obtain it (CE_PLAN §14 / D-7 / D-19). Record
      both; the page/span gap is the primary reason to proceed to M2-3, not a reason to keep re-running
      M1.
      _Builder recommendation 2026-06-20 (PENDING Reviewer audit + Tester repro + owner sign-off — not
      yet checked off):_ **(1) filename-level gate → RECOMMENDED PASS** (citation 100% ≥95%, fabricated
      0, refusal 100%, DRM 100% — all four §4 gates met). **(2) page+span structurally impossible on
      turnkey → M2-3 justified.** So the turnkey pilot proves grounded answering + filename grounding +
      not-found refusal, while the page/span citation bar moves to the M2-3 custom build. Final M1-13
      decision is the owner's to record._

## Out of scope for Milestone 1 (do NOT start)

- Custom FastAPI + LlamaIndex pipeline, Qdrant/LanceDB, Docling, OCR routing, reranker, mechanical
  span-level citation verification. (Milestones 2–3.)
- Production hardware purchase or provisioning. (Milestones 4–5.)
- Any real attorney/client documents. (Milestone 6, onsite, after written approval.)
