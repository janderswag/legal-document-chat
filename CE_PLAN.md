# CE_PLAN.md

> Engineering plan for a **private, local-first document intelligence system** for a solo attorney.
> Status: **PLANNING ONLY.** No application code, no repo scaffold, no package installs until this plan is approved.
> Audience: another engineer should be able to pick this up and build from it.

---

## 1. Executive Summary

We are building a **private, onsite document intelligence assistant** for an attorney. It lets the attorney search, retrieve, summarize, and ask plain-English questions across **their own** documents (contracts, filings, correspondence, scanned exhibits, etc.) and get back answers that are **grounded in and cited to the source documents**.

In plain English: it is a **smart, private search-and-summarize tool over the attorney's own files**. Think "a librarian who has read every document in the office and always tells you which page they got the answer from" — not "a lawyer," and not an autonomous agent.

What it is **not**:

- It is **not an AI lawyer** and gives **no legal advice or legal conclusions**.
- It is **not an autonomous agent** — it does not act, send, file, or change anything in the outside world.
- It is **not a cloud service** for confidential documents — real client documents stay on hardware the attorney owns and controls.

The attorney remains the professional of record and is **responsible for verifying every answer** against the cited source before relying on it. The system is designed to make that verification easy by always showing its sources.

**Two-environment reality (important):**

