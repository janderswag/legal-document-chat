# RUN_STATE.md — Current project status

> Single source of truth for "where are we right now." Update this after every working session.
> Read at the start of each session alongside `CLAUDE.md`.

_Last updated: 2026-06-19_

## Status

**Planning complete; project governance established; repo isolated. Milestone 1 not yet started.**

The CE_PLAN is finalized and validated. No application code exists and none should be written until
the Milestone 1 turnkey pilot proves citation accuracy. The repo currently holds planning and
governance docs only.

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

_No setup, installs, code, or document processing performed._

## Next task

**M1-1 — Install Ollama** (native macOS app) and confirm the local server responds on
`127.0.0.1:11434` with no public binding. (Do not install until explicitly approved to begin
setup.)

## Blockers

- **None technical.** Awaiting go-ahead to begin Milestone 1 setup (installs). Per `CLAUDE.md`,
  nothing is installed without confirming the task calls for it.

## Standing reminders

- Fake/sanitized/public documents only. No real attorney/client data on this machine.
- Local-only; loopback binding; no public ports; no cloud dependencies without written approval.
- Do not scaffold the custom production pipeline (Milestones 2+) until the M1 gate passes.
