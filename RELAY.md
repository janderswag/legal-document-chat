# RELAY.md — the 4-tab loop operating manual

> Read this first in ANY tab after a context clear. It re-establishes the Planner → Builder → Reviewer
> → Tester relay. The durable state of this project lives in the **tracked files below**, not in any
> tab's conversation history — so a tab can be cleared and restored from these files at any clean
> (between-task) boundary with no loss.

## The loop

**Planner (tab 1) → Builder (tab 2) → Reviewer (tab 3) → Tester (tab 4) → back to Planner.**
The human relays each prompt between tabs. Every tab **ends its turn by emitting the next tab's
prompt** (Planner emits the Builder prompt; Builder emits the Reviewer prompt; Reviewer emits the
Tester prompt; Tester reports results back to the Planner).

## Roles & responsibilities

- **Planner (tab 1):** owns scope and sequencing. Reads `RUN_STATE.md` "Next task", surfaces genuine
  forks to the **owner** (never decides locked-decision changes alone), records decisions into
  `DECISIONS.md`, keeps `RUN_STATE.md`/`TASKS_M2.md` current, and writes the next **Builder prompt**
  (small, tested, owner-gated, self-contained). Flags every new install at its gate.
- **Builder (tab 2):** restores from `BUILDER_STATE.md`, executes exactly one task **test-first**,
  reports (files / commands / verification / risks / scope), then emits the **Reviewer prompt**.
- **Reviewer (tab 3):** audits the Builder's work against the task contract + `DECISIONS.md` +
  `eval/TEST_PLAN.md`; checks correctness, scope discipline, and safety (loopback-only, no real data,
  conservative verifier). Emits the **Tester prompt**.
- **Tester (tab 4):** independently reproduces/exercises the result (fresh invocation, not the
  Builder's cache), confirms egress posture, surfaces carry-forward findings, then reports the
  confirmed numbers + recommendations back to the **Planner**.

## Canonical state files (read at restore, in this order)

1. **`CLAUDE.md`** — governance, hard safety rules, current milestone (now **Milestone 2-3**).
2. **`RUN_STATE.md`** — single source of truth for status + **"Next task"** (the pointer that drives
   the loop) + completed log + carry-forward risks.
3. **`TASKS_M2.md`** — the M2-3 checklist (done + next). `TASKS.md` = M1 (historical, PASSED).
4. **`DECISIONS.md`** — locked decisions **D-1 … D-39** (every architectural/scope/scoring call + why).
5. **`eval/TEST_PLAN.md`** — eval rubric; **§3/§4** = M1 filename-level (D-29), **§6** = M2 page+span bar (D-39).
6. **`BUILDER_STATE.md`** — Builder's in-flight code snapshot (regenerated before each Builder clear).
7. The **pipeline code** under `pipeline/` (ingest → chunk+SAC → LanceDB → retrieve → answer → verify).

## Standing constraints (always true — from CLAUDE.md / BUILDER_STATE.md §5)

- **Local-only, loopback-only.** System Ollama `127.0.0.1:11434` (NOT AnythingLLM's bundled engine).
  Never bind `0.0.0.0`; never set `OLLAMA_HOST`. Keep `DISABLE_TELEMETRY='true'`.
- **Synthetic/public documents only. No real attorney/client data** anywhere (real data = M6, onsite,
  written approval).
- **Installs/model pulls are owner-gated, one step at a time** (approved via the relay prompt).
- **D-11 model pins:** `qwen3:14b=bdbd181c33f2`, `bge-m3=790764642607`, + `RERANKER_REVISION`
  (`reranker.py`). A change forces re-index/re-eval. **Reranker OFF by default** (D-36, neutral lift).
- **Git-ignored (D-28):** document bodies (`documents/`), `pipeline/.lancedb/`, chunk data,
  `eval/results/`. Never commit a document body or a secret/API key.
- **Manual eval scoring** — an auto-scorer is approval-gated tooling (`TEST_PLAN.md` §3/§5).
- **The verifier (M2-6) fails conservatively** — a false-reject of a truthful span is a precision bug;
  it must never false-**accept** a fabrication. Displayed citations are **chunk-derived** (D-38).
- **Air-gap proof = egress-monitored** (D-31): networking on + `lsof`/`nettop` show zero non-loopback;
  no physical disconnect for synthetic-corpus runs.

## How to resume after a clear

1. Each tab: read this file + the canonical files + its own `*_STATE.md` (if any); confirm role; report ready.
2. **Planner** reads `RUN_STATE.md` "Next task" and emits the next Builder prompt. Others **await their
   handoff prompt** (Builder awaits Planner; Reviewer awaits Builder; Tester awaits Reviewer).
3. Clear context only at a **between-task boundary** (no half-finished edits). If mid-task, finish or
   record it in `BUILDER_STATE.md` §3 first.

## Where we are (update this line each milestone beat)

**✅ SAM-style local UI COMPLETE (D-48, 2026-06-20, Tester-confirmed):** 7 tasks 🟢 (commits
`77a3b88`→`0e7abdb`) — left nav, matter-scoped upload+cited-chat, retrieved-page thumbnails + cited-span
highlight, "100% local · 0 outbound" badge; dedicated `.lancedb_kb`; eval stores + M2-8 byte-identical; 0
non-loopback; product boundary held. App at `http://127.0.0.1:8000/app`; tree clean. **Next = OWNER
DIRECTION:** complete CE_PLAN M4 (user-guide + demo script → attorney UAT) / UI polish / `<3s` latency
yellow / housekeeping. Plans under `docs/superpowers/plans/`. _M2/M3 gap-closure (D-47) done; M4-5
hardware + M6 real data owner-gated._

### (Prior beat)

**🎉 MILESTONE 2-3 COMPLETE (D-44, 2026-06-20).** M2-8 = FINAL PASS (D-40: page+span 62/63 = 98.4%, 0
displayed fabrications, NF 9/9, DRM 2/2), M2-7 done (D-41: loopback FastAPI surface), M2-9 done (D-43:
single-service Compose, Ollama on host via `host.docker.internal`, published `127.0.0.1:8000` only,
0 non-loopback egress — **COMPOSE-ONLY** loopback boundary, never `docker run -p`). The custom pipeline
delivers the verifiable page+span citation the turnkey stack proved impossible. **A CE_PLAN
cross-reference (D-45) reframed D-44 as capability-level** and opened the **M2/M3 acceptance-gap
closeout** (plan: `docs/superpowers/plans/2026-06-20-m2m3-gap-closure.md`), **now DONE** via a 7-task
batch (D-47, Tester-confirmed + Planner-verified, commits `89c7c66`→`c2cc89f`; baseline untouched).
**SC scorecard:** SC-1/SC-2(capability)/§8/hybrid(off)/SC-7/SC-3-6 all 🟢; **lone yellow = `<3s`
first-token (~3.6s, NOT met)** — a §2/M3 quantitative target, hardware-hypothesis for D-22. SC-1…SC-7
demo-GO gate met; do NOT relabel M2/M3 "complete" (latency open). **Next = OWNER decision on CE_PLAN
M4 (attorney UAT)**; loose ends: commit prior-milestone code, validate latency on real hardware. Still
owner-gated: M4-5 hardware (no purchase on spec), M6 real data (written approval).