- **Development environment (my machine):** Build and validate the entire system using **only fake, public, or sanitized documents**. No real attorney/client data, ever, unless explicitly approved in writing.
- **Production environment (attorney's onsite workstation):** Purchased separately by the attorney **after** validation. Real documents are ingested **locally there only**.

The whole system is designed to be **boring, safe, and useful**: deterministic structure, local-only data flow, citations on every claim, and an explicit "I couldn't find this" when the documents don't support an answer.

---

## 2. Success Criteria

The first pilot is "working" when **all** of the following are demonstrably true on my development machine, using a fake/sanitized test corpus:

| # | Criterion | How we prove it |
|---|-----------|-----------------|
| SC-1 | **Ingest a small test corpus** | 20–50 fake documents (PDF, DOCX, TXT, scanned PDF) ingest end-to-end with a per-file pass/fail report. |
| SC-2 | **OCR scanned PDFs** | At least 5 image-only/scanned PDFs produce searchable text; verified against known content. |
| SC-3 | **Answer questions with citations** | Known-answer questions return correct answers, each factual claim carrying a citation (file + page + section/chunk). |
| SC-4 | **Refuse unsupported answers** | "Not found" questions reliably return "I could not find this in the documents" instead of a fabricated answer. |
| SC-5 | **Show source documents/pages** | The UI/output exposes the retrieved source snippets and lets the attorney open the original document at the cited page. |
| SC-6 | **Run fully locally** | With the network monitor on, a full ingest + query cycle makes **zero outbound calls** carrying document content. |
| SC-7 | **Redeployable onsite** | The system can be torn down and stood back up from scripts + config on a clean machine, with documented steps. |

**Pilot is GO for attorney demo only when SC-1 through SC-7 all pass.**

Quantitative targets for the pilot — **tightened to match the validation report's acceptance checklist** (see §11). These are stricter than typical RAG because the domain is legal and a wrong citation is a malpractice risk:

- **Citation fidelity: 100%** of factual claims carry a specific filename + page/section citation whose cited span **mechanically overlaps** the retrieved evidence (no claim ships uncited).
- **Refusal discipline: 0% hallucination on "not found" questions** — when the evidence isn't in the corpus, the system must refuse, every time.
- **Citation accuracy:** ≥ 95% of citations verifiably support their claim on the golden eval set (target: parity with the best-in-class commercial tools' *floor*, knowing Stanford measured 17–33% hallucination even in Lexis/Westlaw-class tools — RAG reduces but never eliminates this, so the human-verification workflow is mandatory, not optional).
- **DRM resilience:** the system distinguishes identical boilerplate clauses across different contracts via metadata filtering (no "right clause, wrong client" errors).
- **Latency:** **< 3s to first token**; **no OOM** processing a **32K context window** on pilot hardware.
- **Air-gap:** Wireshark (or equivalent) confirms **zero outbound transmission** during retrieval and inference.

---

## 3. Non-Goals and Safety Boundaries

The v1 system **must not** do any of the following. These are hard boundaries, not backlog items.

- **No autonomous legal action.** It never takes actions on the attorney's behalf.
- **No email sending.** No SMTP, no mail API, no drafting-and-sending.
- **No court filing.** No e-filing integrations, no document submission.
- **No client communication.** It never contacts clients or third parties.
- **No modifying or deleting legal documents.** Originals are read-only; the system only ever reads them and writes to its own derived stores.
- **No external tool use while in confidential-document mode.** The retrieval/answering agent has access to the vector store and the local LLM — and nothing else. No web browsing, no shell, no file-write tools, no MCP action tools.
- **No unsourced legal conclusions.** Every factual claim must trace to a retrieved chunk. No answer = say so.
- **No legal advice.** The assistant summarizes and locates; it does not advise, predict outcomes, or recommend legal strategy.
- **No real client data in development.** Development uses fake/sanitized/public documents exclusively.
- **No hidden cloud processing for confidential documents.** All inference, embedding, OCR, and storage for real documents happen on local hardware.

**Architectural enforcement of the boundary (key principle #12):** the component that can *read confidential documents* and the component that can *take actions or reach the outside world* are **never the same agent**. In v1 the answering agent simply has no action tools at all, which makes the boundary trivial to enforce and audit.

---

## 4. Threat Model and Privacy Rules

**Who/what we are protecting against:** accidental leakage of privileged client material to third parties or cloud services; local compromise of the workstation; and the attorney over-trusting an unverified answer. We are **not** defending against a nation-state adversary; we are building reasonable, defensible privacy hygiene for a law office.

### Privacy / handling rules (non-negotiable)

1. **Dev uses fake/sanitized/public documents only.** Real attorney/client documents are never processed on my machine without **written** approval.
2. **Production documents stay on attorney-owned hardware.** No syncing of confidential documents off the production box.
3. **Secrets are never committed.** `.env` is git-ignored; only `.env.example` (with placeholder values) is committed. No API keys are required for the local-only path anyway.
4. **Local ports are not exposed publicly.** Services bind to `127.0.0.1` (loopback) by default, never `0.0.0.0`, unless a deliberate LAN-access decision is made and firewalled.
5. **Remote access requires explicit written approval** and, if approved, is done via Tailscale (WireGuard, private tailnet) — never a raw port-forward or public tunnel. See §6 deployment.
6. **Document retrieval is separated from action-taking tools.** (See §3.) The confidential-mode agent has no egress and no action tools.

### Workstation hardening recommendations (for the production onsite machine)

- **Full-disk encryption** enabled (FileVault on macOS / BitLocker on Windows / LUKS on Linux). This is the single most important control if the machine is lost or stolen.
- **Strong account password**, screen auto-lock, no auto-login. Separate admin vs. daily-use accounts where practical.
- **Host firewall ON**, default-deny inbound. Only loopback (and, if approved, the Tailscale interface) reaches the app.
- **Local network restrictions:** the app is reachable only from the local machine (or the private tailnet if remote access is approved). No public DNS, no public IP exposure.
- **Encrypted local backups** with a documented, tested restore (see §13). Backups are themselves confidential material — encrypt them and store the key separately.
- **OS auto-updates** for security patches; keep the LLM runtime and dependencies patched on a documented cadence.
- **Physical security:** the workstation lives in the office, not a laptop bag. Lock the screen when away.

### Data-flow privacy invariant

> In confidential mode, **no document bytes, embeddings, prompts, or generated answers leave the local machine.** Any feature that would violate this invariant is out of scope for v1 and requires explicit re-approval.

---

## 5. Architecture Overview

```
                         ATTORNEY-OWNED, LOCAL-ONLY BOUNDARY
  ┌──────────────────────────────────────────────────────────────────────────┐
  │                                                                            │
  │   Documents                                                                │
  │   (PDF / DOCX / TXT / scanned PDF)                                         │
  │        │                                                                   │
  │        ▼                                                                   │
  │   /documents/inbox  ──► [1] Ingestion Watcher / Scanner                    │
  │        │                                                                   │
  │        ▼                                                                   │
  │   [2] File-type detect ──► [3] Parser / OCR ──► [4] Normalize to md/text   │
  │        (PDF text vs.        (PyMuPDF text |        (clean markdown,         │
  │         image-only)          OCRmyPDF+Tesseract     page boundaries kept)  │
  │                              for scans)                                    │
  │        │                                                                   │
  │        ▼                                                                   │
  │   [5] Metadata extraction ──► [6] Chunking ──► [7] Embeddings (local)      │
  │        (filename, matter,       (section/page-     (bge-m3 via Ollama;     │
  │         page, type, dates)       aware + SAC        dense + sparse/BM25)   │
  │                                  doc summary)                              │
  │        │                                                                   │
  │        ▼                                                                   │
  │   [8] Vector DB (Qdrant, local)   ◄───────────────┐                        │
  │        ▲   (metadata filter FIRST:                │                        │
  │        │    matter/client/date → anti-DRM)         │                        │
  │        │ hybrid retrieve top-k → cross-encoder rerank (bge-reranker-v2-m3) │
  │   [9] Retrieval ──────────────────────────────────┘                        │
  │        │                                                                   │
  │        ▼                                                                   │
  │   [10] Local LLM (Qwen3 14B via Ollama) ── grounded, cited answer ──►      │
  │         (answering agent: NO web, NO tools, context only;                  │
  │          citation spans must mechanically overlap retrieved evidence)      │
  │        │                                                                   │
  │        ▼                                                                   │
  │   [11] Cited answer  ──►  [12] ATTORNEY REVIEW & VERIFICATION              │
  │         (claim + file + page + snippet)     (human in the loop, always)    │
  │                                                                            │
  │   Side stores:  /documents/processed  /documents/failed                    │
  │                 /documents/originals (read-only)  /indexes  /logs          │
  │                                                                            │
  └──────────────────────────────────────────────────────────────────────────┘
        No outbound network for document content. Backups → /backups (encrypted).
```

**Reading the diagram:** documents land in an inbox, get parsed/OCR'd into clean text with page boundaries preserved, get metadata + chunked + embedded, and are stored in a local vector DB. At query time we retrieve the most relevant chunks and hand **only those** to a local LLM that is instructed to answer **only** from that context and cite it. The attorney verifies against the cited source. Nothing leaves the box.

---

## 6. Component Decisions

For each component: options considered, the **recommended default for the pilot**, and why.

> **Note (post-validation):** the recommendations below now reflect a **two-stack reality** from the validation report — a **turnkey Pilot stack** (prove citation accuracy fast, no custom code) and a **citation-grade Production stack** (custom orchestration that mechanically enforces citations and mitigates DRM). Where they differ, both are given.

### 6.1 Model runtime (local LLM inference)
- **Options:** Ollama · LM Studio · llama.cpp (raw) · vLLM.
- **Recommended: Ollama** (pilot **and** production). One-line model pulls, OpenAI-compatible HTTP API, native Metal acceleration on Apple Silicon, and serves **both** chat and embedding models. Lowest operational friction for a single-box pilot and trivial to script for redeployment. vLLM is reserved for the CUDA multi-user path only (out of scope for a solo attorney); LM Studio is GUI-first and less scriptable; raw llama.cpp is more wiring than we need.

### 6.2 Chat / front-end interface
- **Options:** AnythingLLM · Open WebUI · RAGFlow · custom chat UI.
- **Recommended (Pilot): AnythingLLM.** The validation report's May 2026 5,000-page benchmark gave AnythingLLM the **lowest hallucination rate (6%)** and the best out-of-the-box citations — filename + page, clickable inline — and explicitly flagged **Open WebUI's citation shortcomings**. For a turnkey pilot that proves citation accuracy on existing hardware without writing code, AnythingLLM + Ollama is the fastest credible path. *(This replaces the earlier Open WebUI recommendation.)*
- **Recommended (Production): a simple custom chat UI wired to our own LlamaIndex Python API.** AnythingLLM's built-in RAG can't enforce mechanical span-level citation verification or Summary-Augmented Chunking, so the citation-grade build moves retrieval into code we own (§6.6/§10) and keeps the front-end thin. RAGFlow is powerful but heavy/opinionated.

### 6.3 OCR / parser
- **Options:** Docling · PyMuPDF · OCRmyPDF/Tesseract · unstructured · marker · RAGFlow DeepDoc.
- **Recommended: Docling + PyMuPDF, with Tesseract as the scanned-page fallback.** Per the validation report, **Docling (IBM)** gives superior structure-preserving parsing (**97.9% complex-table accuracy**) and outputs unified markdown that retains document hierarchy — which is exactly what legal section/clause structure needs. Decision rule per file: **PyMuPDF routes** (does the page have a real text layer?); born-digital text → PyMuPDF, normalized through **Docling** for structure; image-only pages → **Tesseract OCR**, then Docling. All local, free, battle-tested.

### 6.4 Vector database
- **Options:** Qdrant · LanceDB · Chroma · Postgres pgvector.
- **Recommended: Qdrant** (confirmed by the report — best-in-class metadata filtering, essential for matter/client/date scoping and the anti-DRM filter-before-similarity step). **LanceDB** is the noted alternative: an **embedded, server-less** store that removes the Qdrant container and simplifies onsite deployment — a reasonable swap if we want zero moving parts on the attorney's box. Chroma is weaker on filtering; pgvector only makes sense if we already run Postgres (we don't).

### 6.5 Embedding model (local)
- **Options:** `bge-m3` · `qwen3-embedding` · `nomic-embed-text` · `jina-embeddings`.
- **Recommended: `bge-m3` via Ollama** — and **do not pick on MTEB rank.** The report is explicit: general MTEB leaders don't predict *legal* retrieval (per the Massive Legal Embedding Benchmark), so we **evaluate `bge-m3` vs `qwen3-embedding` against our own legal golden set** (§11) before locking it. `bge-m3` is the default because it **supports hybrid dense + sparse retrieval out of the box**, which is crucial for capturing legal terms of art. *(This replaces `nomic-embed-text`.)* **Pin the chosen model** — changing it forces a full re-index, so the id is recorded in config and in every chunk's metadata.

### 6.6 Backend app / orchestration
- **Options:** FastAPI + LlamaIndex · FastAPI alone · Node/Next.js.
- **Recommended: Python — FastAPI for the HTTP surface + LlamaIndex for RAG orchestration.** The report names **LlamaIndex** as the superior framework for a controllable, citation-grade build (hierarchical chunking, hybrid retrieval, response synthesis). FastAPI exposes `/ingest` and `/query`; LlamaIndex owns chunking/SAC, hybrid retrieval, reranking, and the mechanical citation-overlap check. The whole parsing/embedding/vector ecosystem is Python-native, so no cross-language glue. *(Pilot uses AnythingLLM's built-in pipeline instead; this custom layer is the Production build.)*

### 6.7 Storage layout
- **Options:** flat folders · structured folders by lifecycle · DB-managed blobs.
- **Recommended: structured folders by lifecycle** (`inbox`/`processed`/`failed`/`originals`) **plus** a small **metadata catalog** (SQLite in `/indexes`) as the source of truth for document/chunk metadata, mirrored into Qdrant payloads. SQLite is local, zero-ops, transactional, and easy to back up/restore. Originals are kept read-only and never mutated. (Full layout in §7.)

### 6.8 Deployment method
- **Options:** bare-metal/manual · Docker Compose · packaged installer.
- **Pilot:** install **Ollama + AnythingLLM directly on the Mac** (both ship native macOS apps) — no Docker needed to prove the concept fast.
- **Production — Docker Compose** for Qdrant + the FastAPI/LlamaIndex backend + the thin chat UI, with **Ollama on the host** (best Metal access and model-cache reuse; containerized GPU/Metal passthrough is fiddly). One `docker compose up` plus a documented `ollama pull`. If we adopt **LanceDB** (§6.4), the Qdrant container drops out entirely. This is the portable "build once, redeploy onsite" story. (Details in §13.)

---

## 7. Data Model and Folder Structure

### 7.1 Local folder structure

```
/srv/docintel/                 # project root on the workstation
├── documents/
│   ├── inbox/                 # drop zone: new files to ingest
│   ├── processed/             # successfully ingested (moved here after success)
│   ├── failed/                # failed ingestion + a sibling .error.txt explaining why
│   └── originals/             # immutable, read-only copy of every ingested source
├── indexes/                   # SQLite metadata catalog + Qdrant snapshot/persistence
├── backups/                   # encrypted backups (catalog + vector store + originals manifest)
├── logs/                      # structured processing + query logs (JSONL)
├── config/                    # config.yaml, prompt templates, .env (git-ignored)
└── (code lives in the repo, mounted/deployed separately from data above)
```

**Lifecycle rule:** a file enters `inbox/`, a copy of the untouched source is written to `originals/` (read-only), and on success the inbox file moves to `processed/`; on failure it moves to `failed/` with an adjacent `<name>.error.txt`. `originals/` is the canonical source-of-truth for "open the cited document."

### 7.2 Document & chunk metadata fields

Stored in the SQLite catalog and mirrored into each Qdrant point's payload so retrieval can filter and citations are self-contained.

| Field | Level | Description |
|-------|-------|-------------|
| `document_id` | document | Stable unique id (UUID or hash-derived). |
| `original_filename` | document | The file's original name as dropped in `inbox/`. |
| `matter_or_client` | document | Matter/client association (from folder convention or a sidecar manifest; see note). |
| `document_type` | document | e.g. contract, pleading, correspondence, exhibit, memo (best-effort classification + override). |
| `source_path` | document | Path to the immutable copy in `originals/`. |
| `page_number` | chunk | Page the chunk came from (range if a chunk spans pages). |
| `section_heading` | chunk | Nearest heading/section breadcrumb for the chunk. |
| `chunk_id` | chunk | Stable unique id for the chunk (`document_id` + ordinal). |
| `created_at` | document | When the source file was first seen/ingested. |
| `indexed_at` | chunk | When this chunk was embedded/stored. |
| `checksum_sha256` | document | Hash of the original bytes — dedupe + integrity + change detection. |
| `ocr_status` | document | `none` (born-digital), `ocr_applied`, or `ocr_failed`. |
| `embedding_model` | chunk | Embedding model id used (so re-index decisions are unambiguous). |
| `retrieval_score` | runtime | Similarity/rerank score attached to a chunk **at query time** (not stored; part of the answer payload). |

**Note on `matter_or_client`:** for the pilot, derive it from a top-level folder convention inside `inbox/` (e.g. `inbox/<MatterName>/...`) and/or an optional `manifest.csv`. We do **not** infer client identity from document contents with the LLM in v1 — that would be an unsourced, error-prone classification on privileged material.

---

## 8. Ingestion Pipeline

Each file moves through these stages. The pipeline is **idempotent** (re-dropping the same file is detected by checksum) and **fail-loud** (a failure quarantines one file without halting the batch).

1. **Watch / scan the input folder.** Watch `inbox/` (filesystem watcher) with a periodic full-scan fallback. New/changed files (by checksum) are enqueued.
2. **Identify file type.** By extension + magic bytes: PDF (born-digital vs. image-only), DOCX, TXT/MD. Unknown types → `failed/`.
3. **Extract text or run OCR.** PDFs: try PyMuPDF text extraction; if a page has no/negligible text layer, route that document (or page) to OCRmyPDF/Tesseract. DOCX: extract via a DOCX parser. TXT/MD: read directly.
4. **Convert to markdown/text.** Normalize to clean markdown via docling (or a lighter normalizer), preserving headings and list structure.
5. **Preserve page boundaries.** Tag text with explicit page markers so every downstream chunk knows its source page(s). This is mandatory — citations depend on it.
6. **Extract metadata.** Compute checksum, derive `matter_or_client` from folder/manifest, set `document_type` (best-effort + overridable), timestamps, OCR status.
7. **Chunk text.** Section/page-aware chunking (see §9).
8. **Generate embeddings.** Embed each chunk with the pinned local embedding model via Ollama.
9. **Store in the vector DB.** Upsert points into Qdrant with full metadata payloads; write/update the SQLite catalog in the same logical transaction.
10. **Store processing logs.** Append a structured JSONL record per file (stages, timings, page counts, OCR decision, success/failure).
11. **Report failures.** Move failed files to `failed/` with a human-readable `.error.txt`; surface a per-batch summary (N succeeded / M failed, with reasons).

### Expected failure modes and handling

| Failure mode | Handling |
|--------------|----------|
| **Encrypted/password-protected PDF** | Quarantine to `failed/` with a clear message; do not attempt to crack. Attorney supplies an unlocked copy. |
| **Image-only PDF with no text layer** | Detected at step 3 → OCR path. If OCR confidence is very low, mark `ocr_failed` and flag for human review (don't silently index garbage). |
| **Corrupt / truncated file** | Caught at parse; quarantine with error detail. |
| **Unsupported type** (e.g. raw image, spreadsheet) | Quarantine; note as out-of-scope for v1 (revisit later). |
| **Duplicate file** (same checksum) | Skip ingest, log as duplicate; no double-indexing. |
| **Mixed digital+scanned pages** | Per-page routing: text-layer pages via PyMuPDF, image pages via OCR; reassemble in page order. |
| **OCR produces gibberish** | Confidence threshold + spot heuristics; below threshold → flag, don't index as authoritative. |
| **Embedding/DB write fails midway** | Transactional upsert; on failure the file is treated as not-indexed and retried, never left half-indexed. |
| **Huge file / memory pressure** | Stream/page-wise processing; cap and chunk by page to bound memory. |

---

## 9. Chunking Strategy

Legal documents reward structure-aware chunking. The strategy:

- **Respect headings and sections.** Split on document structure first (sections, articles, numbered clauses, headings) rather than blindly on token count. A clause should stay intact where possible.
- **Preserve page numbers.** Every chunk records the page(s) it came from. Non-negotiable — it's the backbone of citations.
- **Include breadcrumb metadata.** Each chunk carries its `section_heading`/path (e.g. "Agreement › Section 4 › 4.2 Indemnification") so the model and the citation both have context.
- **Avoid too-tiny and too-massive chunks.** Target a sensible window (starting point: ~**500–800 tokens** per chunk with ~**10–15% overlap**), tuned during eval. Merge runt fragments; split oversized sections at sub-headings or sentence boundaries.
- **Include neighboring context where useful.** Small overlap between adjacent chunks, plus the ability to fetch the **previous/next chunk** of a retrieved hit at answer time so a clause split across a boundary isn't truncated.
- **Summary-Augmented Chunking (SAC) — anti-DRM.** Prepend a short **document-level synthetic summary** (and the matter/client breadcrumb) to each chunk before embedding. The validation report identifies this as a proven mitigation for **Document-Level Retrieval Mismatch** — the catastrophic "right boilerplate clause, wrong client's contract" failure that plagues redundant legal corpora. The summary injects global context so identical clauses in different matters no longer collide in vector space.
- **Support exact-quote retrieval with hard offsets.** Keep chunk text close to verbatim (don't paraphrase or re-flow) and **store character/line offsets** for every chunk. These offsets are not optional polish — they are the anchor for **mechanical citation verification** in §10 (a cited span must overlap a retrieved chunk's offsets, or the claim is rejected).

### How chunking is tested

- **Boundary fidelity:** assert no chunk loses its page/section metadata; spot-check that section boundaries land on real headings.
- **Quote round-trip:** take known sentences from source docs, confirm the containing chunk reproduces them verbatim and that page/section metadata is correct.
- **Split-clause test:** craft a clause that spans a page break; confirm retrieval + neighbor-fetch returns the whole clause.
- **DRM stress test:** put the **same boilerplate clause in two different matters'** documents, then ask a matter-scoped question. Confirm SAC + metadata filtering returns the clause from the **correct** matter every time (zero cross-matter pulls).
- **Offset integrity:** confirm every chunk's stored character/line offsets resolve back to the exact source span (the substrate for §10's mechanical citation check).
- **Size distribution:** chart chunk-size histogram; flag a long tail of tiny/huge chunks for tuning.
- **Retrieval sensitivity:** run the eval Q&A set under a couple of chunk sizes/overlaps and pick the config with the best citation accuracy (see §11). Chunking config is recorded so results are reproducible.

---

## 10. Retrieval and Answering Rules

### RAG behavior

- **Metadata filter FIRST, then similarity (anti-DRM).** When the query is matter-scoped, apply the `matter_or_client`/`document_type`/date filter **before** vector similarity so identical boilerplate from another client's contract can never enter the candidate set. This is the report's primary DRM mitigation alongside SAC.
- **Hybrid retrieval (dense + sparse/BM25).** Combine dense vector search with BM25 keyword search so specific legal terms of art (statute numbers, defined terms, party names) are caught — pure dense retrieval misses these. `bge-m3` supports both natively.
- **Cross-encoder rerank — planned, not optional.** Rerank the hybrid top-N with a local cross-encoder (`bge-reranker-v2-m3`). Promoted from the earlier "only if measured" stance because legal redundancy makes first-stage ranking unreliable; keep it in from Phase 3.
- **Answer only from provided context.** The model sees only the retrieved chunks and uses nothing else. No outside/world knowledge fills gaps.
- **Cite every factual claim** with **document name + page + section + chunk id + character/line span**.
- **If support is weak, refuse.** Below a retrieval-score floor, or when retrieved chunks don't actually address the question, return the explicit "I could not find this in the documents" — target **0% hallucination on not-found** (§2/§11).
- **Prefer verbatim quotes** for "what does it say about X" questions — snippet + citation, not paraphrase.
- **Never invent page numbers or document names.** Citations may only reference retrieved-chunk metadata.
- **Surface source strength.** Show a simple "Strong / Partial / Weak support" signal derived from retrieval/rerank scores and coverage so the attorney calibrates trust.

### Code-side guardrails (don't rely on the prompt alone)

> The validation report's central warning: **RAG is not hallucination-free** — Stanford measured 17–33% hallucination in commercial legal RAG, *including falsely asserting that a source supports a proposition.* The prompt alone cannot be trusted; these checks run in code.

- **Mechanical span-level citation verification (the key new guardrail).** The LLM must emit, for each claim, the specific character/line span it relied on. In code, that span **must mechanically overlap** the offsets of an actually-retrieved chunk. A claim whose cited span does **not** overlap retrieved evidence is **rejected/flagged before display** — this catches the "source doesn't actually support the proposition" failure that pure citation-presence checks miss.
- Validate every citation resolves to a chunk in the actual retrieved set; strip hallucinated citations.
- Enforce the "not found" score floor in code, not just via model judgment.
- Log the full retrieval set (with scores) + final answer for every query, locally, for audit.

### Default system prompt (local document assistant)

```
You are a private document assistant for an attorney. You help locate, summarize,
and quote information from the attorney's own documents. You are NOT a lawyer and
you do NOT give legal advice, legal opinions, predictions, or strategy.

RULES — follow exactly:

1. Answer ONLY using the provided <context> chunks. Do not use outside knowledge.
   If the answer is not in the context, respond exactly:
   "I could not find this in the documents."

2. Cite every factual statement. After each claim, include a citation in the form:
   [document: <original_filename>, page: <page_number>, section: <section_heading>,
    chunk: <chunk_id>, span: "<exact quoted text you relied on>"]
   The span MUST be copied verbatim from the provided context. Only cite documents,
   pages, sections, and chunk ids that appear in the provided context. Never invent or
   guess a citation, page number, document name, or span. (The system mechanically
   checks that your span overlaps the retrieved source; non-overlapping claims are
   rejected.)

3. When the user asks what a document says, prefer a direct verbatim quote from the
   context, in quotation marks, followed by its citation.

4. If the context only partially supports an answer, say what is supported, cite it,
   and clearly state what is missing. Do not fill gaps with assumptions.

5. Do not give legal advice or legal conclusions. You may summarize and locate what
   the documents say; you may not advise on what the attorney should do.

6. End every response with this reminder:
   "Verify against the cited source. This is not legal advice."

You have no access to the internet, email, file changes, or any external tools.
Your only inputs are the user's question and the provided document context.

<context>
{retrieved_chunks_with_metadata}
</context>

User question:
{user_question}
```

---

## 11. Evaluation Plan

Build a labeled eval set from **fake/sanitized legal-style documents** (synthetic contracts, sample pleadings, public-domain legal texts, fabricated correspondence). **20–50 documents** including several scanned/image-only PDFs.

### Test categories & pass/fail criteria

Golden set sizing follows the report's acceptance checklist: **50+ known-answer legal questions, each mapped to an exact known source page.**

| Test type | What it checks | Pass criterion |
|-----------|----------------|----------------|
| **Golden eval set (50+)** | Known-answer Q&A mapped to exact source page | Correct answer + correct page-level citation on the golden set. |
| **Scanned-PDF tests** | OCR → retrieval works on image docs | Questions answerable only from scanned docs succeed ≥ 85%. |
| **DRM / similar-document** | No "right clause, wrong client" pulls | Correct-matter source via metadata filter + SAC; **zero** cross-matter citation errors. |
| **"Not found" / refusal** | Refuses when the answer isn't present | **0% hallucination** — refuses every time the evidence is absent. |
| **Citation fidelity** | Every claim cites filename + page/section, span overlaps evidence | **100%** of factual claims carry a span-verified citation; **zero** invented filenames/pages. |
| **Performance** | Usable latency, no OOM | **< 3s to first token**; **no OOM on a 32K context window** on pilot hardware. |
| **Air-gap** | No data leaves the box | Wireshark confirms **zero** outbound traffic during retrieval + inference. |
| **User acceptance (attorney)** | Real-world usefulness & trust | Attorney rates ≥ 80% of demo answers "useful and correctly cited." |

### Method

- Store eval cases as `(document_set, question, expected_answer/expected_source, category)`.
- A harness runs all cases, scores automatically where possible (citation-in-retrieved-set, not-found detection, latency) and flags subjective ones for human grading.
- **Regression gate:** any prompt/chunking/model change re-runs the suite; ship a change only if it does not regress citation accuracy or the not-found rate beyond a small threshold. (Mirrors the "eval before prompt" discipline.)
- **The hallucination/fabricated-citation count is a hard zero.** A single invented citation in the eval is a blocking failure, not a percentage.

---

## 12. Hardware Assumptions

The **pilot runs on the confirmed dev machine — a MacBook Pro 14" (Nov 2024), Apple M4 Pro, 24GB unified, macOS Tahoe 26.5** — with quantized models and the fake test corpus. We do **not** buy production hardware until SC-1..SC-7 pass and the attorney has seen the demo. Goal: validate cheaply, then right-size to the **measured** workload — not the imagined one. **Important 2026 reality (from the report): the RTX 4080/4090 are discontinued; the 50-series (Blackwell) launched into a GDDR7 shortage that inflated prices** — so the CUDA tier below is re-specced to current parts.

| Tier | Use | Spec | Notes |
|------|-----|------|-------|
| **Pilot (in hand)** | Build/validate now | **MacBook Pro M4 Pro, 24GB unified** (~273 GB/s) | Comfortably runs a quantized **Qwen3 14B** (~9–10GB) + `bge-m3` + reranker + Qdrant + OCR on a small corpus. 24GB means pilot ≈ near-production capability; dev and prod share one Apple Silicon + Ollama + Metal story. |
| **Production — Option A (recommended): low-maintenance appliance** | Attorney's onsite box | **Mac Studio M4 Max, 64–128GB unified** (~546 GB/s, ~$3.5k–$5k) | Silent, low-power, zero Windows admin. Runs 14B comfortably; can even handle 70B at ~8–15 tok/s if ever needed. The report's recommended single-box appliance for a law office. |
| **Production — Option B: CUDA performance path** | If max tok/s or future multi-user (vLLM) | **RTX 5070 Ti / 5080 (16GB)** or **RTX 5090 (32GB)** + 64GB RAM + NVMe (~$5k–$8k) | 16GB cards handle 24B–32B at 4-bit; the 32GB 5090 gives headroom. Only if latency/scale demands it — adds Windows/Linux admin burden. |
| **Higher-end (only if justified)** | Larger corpus / bigger models | 48GB+ VRAM (or multi-GPU) / 128GB+ | Only if eval at the real corpus size proves Option A/B insufficient. **Do not buy on spec.** |

Sizing drivers: model size (quantized **14B–32B** is the local sweet spot per the report — a 70B model is unnecessary for a few-thousand-doc corpus and adds cost/latency), corpus size (drives index + RAM/disk), and latency targets. **Right-size after measuring on the real corpus during the demo phase.**

---

## 13. Deployment Plan

Goal: **build once locally, redeploy cleanly onto the attorney's machine** with minimal manual steps and no confidential data carried over from dev.

Artifacts to produce:

- **`docker-compose.yml`** (production) — Qdrant + the FastAPI/LlamaIndex backend + the thin chat UI. Ollama runs on the host (documented separately) for Metal access. *(Pilot needs no compose file — Ollama + AnythingLLM install as native macOS apps.)* If LanceDB is chosen (§6.4), Qdrant drops out.
- **`.env.example`** — every config knob with safe placeholder values; the real `.env` is git-ignored and created per-environment. No secrets in the repo.
- **`scripts/install.sh`** — preflight (check Docker, Ollama installed), create the `/documents/*`, `/indexes`, `/backups`, `/logs`, `/config` tree, pull models, bring up the stack. Idempotent.
- **`scripts/backup.sh`** — produce an **encrypted** archive of: SQLite catalog, Qdrant data/snapshot, and an `originals/` manifest (and optionally the originals themselves), into `/backups` with a timestamp. Documents the encryption method and where the key lives (not in the backup).
- **`scripts/restore.sh`** — restore from a chosen backup archive to a clean install; verifies integrity (checksums) and reports what was restored. **Restore must be tested, not assumed.**
- **Model download instructions** — exact `ollama pull` commands for the pinned models (chat: **`qwen3:14b`**, alt **Mistral Small 3.1 24B**; embedding: **`bge-m3`**; reranker: **`bge-reranker-v2-m3`**), with version/digest pinning so dev and prod match. Changing the embedding model = mandatory full re-index.
- **Admin guide** (`docs/ADMIN.md`) — install, start/stop, where data lives, how to back up/restore, how to add documents, how to update models, the privacy invariants, and the hardening checklist from §4.
- **User guide** (`docs/USER.md`) — for the attorney: how to drop documents in, how to ask questions, **how to read and verify citations**, what "I could not find this" means, and the standing reminder that answers must be verified and this is not legal advice.

**Portability principle:** everything that differs between dev and prod lives in `.env` + `config/`. The same compose file and scripts stand the system up on either machine. **No dev data is ever shipped to prod;** prod starts with an empty document store.

---

## 14. Milestones

Each milestone has deliverables and acceptance criteria. Real client data does not appear until Milestone 6, onsite. **Mapping to the validation report's roadmap:** M1 ≈ Phase 1 (turnkey pilot, weeks 1–3), M2–M3 ≈ Phase 3 (custom citation-grade layer, weeks 7–10), M4–M5 ≈ Phase 2/4 (procurement + rollout). The report front-loads a **turnkey pilot to prove citation accuracy before any capex** — M1 reflects that.

### Milestone 1 — Turnkey pilot, citation accuracy proven (fake docs)
- **Deliverables:** **Ollama + AnythingLLM** on the M4 Pro; **`qwen3:14b`** + **`bge-m3`** pulled; a small sanitized corpus loaded; a **golden eval set of 50+ legal-style questions mapped to known source pages**.
- **Acceptance:** the turnkey stack answers golden questions with correct **filename + page** citations and refuses on not-found. **This is the go/no-go gate before building any custom code or buying hardware** (per the report: "do not proceed until the system proves it can accurately retrieve and cite").

### Milestone 2 — Reliable ingestion / OCR / indexing (custom pipeline)
- **Deliverables:** full ingestion pipeline (§8) incl. **PyMuPDF routing → Docling structure → Tesseract OCR**, page-boundary preservation, metadata catalog, **SAC document summaries**, failure quarantine + logs.
- **Acceptance:** SC-1 and SC-2 pass on the 20–50 doc fake corpus (incl. scanned PDFs); failures are quarantined with reasons; re-ingest is idempotent.

### Milestone 3 — Citation-grade Q&A (custom LlamaIndex layer)
- **Deliverables:** **hybrid retrieval (dense + BM25) + `bge-reranker-v2-m3`**, **metadata-filter-before-similarity** (anti-DRM), the §10 system prompt, and **mechanical span-level citation verification** in code; "not found" path; source-strength signal.
- **Acceptance:** SC-3/4/5 pass; eval (§11) hits **100% citation fidelity, 0% not-found hallucination, DRM resilience**, **< 3s to first token, no 32K OOM**; zero fabricated citations.

### Milestone 4 — Attorney demo (sample docs)
- **Deliverables:** thin chat UI on the LlamaIndex API (or AnythingLLM for the earliest demo); user guide draft; demo script using **fake/sanitized** docs.
- **Acceptance:** attorney completes a guided session, citations open the right source pages, attorney UAT ≥ 80% useful-and-cited; **go/no-go on production hardware (Mac Studio M4 Max) recorded**.

### Milestone 5 — Production deployment on attorney hardware
- **Deliverables:** **Mac Studio M4 Max** provisioned + hardened (§4, FileVault + offline encrypted backups); compose stack + scripts deployed; backup/restore tested on the box; admin/user guides finalized.
- **Acceptance:** SC-6 + **Wireshark-confirmed zero outbound** verified on prod; SC-7 redeploy verified; restore drill succeeds; **still no real documents ingested.**

### Milestone 6 — Real document ingestion (onsite)
- **Deliverables:** **written approval** to process real documents; onsite ingestion of the first real corpus by the attorney/with supervision.
- **Acceptance:** real corpus ingests with an acceptable success rate; spot-checked citations are correct; privacy invariant holds (nothing leaves the box). First time real data is touched, only on attorney-owned hardware.

### Milestone 7 — Training, support, maintenance (**ongoing managed**)
- **Deliverables:** attorney training on the **mandatory verification workflow** (click every citation, verify source text before use); a documented **ongoing-managed support agreement** — Jake retains responsibility for updates, backups, model refreshes, with a defined cadence + response window; escalation path.
- **Acceptance:** attorney can independently add documents, run queries, verify citations, and trigger a backup; the ongoing-managed agreement (cadence + response SLA) is signed.

### Milestone 8 — Future automations (only after retrieval is stable)
- **Deliverables:** a vetted backlog of *additive, still-safe* enhancements (e.g. saved searches, matter dashboards, better rerankers) — **explicitly excluding** the §3 non-goals.
- **Acceptance:** retrieval quality has been stable in production for an agreed period; each proposed automation passes a safety/privacy review before any build. No action-taking/agentic features without a fresh, explicit decision.

---

## 15. Risks and Mitigations

| Risk | Type | Mitigation |
|------|------|------------|
| **Hallucinated answers** (RAG is *not* hallucination-free — Stanford: 17–33% even in commercial legal tools) | Technical/Legal | Answer-only-from-context prompt + **mechanical span-level citation verification** (cited span must overlap retrieved evidence) + score-floor "not found" path + eval gate with zero-fabrication rule. **Human verification is mandatory, not optional** — designed into the workflow. |
| **Document-Level Retrieval Mismatch (DRM)** — right clause, wrong client's contract | Technical/Legal | **Metadata filter before similarity** (matter/client/date) + **Summary-Augmented Chunking** + dedicated DRM stress test in the eval. This is a *catastrophic* legal failure mode, treated as first-class. |
| **Bad OCR** | Technical | PyMuPDF-vs-OCR routing, Docling structure, Tesseract fallback, confidence thresholds, flag-don't-index low-confidence output, scanned-PDF eval category. |
| **Wrong citations** | Technical | Span-overlap verification + validation against the actually-retrieved set; never synthesized; quote round-trip + offset-integrity tests. |
| **Embedding chosen on the wrong benchmark** (MTEB ≠ legal retrieval) | Technical | Evaluate `bge-m3` / `qwen3-embedding` against our **own legal golden set**, not public leaderboards; hybrid dense+BM25 for terms of art. |
| **Missing documents** (not retrieved) | Technical | Tune chunking/top-k/hybrid/rerank against eval; neighbor-fetch; surface "weak support" honestly rather than guessing. |
| **Permission / access issues** | Privacy | Loopback-only binding, host firewall, separate accounts, disk encryption; retrieval agent has no egress/tools. |
| **Hardware failure** | Operational | Tested encrypted backups + restore drill; originals retained; documented rebuild via install script. |
| **Scope creep** (toward an agent) | Business/Legal | §3 non-goals are hard boundaries; §8 milestone 8 requires explicit re-approval; no action tools in confidential mode. |
| **Attorney expects ChatGPT-level reasoning** | Business | Set expectations explicitly: this is grounded retrieval + summarization over *their* docs, not a general reasoning oracle; "not found" is a feature; demo with realistic examples. |
| **Privileged-data leakage** | Privacy/Legal | Dev uses fake data only; prod is local-only with the data-flow invariant; written approval gate before real data; no cloud calls for confidential content. |
| **Maintenance burden** | Business | Boring, well-documented stack; Docker Compose + scripts; admin guide; defined maintenance cadence/agreement; pin model + dependency versions. |
| **Model/index drift on upgrade** | Technical | Pin chat + embedding model digests; embedding-model id stored per chunk; changing embeddings = explicit full re-index. |
| **Over-trust of a single answer** | Legal | Source-strength signal + mandatory "verify against source / not legal advice" footer + attorney-in-the-loop by design. |

---

## 16. Questions Before Implementation

All ten are now resolved — seven from the **Technical Validation Report (Manus AI, June 19, 2026)**, and three (1, 2, 10) from Jake directly on 2026-06-19.

1. **OS / dev machine?** — **ANSWERED: macOS (Tahoe 26.5), MacBook Pro 14" Apple M4 Pro.** Apple Silicon, so dev and production share one runtime story (Ollama + Metal); production just scales up to a Mac Studio M4 Max.
2. **What hardware do you currently have?** — **ANSWERED: M4 Pro, 24GB unified memory** (~273 GB/s). Comfortably runs a quantized Qwen3 14B + bge-m3 + reranker for the pilot — close to production capability, so the pilot is representative, not a toy.
3. **First UI?** — **ANSWERED: AnythingLLM for the pilot** (not Open WebUI). In a May 2026 5,000-page benchmark, AnythingLLM had the **lowest hallucination rate (6%)** and the best out-of-the-box citations (filename + page, clickable inline); the report explicitly calls out Open WebUI's citation shortcomings. **Production UI:** a simple custom chat front-end wired to our own LlamaIndex Python API (so we control mechanical citation verification + DRM mitigation).
4. **Which document types first?** — **ANSWERED: PDF is the priority** (both born-digital and scanned), then DOCX and TXT. The report's entire parsing/OCR investment (PyMuPDF routing → Docling structure → Tesseract fallback) is built around PDFs.
5. **How important are scanned PDFs in v1?** — **ANSWERED: central / first-class.** The report bakes a full OCR pipeline into Phase 2 (PyMuPDF for routing, Docling for structure at 97.9% complex-table accuracy, Tesseract for fallback scans). Treat scanned-PDF support as core, not optional.
6. **Remote access?** — **ANSWERED: no — local/air-gapped for v1.** The acceptance checklist requires Wireshark-verified **zero outbound transmission** during inference and retrieval. Remote access (Tailscale) is out of scope for v1 and only revisited later with explicit written approval.
7. **How many users?** — **ANSWERED: single attorney in v1.** The report scopes to one attorney; multi-user (e.g. vLLM on the CUDA path) is named only as a later scaling option, not a v1 requirement.
8. **How many documents in the first production corpus?** — **ANSWERED: "a few thousand documents."** This is what drives the 14B–32B model / 16–32GB VRAM hardware sweet spot; a 70B model is explicitly called unnecessary for this corpus size.
9. **One attorney or a small firm?** — **ANSWERED: solo attorney** (the report's stated audience). Single-tenant build; firm-scale matter-scoping/access stays a v2 concern.
10. **Support/maintenance arrangement?** — **ANSWERED: ongoing managed.** Jake retains responsibility for the system — updates, backups, model refreshes — on a defined cadence with a response window. This is a recurring engagement (shapes Milestone 7; the cadence + SLA get written into the support agreement and admin guide). *Still to pin down with the attorney: exact cadence and response-time numbers.*

### What the research changed elsewhere in the plan (now applied throughout)

The following course-corrections from the validation report have been **folded into §2, §5, §6, §9, §10, §11, §12, §13, §14, §15, and §17** as of 2026-06-19. This list is the changelog/rationale:

- **RAG is not hallucination-free.** Stanford (Magesh et al., 2025) measured 17–33% hallucination in *commercial* legal RAG tools, including "falsely asserting a source supports a proposition." → Add **mechanical / span-level citation verification**: the LLM must emit text offsets/line ranges that must *mechanically overlap* the retrieved evidence, or the claim is rejected. (Strengthens §10's code-side guardrail from "citation is in the retrieved set" to "citation's span actually overlaps the evidence.")
- **Document-Level Retrieval Mismatch (DRM)** — the catastrophic "right clause, wrong client's contract" failure on redundant boilerplate. → Mitigate with **strict metadata filtering before vector similarity** (matter/client/date) **+ Summary-Augmented Chunking (SAC)** (prepend a document-level synthetic summary to each chunk for global context). Add DRM as a named risk in §15 and a named acceptance test.
- **Don't pick embeddings off MTEB.** General leaderboards don't predict legal retrieval (per MLEB). → **Evaluate `bge-m3` and `qwen3-embedding` against our own legal golden set**, and use **hybrid retrieval (dense + BM25 sparse)** for legal terms of art. Production default: **`bge-m3`** (native hybrid). This **replaces `nomic-embed-text`** from §6.5.
- **Add a cross-encoder reranker** (`bge-reranker-v2-m3`) over top-N — promoted from "only if measured" to a planned Phase 3 component.
- **LLM choice:** **Qwen3 14B (or 8B)**, alternately **Mistral Small 3.1 24B** — disciplined grounded RAG that degrades gracefully when evidence is missing. Replaces the generic "8B-class" placeholder in §6/§12.
- **Orchestration:** **LlamaIndex** for the production citation-grade build (hierarchical chunking + response synthesis). New component vs. the original FastAPI-only plan; FastAPI still serves the HTTP surface.
- **Vector DB:** confirms **Qdrant** (best metadata filtering for matter scoping); **LanceDB** noted as an embedded, server-less alternative to simplify deployment.
- **Chunking/OCR:** confirms and strengthens **Docling + PyMuPDF** (Docling 97.9% complex-table accuracy, structure-preserving markdown).
- **Hardware (2026 reality):** the RTX 4080/4090 referenced in §12 are **discontinued**; 50-series (Blackwell) launched into a GDDR7 shortage. → **Option A (recommended): Mac Studio M4 Max, 64–128GB unified (~$3.5k–$5k)** as a silent single-box appliance. **Option B (CUDA path): RTX 5070 Ti / 5080 (16GB) or RTX 5090 (32GB)** + 64GB RAM + NVMe (~$5k–$8k), warranted if maximum tokens/sec or future multi-user (vLLM) is needed.
- **Tighter acceptance bar (§2/§11):** **0% hallucination on "not found" questions**, **100% citation fidelity** (filename + page/section), **< 3s to first token**, **no OOM on a 32K context window**, and **Wireshark-confirmed zero outbound traffic**.
- **Sequence:** the report's roadmap front-loads a **3-week turnkey pilot (Ollama + AnythingLLM) on existing hardware** to prove citation accuracy *before* any hardware purchase — matches our Milestones 1–4 and reinforces "validate before capex."

---

## 17. First Implementation Tasks (after this plan is approved)

Sequenced to match the report: **prove citation accuracy on a turnkey stack first (Tasks 0–1), then build the custom citation-grade layer.** **Do not start until the plan is approved.**

0. **Turnkey pilot (validate before building):** install **Ollama + AnythingLLM** on the M4 Pro; `ollama pull qwen3:14b` + `bge-m3`; load a small sanitized corpus; build the **50+ golden eval set** (question → known source page); measure citation accuracy + not-found refusal. **Gate:** do not proceed to custom code until this proves accurate retrieval + citation.
1. **Scaffold the repo** (git init): `app/` (FastAPI), `pipelines/`, `orchestration/` (LlamaIndex), `schemas/`, `prompts/`, `eval/`, `scripts/`, `docs/`, plus the `documents/*`, `indexes/`, `backups/`, `logs/`, `config/` data tree. Add `.gitignore` (ignore `.env`, data dirs, model caches) and `.env.example`.
2. **Stand up infrastructure:** `docker-compose.yml` for Qdrant (or wire LanceDB embedded); verify Ollama on host; `ollama pull` the pinned models (`qwen3:14b`, `bge-m3`, `bge-reranker-v2-m3`); smoke-test connectivity.
3. **Define schemas first:** document/chunk metadata (§7.2, incl. **character/line offsets** + SAC summary field) and the answer+citation schema (incl. **span**). The contract before any LLM-calling code.
4. **Build the metadata catalog** (SQLite) + `originals/` immutable-copy + checksum/dedupe.
5. **Implement the ingestion pipeline** (§8): file-type detect → PyMuPDF routing → Docling structure / Tesseract OCR → page-boundary-preserving markdown → metadata → **SAC summaries** → chunking (§9) → `bge-m3` embeddings → vector upsert → logs + quarantine.
6. **Assemble the fake/sanitized eval corpus** (20–50 docs incl. scanned PDFs **and a DRM pair** — same clause in two matters) and write the labeled eval cases (§11).
7. **Implement retrieval + answering** (§10) in LlamaIndex: **metadata-filter-before-similarity** → **hybrid (dense + BM25)** → **`bge-reranker-v2-m3`**; the system prompt; **mechanical span-overlap citation verification**; score-floor "not found"; source-strength signal.
8. **Build the eval harness** and run it; tune chunking/hybrid/rerank until §11 targets pass — **100% citation fidelity, 0% not-found hallucination, DRM resilience, <3s first token, no 32K OOM**, zero fabricated citations.
9. **Wire the thin chat UI** to the `/query` endpoint; confirm citations open the correct source page. Run the **Wireshark air-gap check**.
10. **Write `install.sh` / `backup.sh` / `restore.sh`** + admin/user guides; do a clean-machine redeploy + restore drill (SC-7) on the dev box as a production dry run.

---

*End of plan. Nothing in this document authorizes processing real attorney/client documents. Real data is touched only at Milestone 6, onsite, on attorney-owned hardware, after written approval.*
