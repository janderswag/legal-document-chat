# Legal Document Intelligence System

Private, **local-first / air-gapped** AI document hub for a solo attorney — search, retrieve,
summarize, and ask questions across the attorney's own documents with **page-level cited
answers**. This is a cited-retrieval assistant, **not** an AI lawyer and **not** an autonomous
agent. The attorney verifies every answer.

## Start here

- **[CE_PLAN.md](CE_PLAN.md)** — the finalized engineering plan (17 sections). Read it before
  writing any code.
- **[docs/CE_PLAN_VALIDATION_REPORT.pdf](docs/CE_PLAN_VALIDATION_REPORT.pdf)** — the external
  technical validation the plan was revised against.

## Hard rules (from the plan)

- **Dev uses fake / sanitized / public documents only.** Real attorney/client documents are
  touched **only at Milestone 6 — onsite, on attorney-owned hardware, after written approval.**
- The answering agent has **no action tools and no network egress** (retrieval is separated from
  anything that can act or reach outside).
- **No legal advice. No unsourced answers. No hidden cloud processing.**

## Environments

- **Dev (this machine):** MacBook Pro 14" — Apple M4 Pro, 24GB unified, macOS Tahoe 26.5.
- **Production:** Mac Studio M4 Max (purchased by the attorney after pilot validation).

## Next step — Task 0 (the go/no-go gate)

Before any custom code or hardware purchase, stand up the **turnkey pilot** and prove citation
accuracy:

1. Install **Ollama** + **AnythingLLM** (both native macOS apps).
2. `ollama pull qwen3:14b` and `ollama pull bge-m3`.
3. Load a small **sanitized** test corpus.
4. Build a **50+ question golden eval set** (each question → known source page).
5. Measure citation accuracy + not-found refusal.

Do not proceed to the custom LlamaIndex build until this proves accurate retrieval + citation.
See **§17 First Implementation Tasks** in the plan.

> Nothing in this repo is implemented yet. The plan is finalized; code begins at Task 0 above.
