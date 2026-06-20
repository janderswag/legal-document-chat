# CLAUDE.md — Legal Document Intelligence System

> Project governance for every Claude Code session in this folder.
> Source of truth for scope: `CE_PLAN.md`. Current status: `RUN_STATE.md`.
> Read this file and `RUN_STATE.md` at the start of every session before doing anything.

> **This is a standalone, self-contained project**, living at `~/projects/legal-doc-intelligence/`.
> It is unrelated to any other project on this machine (in particular the "Proposal & SOW Generation
> Agent"). The only instructions that govern this project are this file, the other docs in this
> folder, and the user's global `~/.claude/CLAUDE.md`. No other project's `CLAUDE.md` applies here.

## What this project is

A **private, local-first document intelligence system** for a **solo attorney**. It lets the
attorney search, retrieve, summarize, and ask plain-English questions across **their own**
documents and get back answers that are **grounded in and cited to the source** (file + page +
section + chunk + verbatim span). The attorney verifies every answer against the cited source.

## What this project is NOT

- **It is NOT an AI lawyer.** No legal advice, no legal conclusions, no outcome predictions, no
  strategy recommendations. It locates and summarizes what the documents say. Nothing more.
- **It is NOT an autonomous agent.** It never acts, sends, files, or changes anything in the
  outside world. The answering component has no action tools and no network egress.

## Hard safety rules (non-negotiable)

These are boundaries, not backlog items. Do not violate them, and do not build features that would.

1. **Fake / public / sanitized documents ONLY in development.** Use synthetic contracts, sample
   pleadings, public-domain legal texts, and fabricated correspondence. Nothing real.
2. **Never process real attorney/client documents on this machine.** Real data is touched only at
   Milestone 6, onsite, on attorney-owned hardware, after **written** approval. Not here. Not now.
3. **No cloud dependencies unless explicitly approved in writing.** Local-only inference,
   embedding, OCR, and storage. No API keys are required for the local path. If a task seems to
   need a cloud service, stop and ask.
4. **Do not expose ports publicly.** Services bind to `127.0.0.1` (loopback) only, never `0.0.0.0`.
   No public DNS, no public IP, no tunnels, no port-forwards.
5. **No autonomous legal actions.** Specifically, the system must never:
   - send email (no SMTP, no mail API, no draft-and-send),
   - file court documents (no e-filing, no submission),
   - contact clients or third parties,
   - modify or delete legal documents (originals are read-only; only derived stores are written),
   - take any action on the attorney's behalf.
6. **No unsourced answers.** Every factual claim traces to a retrieved chunk. If the documents do
   not support an answer, the system says **"I could not find this in the documents."**
7. **Secrets are never committed.** `.env` is git-ignored; only `.env.example` with placeholders.

## Current milestone — Milestone 1 ONLY

We are executing **Milestone 1 only**. Do not work ahead of it.

**Milestone 1 goal:** stand up a turnkey local pilot and prove citation accuracy before any
custom code or hardware purchase.

- **Ollama + AnythingLLM** installed natively on this Mac (no Docker for the pilot).
- Models pulled: **`qwen3:14b`** (chat) + **`bge-m3`** (embedding).
- A small **sanitized corpus** loaded into AnythingLLM.
- A **golden eval set of 50+ legal-style questions**, each mapped to a known source page.
- Measure **citation accuracy** (correct answer + correct filename + page) and
  **not-found refusal** (refuses every time the evidence is absent).

**Milestone 1 acceptance / go-no-go gate:** the turnkey stack answers golden questions with
correct filename + page citations and refuses on not-found. This is the gate before building any
custom code or buying hardware.

### Do NOT do yet (blocked until Milestone 1 passes)

- **Do not scaffold the custom production pipeline** (FastAPI + LlamaIndex + Qdrant/LanceDB +
  Docling + reranker + mechanical span verification). That is Milestones 2–3, after the gate.
- Do not write application code for ingestion, retrieval, or answering.
- Do not buy or spec production hardware.

## How to work in this repo

- **Every task must be small, tested, and summarized.** Prefer the smallest change that proves
  the next thing. State assumptions before acting; if something is ambiguous, ask.
- **Surgical changes only.** Touch only what the task requires. Match existing style.
- **Do not install anything or run setup steps without confirming the task calls for it.** When a
  task does require installs, say exactly what will be installed and why first.

## Required report after every change

After making changes, always report:

1. **Files changed** — paths, with a one-line note on each.
2. **Commands run** — exact commands, and whether each succeeded.
3. **Verification result** — what you checked and what the outcome was.
4. **Risks** — anything that could be wrong, unsafe, or worth a second look.
5. **Next recommended task** — the single next step, scoped small.
