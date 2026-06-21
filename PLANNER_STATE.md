# PLANNER_STATE.md — Planner handoff (pre-context-clear)

> Snapshot of the Planner tab's state. Read alongside `RELAY.md` (loop manual), `RUN_STATE.md` (source
> of truth + Next task), `DECISIONS.md` (D-1..D-39), `TASKS_M2.md`, `eval/TEST_PLAN.md`. Most Planner
> state already lives in those files; this captures only the forward-looking judgment that doesn't.

## Role
Scope + sequencing owner. Read `RUN_STATE.md` "Next task" → write the next **Builder prompt**
(small, test-first, owner-gated, self-contained, ends by instructing the Builder to emit the Reviewer
prompt). Surface genuine forks to the **owner** via a question; never change a locked decision alone.
Record every decision into `DECISIONS.md`; keep `RUN_STATE.md` + `TASKS_M2.md` current. Flag each new
install at its gate.

## Current position
**✅ SAM-style local UI COMPLETE (D-48, Tester-confirmed + Planner-verified 2026-06-20).** All 7 tasks 🟢
(commits `77a3b88`→`0e7abdb`); eval stores + M2-8 byte-identical; 0 non-loopback; product boundary held.
App runs at `http://127.0.0.1:8000/app`; tree clean (all committed). **Next = OWNER DIRECTION** (relay
auto-starts nothing): complete CE_PLAN M4 (user-guide + demo script → attorney UAT) / more UI polish /
close the `<3s` latency yellow (G-LAT) / housekeeping (drop 2 synthetic test matters from the live
catalog; capture an `/app` screenshot). Owner-gated beyond M4: M4-5 hardware (no purchase on spec), M6
real data (written approval). _Earlier position retained below for history._

### (Earlier) Current position
**M2-3 capability complete (D-44); M2/M3 acceptance-gap closeout underway (D-45).** M2-8 = FINAL PASS
(D-40), M2-7 (D-41), M2-9 (D-43) all Tester-confirmed. A **CE_PLAN cross-reference** (§2 SC-1..SC-7 /
§14) showed D-44's "complete" was capability-level (page+span eval) and surfaced real CE_PLAN acceptance
gaps. **M2/M3 gap-closure DONE (D-47).** The 7-task batch landed + was Tester-confirmed and Planner-verified
(commits `89c7c66`→`c2cc89f`; baseline `.lancedb`/M2-8 byte-identical; new stores git-ignored — I
checked the git/filesystem myself, didn't just trust the report). SC-1/SC-2(capability)/§8/hybrid(off,
negative lift)/SC-7/SC-3-6 all 🟢; **lone yellow = `<3s` first-token (~3.6s, NOT met)** — §2/M3
quantitative target, hardware-hypothesis for D-22 (unproven). The SC-1…SC-7 demo-GO gate is met but
M3 acceptance isn't 100% (latency) — **do not relabel "complete."** **Next = OWNER decision** (relay
auto-starts nothing): CE_PLAN **M4 attorney-demo prep** / chase latency first / other. **Surface to the
owner:** the latency yellow (validate on real hardware, not assume), and two loose ends — (1) commit the
uncommitted prior-milestone code (M2-7/M2-9/UI); (2) egress-log discipline (logs must carry real
samples). Still owner-gated: M4-5 hardware (no purchase on spec, D-21/D-22), M6 real data (written
approval); each carries its own sub-fork to surface first. **Formal CE_PLAN Milestone-4 attorney demo needs SC-1..SC-7
all green.** Still owner-gated beyond M3: **M4-5 hardware** (after demo; no purchase on spec, D-21/D-22)
and **M6 real data** (onsite, written approval; hard rules #1–#2) — each carries its own sub-fork to
surface first.

## Remaining M2-3 sequence (after M2-8a)
- **M2-7** — FastAPI loopback HTTP surface (D-13; LlamaIndex was dropped, D-37, but FastAPI stands).
  Last build step; loopback-only, no `0.0.0.0`.
- **M2 milestone wrap** — record the milestone result (custom pipeline cleared the page+span bar the
  turnkey stack failed). Then the project looks toward **M4-5 hardware** (owner decision, no purchase
  on spec — D-21/D-22) and eventually **M6** (onsite real data, written approval).

## Anticipated forks to put to the owner (don't pre-decide)
- **M2-7:** API auth/shape for a loopback single-user service (likely none/minimal — confirm).
- **Pre-M4 demo:** latency tuning pass (qwen3 "thinking" mean ~19s/Q vs <3s target) — when + how.
- **Before M6 (real data):** the open **real-PDF section-heading robustness** risk (Docling
  `section_header` detection vs the synthetic `#` markers) must be validated on heading-less PDFs.

## Watch items / carry-forward (also in RUN_STATE/TASKS_M2)
- Verifier must **fail conservatively** (D-38/M2-6) — never weaken fabrication rejection to chase %.
- Reranker stays **OFF by default** (D-36, neutral lift) until real-scale justifies it.
- Egress-monitored air-gap (D-31) on every full run; manual scoring only (no auto-scorer).

## How I resume
Read `RUN_STATE.md` "Next task". If a Tester report is pending, process it (record results +
decisions, update docs), then emit the next Builder prompt. If a fork blocks the next task, ask the
owner first.
