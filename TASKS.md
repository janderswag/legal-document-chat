# TASKS.md — Milestone 1 Checklist (turnkey pilot)

> Milestone 1 ONLY. Do not add Milestone 2+ tasks here until the M1 go/no-go gate passes.
> Each task is small, tested, and summarized. See `CLAUDE.md` for rules, `RUN_STATE.md` for status.

## Setup

- [ ] **M1-1 — Install Ollama** (native macOS app) and confirm the local server responds on
      `127.0.0.1:11434`. No public binding.
- [ ] **M1-2 — Install AnythingLLM** (native macOS app) and confirm it launches.
- [ ] **M1-3 — Pull `qwen3:14b`** (`ollama pull qwen3:14b`); confirm it loads and answers a trivial
      prompt locally.
- [ ] **M1-4 — Pull `bge-m3`** (`ollama pull bge-m3`); confirm it is available as an embedding model.
- [ ] **M1-5 — Wire AnythingLLM to Ollama** — chat model `qwen3:14b`, embedding model `bge-m3`,
      local-only. Confirm a round-trip query works.

## Sanitized corpus

- [ ] **M1-6 — Assemble a small sanitized corpus** (synthetic contracts, sample pleadings,
      public-domain legal texts, fabricated correspondence). Fake/public/sanitized ONLY.
- [ ] **M1-7 — Load the corpus into an AnythingLLM workspace**; confirm all documents embed without
      error.

## Golden eval set

- [ ] **M1-8 — Build the golden eval set: 50+ legal-style questions**, each mapped to a known
      source document + page. Store as structured `(question, expected_answer, expected_source_page,
      category)` records.
- [ ] **M1-9 — Include a "not found" category** — questions whose answer is deliberately absent from
      the corpus, to test refusal.

## Measurement (the go/no-go gate)

- [ ] **M1-10 — Run the golden set through the pilot** and record each answer + its citation.
- [ ] **M1-11 — Measure citation accuracy** — answer correct AND citation points to the correct
      filename + page.
- [ ] **M1-12 — Measure not-found refusal** — the system returns "I could not find this in the
      documents" on every not-found question (target: 0% hallucination).
- [ ] **M1-13 — Record the go/no-go decision.** PASS = citations are accurate and refusal holds →
      eligible to proceed to Milestone 2. FAIL = tune corpus/config and re-run; do not build custom
      code.

## Out of scope for Milestone 1 (do NOT start)

- Custom FastAPI + LlamaIndex pipeline, Qdrant/LanceDB, Docling, OCR routing, reranker, mechanical
  span-level citation verification. (Milestones 2–3.)
- Production hardware purchase or provisioning. (Milestones 4–5.)
- Any real attorney/client documents. (Milestone 6, onsite, after written approval.)
