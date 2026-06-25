# Legal Document Chat for Attorneys — Private, Self-Hosted, Cited

**Parse and chat with sensitive legal documents — privately, on your own hardware, using local open-source LLMs, with every answer cited to the exact page and verified against the source.**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.12+-3776AB.svg)](https://www.python.org/)
[![Stack: FastAPI + Ollama + LanceDB](https://img.shields.io/badge/stack-FastAPI%20%C2%B7%20Ollama%20%C2%B7%20LanceDB-0a7e8c.svg)](#tech-stack)
[![PRs welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

<a href="https://www.producthunt.com/posts/legal-document-chat-for-attorneys-open?utm_source=badge-featured&amp;utm_medium=badge" target="_blank"><img src="https://api.producthunt.com/widgets/embed-image/v1/featured.svg?post_id=1180166&amp;theme=light" alt="Featured on Product Hunt" height="36" /></a>
&nbsp;
<a href="https://abacklaunch.com" target="_blank"><img src="https://abacklaunch.com/badges/listed-on-blue.svg" alt="Listed on Aback Launch" height="36" /></a>

![Legal Document Chat — local, cited document chat for attorneys: a matter-scoped conversation with answers cited to the exact page and section](docs/demo.png)

> _Matter-scoped chat with every answer cited to the exact page and section. Shown with synthetic documents — development uses synthetic/public data only._

## Why this exists

Attorneys need to parse, search, and ask questions across **privileged, confidential documents** — but sending those documents to a closed-model cloud API (OpenAI, Anthropic, Gemini) is a non-starter for attorney–client privilege and client confidentiality.

This project is a **self-hosted, privacy-first** document-intelligence stack that runs **100% locally**:

- **Your documents never leave the machine.** Inference, embeddings, OCR, and storage are all local. The query path makes **no cloud calls** and binds to **loopback only** (`127.0.0.1`).
- **Open-source / local models** via [Ollama](https://ollama.com) — no API keys, no per-token billing, no vendor lock-in.
- **Every answer is grounded and verified.** A mechanical, character-level check confirms each cited quote actually appears in the cited source; unverifiable claims are dropped, never shown. If the documents don't support an answer, it says so instead of hallucinating.

It is a **cited-retrieval assistant — not an AI lawyer and not an autonomous agent.** It locates and summarizes what documents say, with citations the user verifies. It gives no legal advice and has no tools to act on the outside world.

## Who this is for

- **Engineers building legal tech** who need a private, inspectable RAG stack instead of a black-box SaaS.
- **Solo founders & AI agencies** who want a self-hostable "chat with documents" product they can deploy for privacy-sensitive clients.
- **Anyone who needs verifiable, local document chat** — the citation-verification core is domain-agnostic.

Practicing attorneys: you're welcome too — open an issue describing a real workflow (see [CONTRIBUTING](CONTRIBUTING.md)).

## How it compares to cloud AI chat

How local, self-hosted legal document chat differs from sending documents to a cloud chatbot (ChatGPT, Claude, Gemini):

| | **Legal Document Chat** (this project) | Cloud AI chat (ChatGPT / Claude / Gemini) |
|---|---|---|
| Where your documents go | Stay on your machine — loopback only (`127.0.0.1`) | Uploaded to a third-party cloud |
| Models | Local, open-source via [Ollama](https://ollama.com) | Closed, vendor-hosted |
| Citations | Mechanically verified to page + exact span | Often unverified or hallucinated |
| Works offline / air-gapped | Yes (after a one-time model download) | No |
| Cost | Free — no API keys, no per-token billing | Subscription or per-token |
| Attorney–client privilege | Preserved — nothing leaves the machine | At risk — data leaves your control |

## Features

- **Matter-scoped chat** — documents are organized by legal matter; retrieval is hard-filtered to the matter, so one client's documents can never leak into another's answer.
- **Mechanically-verified citations** — every cited span is checked character-by-character against the retrieved source chunk. A fabricated or altered quote yields **zero** citations. This is the core differentiator.
- **Page- and span-level citations** — answers point to file + page + the exact highlighted text; click to open the source at that spot.
- **Document Hub** — drag-and-drop upload with async parse/ingest and a status view.
- **Table & exhibit extraction** — fee schedules and damages tables are extracted as structured, searchable, citable content (Docling TableFormer), not garbled text.
- **OCR for scanned PDFs** — image-only pages are routed through local Tesseract; born-digital pages keep the fast path.
- **Contract Review clause checklist** — run a curated clause set over a contract; each clause comes back cited or flagged "potentially missing."
- **Multi-document review grid** — rows = documents, columns = questions, cells = cited answers, for reviewing many documents at once.
- **Honest refusal** — answers "I could not find this in the documents" rather than inventing one.
- **Air-gapped by design** — loopback-only, no telemetry, no cloud dependencies at query time.

## Tech stack

| Layer | Choice |
|---|---|
| Backend / API | **Python · FastAPI** (loopback-only) |
| Local inference | **Ollama** — `qwen3:14b` (chat), `bge-m3` (embeddings), `bge-reranker-v2-m3` (optional) |
| Vector store | **LanceDB** (embedded, no server) |
| Parsing & OCR | **PyMuPDF**, **Docling** (TableFormer), **Tesseract**, **python-docx** |
| Retrieval & answering | **Hand-rolled RAG** — *no LangChain, no LlamaIndex*, for a transparent claim → chunk → character-offset citation path |
| UI | Vanilla **HTML / CSS / JS** (no framework) |
| Deploy | **Docker Compose** (publishes `127.0.0.1:8000` only) |

## Quickstart

**Prerequisites:** [Ollama](https://ollama.com) running locally, Python 3.12+, and (optional) Tesseract for scanned PDFs / Docker Desktop for the container path.

```bash
# 1. Pull the local models (one-time download; runs offline afterward)
ollama pull qwen3:14b
ollama pull bge-m3

# 2a. Run locally (Python) — run from inside pipeline/
cd pipeline
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python api.py
#    → open http://127.0.0.1:8000/app
```

```bash
# 2b. ...or run with Docker Compose (loopback-only)
deploy/up.sh
#    → open http://127.0.0.1:8000/app
#    deploy/down.sh to tear down
```

Then open the **Document Hub**, create a matter, upload a PDF (use your own or any public/synthetic document), and start asking questions. Every answer comes back with a clickable, verified citation.

> **Optional — scanned PDFs:** install Tesseract (`brew install tesseract` on macOS) before ingesting image-only documents.

## Architecture

```
ingest → parse → chunk + embed → retrieve → answer → verify → cite
```

1. **Ingest / parse** — PyMuPDF for born-digital text (with page + character offsets), Docling TableFormer for tables, Tesseract for scanned pages.
2. **Chunk + embed** — page/section-aware chunks with source context, embedded by `bge-m3` into LanceDB.
3. **Retrieve** — a hard **matter pre-filter** runs *before* similarity search (so retrieval is scoped to one matter), with an optional local reranker.
4. **Answer** — `qwen3:14b` answers from the retrieved context under a strict grounded-and-cite-or-refuse prompt.
5. **Verify** — each cited quote is mechanically checked to overlap a retrieved chunk's character range on its page. The displayed page/span is **derived from the verified match**, never asserted by the model.
6. **Cite** — the UI shows the answer with source chips and opens the original page with the cited span highlighted.

## Roadmap

- **Shipped:** matter-scoped cited chat · mechanical span verification · table/exhibit extraction · OCR for scans · Contract Review clause checklist · multi-document review grid.
- **Planned / parked:** deposition transcripts with `page:line` citations · search-by-cited-authority (case/statute extraction) · retrieval-recall tuning · Apple-Silicon OCR/ingest speedups · a warmer assistant voice.
- **Privacy posture:** development uses **synthetic / public documents only**; this is a deliberate boundary, not a limitation of the code.

See [`DECISIONS.md`](DECISIONS.md) for the full architecture-decision record (why hand-rolled RAG, why LanceDB over a server, why mechanical citation verification, etc.).

## FAQ

**Is this a private, local legal document chat?**
Yes. It's a self-hosted "chat with your legal documents" tool that runs entirely on your own hardware. Inference, embeddings, OCR, and storage are all local, and the service binds to loopback (`127.0.0.1`) only.

**Does my data leave my computer?**
No. The query path makes no cloud calls and requires no API keys. Your documents are never uploaded to OpenAI, Anthropic, Google, or any third party.

**Does it work offline / air-gapped?**
Yes. After a one-time local model download via [Ollama](https://ollama.com), it runs with no internet connection.

**Can I chat with scanned PDFs?**
Yes. Image-only pages are routed through local Tesseract OCR, while born-digital pages keep the fast text path. Tables are extracted as structured, citable content.

**How is this different from using ChatGPT, Claude, or Gemini on legal documents?**
Those send your documents to a third-party cloud — a non-starter for privileged, confidential material. This keeps everything local, uses open-source models, and mechanically verifies every citation to a real page and span. See [How it compares](#how-it-compares-to-cloud-ai-chat).

**Is this an AI lawyer? Does it give legal advice?**
No. It is a cited-retrieval assistant — it locates and summarizes what your documents say, with citations you verify. It gives no legal advice, draws no legal conclusions, and takes no actions.

**What models and stack does it use?**
Local open-source models via Ollama (`qwen3:14b` for chat, `bge-m3` for embeddings), with FastAPI, LanceDB for vector search, and PyMuPDF / Docling / Tesseract for parsing and OCR. See [Tech stack](#tech-stack).

## Contributing

Contributions are very welcome — see **[CONTRIBUTING.md](CONTRIBUTING.md)**. We're especially looking for help with new document parsers, additional local model backends, evaluation harnesses, and UI. Domain experts (practicing attorneys) are welcome to open issues describing real workflows.

## License

[MIT](LICENSE).

- Note: this project depends on **PyMuPDF**, which is **AGPL-3.0** licensed — fine for an open-source, self-hosted deployment; be aware of its copyleft terms if you build a closed derivative.
- The clause taxonomy is informed by the **CUAD** dataset (CC-BY-4.0).
