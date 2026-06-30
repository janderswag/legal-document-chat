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

## Current position (2026-06-30)
**Desktop distribution track in flight.** Desktop **v1 DONE** (D-59, Tester GREEN, `c0400cb`: macOS
pywebview launcher + first-run wizard + landing). **Landing redesign DONE** (Planner-built live, `7ea6c43`:
white incident.io-style hero, **animated demo** `site/demo.html` embedded as the hero shot, setup
stack-diagram). **Distribution finding (D-60):** direct **notarized download works WITH Ollama** (Phase B
path); **Mac App Store BLOCKED by the Ollama dependency** (sandbox + self-contained) → launch direct-download
first, sell via license keys; MAS needs embed-the-engine (later). **▶ NEXT (owner-gated to kick):** Desktop
**v1.1 Builder batch** (launcher hard-kill hardening · root-route `/`→`/setup` · **wizard auto-pull models**
· broaden copy) → then **Windows pass** (owner's machine). **Open owner decisions:** transcripts copy↔build
(landing now lists "transcripts"+exact-line, but page:line is deferred D-56); step-2 wording; pricing via
license keys (D-58/D-60). _Uncommitted on Planner side at flush time: "transcripts" added to hero lede →
committing now._ Earlier history below.

### (Earlier) Current position
**▶ M-ENRICH workstream underway (OSS-evaluation roadmap, D-49/D-51).** Owner directed a 9-repo deep dive
(`docs/research/2026-06-21-oss-evaluation.md`); an independent Tester cross-eval converged (D-51). Roadmap
greenlit, sequenced **clause → tables → grid**, transcripts separate; all four threads in `TASKS_M2.md` →
M-ENRICH. **Owner workflow shift (saved as `feedback-builder-comprehensive-prompts`):** Builder prompts are
now **complete features end-to-end**, anti-laziness, "going slow OK" — Reviewer/Tester find gaps.
- **✅ T-CLAUSE DONE (D-52, Tester GREEN ×6 + Planner-verified).** Contract Review clause checklist, 5
  layers, no stubs; never-false-accept held on every path incl. wrong-file doc_id post-filter; 159/159;
  baseline byte-identical; 0 non-loopback. 2 yellows (doc_id regression test + commit untracked) folded
  into T-TBL step-0. KB matter slug = `pemberton-demo`; egress monitors must be PID-scoped (`lsof -a`).
- **✅ T-TBL DONE (D-53, Tester GREEN ×7 + Planner-verified + committed).** Docling TableFormer tables
  end-to-end; tables span-verifiably citable; never-false-accept holds on table chunks; offset-routing D-51
  (table self-relative, prose PyMuPDF byte-identical, never mixed); `has_tables` gating; 175/175; baselines
  untouched. Carry-forwards: TABLEFORMER_REVISION code-enforce (a); prune synthetic KB matters before demo (c).
- **✅ M-ENRICH backlog DONE (D-55, Tester GREEN 240/240 + closeouts + committed).** T-GRID + B1–B6 +
  C1/C2 + D1. Never-false-accept across grid/streaming/fuzzy; bounded concurrency; baselines byte-identical;
  0 non-loopback. Closeouts: canonical `scripts/baseline_hash.sh` (CWD-independent; re-pinned canon hashes
  `537146cf…`/`d329c91e…`/`07f04972…`); empty dir removed; A0 import-time air-gap fix.
- **⏸️ T-TRANS DESIGN DONE, BUILD DEFERRED (D-56).** Brainstormed to a full spec
  (`docs/superpowers/specs/2026-06-21-transcripts-design.md`); not built on spec — depositions already work
  as normal uploads (page-level cites); build the page:line layer only when a real deposition proves
  page-level insufficient (attorney deposition-heavy). Keystone preserves never-false-accept (page:line
  derived from the verified span). Parked alongside **agent personality** (tone-only, must not erode the
  no-advice product boundary).
- **▶ RELAY IDLE at owner direction. Queued decisions (not auto):** adopt the **F-026 fix** (C1 proven,
  baseline-affecting); approve **eyecite** (`[GATE]`); cheap transcript **gutter-strip**; OcrMac/MPS.
- **Owner-gated, untouched:** M4-5 hardware (no purchase on spec), M6 real data (written approval); open
  G-LAT `<3s` latency yellow (unaffected by M-ENRICH).

### (Earlier) ✅ SAM-style local UI COMPLETE (D-48, Tester-confirmed + Planner-verified 2026-06-20). All 7 tasks 🟢
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
