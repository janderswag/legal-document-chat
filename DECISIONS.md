# DECISIONS.md — Decisions already made

> Locked decisions carried over from `CE_PLAN.md` (finalized 2026-06-19, revised against the
> Manus AI Technical Validation Report). Section references point back into `CE_PLAN.md`.
> Changing any of these requires an explicit, recorded re-decision.

## Scope and safety

- **D-1 — Product is a cited-retrieval assistant, not an AI lawyer and not an autonomous agent.**
  Grounded search/summarize over the attorney's own docs; no advice, no actions. (CE_PLAN §1, §3)
- **D-2 — Retrieval is architecturally separated from action-taking.** The answering agent has no
  action tools and no network egress in v1. (CE_PLAN §3 principle #12)
- **D-3 — Dev uses fake/sanitized/public documents only;** real data is touched only at Milestone 6,
  onsite, on attorney-owned hardware, after written approval. (CE_PLAN §4 rule 1, §14)
- **D-4 — Local-only data-flow invariant.** No document bytes, embeddings, prompts, or answers leave
  the machine in confidential mode. Loopback binding only; no public port exposure. (CE_PLAN §4)
- **D-5 — Human verification is mandatory, not optional.** Every answer carries a citation and the
  "verify against source / not legal advice" footer. (CE_PLAN §10, §15)
- **D-28 — Synthetic pilot source documents live under ignored `documents/` paths; tracked `eval/`
  files may contain schemas, templates, and metadata but not document bodies.** Every document-like
  file — even synthetic/fake/sanitized pilot documents — lives under the git-ignored `documents/`
  tree (use `documents/synthetic_corpus/`), preserving the invariant that **document data is never
  committable by default**. The `eval/` tree is tracked and holds only the manifest schema,
  templates, and ground-truth metadata (`fact_id`, page, section, short `verbatim_span` snippets
  drawn from synthetic docs only, expected-absent topics, notes) — never a full source-document
  body and never any real client text. This supersedes the working-tree proposal to author the
  corpus under an unignored `corpus/` path, which would have made synthetic documents committable by
  default. (CE_PLAN §4 rule 1, §7.1; `.gitignore`)

## Sequencing

- **D-6 — Turnkey pilot first, before any custom code or capex.** Milestone 1 (Ollama +
  AnythingLLM) must prove citation accuracy and not-found refusal as the go/no-go gate. (CE_PLAN §14,
  §17 Task 0)
- **D-7 — Custom citation-grade build is deferred to Milestones 2–3,** only after M1 passes.
  (CE_PLAN §14)

## M1 measurement decisions (turnkey pilot)

- **D-29 — M1 citation accuracy is scored at FILENAME level, not page level (turnkey limitation;
  owner-approved 2026-06-19).** Empirically (M1-7c), AnythingLLM 1.14.1's desktop PDF parser flattens
  every page into one blob and emits **empty chunk metadata (no page field)** — so verifiable
  page-level citation is **mechanically impossible on the turnkey stack**, even from page-faithful
  PDFs (page breaks confirmed correct; parser is the bottleneck). Therefore M1 measures what the
  turnkey stack can prove: **answer-correctness + filename grounding + DRM right-doc/right-matter +
  not-found refusal.** `page_match` and exact-`verbatim_span` overlap are **dropped from mechanical
  M1 scoring** (page/section remain informational / optional human-read). **The product page-level bar
  is NOT lowered** — verifiable **page + mechanical span** citation is reassigned to **M2-3** (Docling
  page metadata + mechanical span verification), which is exactly where CE_PLAN already places the
  mechanical overlap check. So the M1 page-level miss is a **go/no-go input** (turnkey insufficient for
  the citation bar → the M2-3 custom build is justified), not a silent pass. Encoded in
  `eval/TEST_PLAN.md` §3.1/§4. (CE_PLAN §2 "filename + page/section … mechanically overlaps", §14,
  D-7, D-19)
- **D-30 — M1 not-found refusal is scored on substance, not exact wording (owner-approved).** The
  refusal safety gate passes when the system **declines + cites nothing**; the exact CE_PLAN §10 / D-5
  sentence ("I could not find this in the documents.") is **pinned as the product string** via the
  `m1-golden` workspace prompt and tracked as a separate UX flag `refusal_wording_exact` — a fixable
  UX check, never scored as a hallucination. **Refinement (owner-approved 2026-06-20):** the gate is
  scoped to the **absent topic** — NF passes iff it asserts no substantive answer to the *asked,
  absent* thing AND cites nothing *for it*; an accurate quote about a **different, real** clause is
  **logged as a quality note, not failed**. Because query mode **always** returns a `sources[]` array
  (retrieved chunks) even on refusals, scoring uses the citation the **answer asserts**, not raw
  `sources[]`. Encoded in `eval/TEST_PLAN.md` §3.2. (CE_PLAN §10, D-5)
- **D-31 — M1-10 air-gap (SC-6) is verified by egress monitoring, not physical disconnect
  (owner-approved 2026-06-20).** The full M1-10 run executes with networking **on** while a monitor
  (`lsof`/`nettop`/pktap) runs throughout and proves **zero non-loopback / zero document-bearing
  egress** — exactly CE_PLAN §2 SC-6's "network monitor confirms zero outbound carrying document
  content." Rationale: an AI-driven run needs the network, the corpus is synthetic, and monitoring is
  the CE_PLAN-specified proof. **Supersedes the earlier M1-EH "networking OFF" framing for M1-10
  only;** physical NIC-off air-gap remains the standard for **M6 real-data** work. (CE_PLAN §2 SC-6,
  §11)

## Stack — pilot (Milestone 1)

- **D-8 — Model runtime: Ollama** (pilot and production). OpenAI-compatible local API, Metal
  acceleration, serves both chat and embedding models. (CE_PLAN §6.1)
- **D-9 — Pilot UI: AnythingLLM.** Chosen over Open WebUI for lowest hallucination (6%) and the best
  out-of-the-box filename + page citations in the May 2026 benchmark. (CE_PLAN §6.2, §16 Q3)
- **D-10 — Chat model: `qwen3:14b`** (alt: Mistral Small 3.1 24B). Disciplined grounded RAG that
  degrades gracefully when evidence is missing. (CE_PLAN §6/§12, §16)
- **D-11 — Embedding model: `bge-m3` via Ollama,** chosen for native hybrid dense + sparse support;
  to be validated against our own legal golden set (not MTEB rank) before locking. Pin the id; a
  change forces a full re-index. (CE_PLAN §6.5)
- **D-12 — Pilot deployment: native macOS apps, no Docker.** (CE_PLAN §6.8)

## Stack — production (deferred, recorded for context; do NOT build in M1)

- **D-13 — Orchestration: FastAPI (HTTP surface) + LlamaIndex (RAG).** (CE_PLAN §6.6)
- **D-14 — Vector DB: Qdrant** (best metadata filtering for matter scoping); LanceDB is the
  embedded server-less alternative. (CE_PLAN §6.4)
- **D-15 — Parsing/OCR: Docling + PyMuPDF, Tesseract fallback.** PyMuPDF routes text-vs-image; born-
  digital via PyMuPDF normalized through Docling; image-only via Tesseract. (CE_PLAN §6.3)
- **D-16 — Reranker: `bge-reranker-v2-m3`,** planned (not "only if measured"). (CE_PLAN §10)
- **D-17 — Storage: lifecycle folders** (`inbox`/`processed`/`failed`/`originals`) + SQLite metadata
  catalog mirrored into vector payloads; originals read-only. (CE_PLAN §6.7, §7)
- **D-18 — Anti-DRM: metadata-filter-before-similarity + Summary-Augmented Chunking (SAC).** Prevents
  "right clause, wrong client" retrieval. (CE_PLAN §9, §10)
- **D-19 — Mechanical span-level citation verification in code.** A cited span must mechanically
  overlap an actually-retrieved chunk's offsets, or the claim is rejected before display. The prompt
  alone is not trusted. (CE_PLAN §10)
- **D-20 — Production deployment: Docker Compose** (Qdrant + FastAPI/LlamaIndex + thin UI), Ollama on
  host. Qdrant drops out if LanceDB is chosen. (CE_PLAN §6.8, §13)

## Hardware

- **D-21 — Pilot runs on the in-hand MacBook Pro 14" M4 Pro, 24GB unified.** No production hardware
  purchase until SC-1..SC-7 pass and the attorney has seen the demo. (CE_PLAN §12)
- **D-22 — Production target (recommended): Mac Studio M4 Max, 64–128GB unified** (Option A
  appliance); CUDA path (RTX 5070 Ti/5080/5090) only if latency/scale demands it. Do not buy on spec.
  (CE_PLAN §12)

## Resolved project questions (CE_PLAN §16)

- **D-23 — Single solo attorney, single-tenant v1.** Multi-user is a later concern.
- **D-24 — PDF first (born-digital and scanned), then DOCX, then TXT.** Scanned PDFs are first-class.
- **D-25 — No remote access in v1** (local/air-gapped); Tailscale only revisited later with written
  approval.
- **D-26 — First production corpus: a few thousand documents** (drives the 14B–32B / 16–32GB sweet
  spot; 70B unnecessary).
- **D-27 — Support model: ongoing managed** (Jake owns updates/backups/model refreshes on a defined
  cadence). Exact cadence + response SLA still to pin down with the attorney.

## Still open / to confirm

- **O-1 — `bge-m3` vs `qwen3-embedding`** final choice pending evaluation against the legal golden
  set. (CE_PLAN §6.5) — relevant from Milestone 2 onward.
- **O-2 — Support cadence + response-time SLA** numbers, to confirm with the attorney. (CE_PLAN §16
  Q10)
