# Contributing

Thanks for being here. This is an open-source, **local-first** stack for parsing and chatting with sensitive documents using open-source models — with **verifiable, mechanically-checked citations** at its core. It's useful well beyond law, and it's built to be read, forked, and extended.

## We're specifically looking for you if you work on…

- **RAG / retrieval** — retrieval quality, reranking, hybrid (dense + lexical), recall tuning, evaluation. Our RAG is **hand-rolled** (no LangChain/LlamaIndex) precisely so the retrieve → chunk → citation path is transparent and hackable.
- **Document parsing** — PDF, DOCX, OCR, tables/exhibits, and new document types (deposition transcripts with `page:line` citations is a designed-but-unbuilt feature waiting for an owner).
- **Document chat / grounded generation** — prompt design, structured extraction, confidence/abstention, and keeping answers honestly grounded.
- **Open-source / local-model inference** — new model backends, quantization, faster local serving, Apple-Silicon acceleration.
- **Legal-tech builders, solo founders, and AI agencies** — you want a private, self-hostable "chat with documents" stack you can deploy for privacy-sensitive clients. Battle-test it, file the rough edges, send PRs.
- **Practicing attorneys & domain experts** — you don't need to write code. **Open an issue describing a real workflow** (how you actually cite a deposition, review a contract, or check a filing) — that's some of the most valuable input we can get.

## The one rule that matters most

**Never weaken citation verification to make a number look better.** The mechanical span check must *never* mark an unverified or fabricated quote as a verified citation. A false *reject* of a true quote is an acceptable bug; a false *accept* of a fabrication is not. If a change touches `pipeline/verifier.py` or how citations are derived, it needs a test proving fabrications still get rejected.

Also: **synthetic / public documents only** in the repo and in tests — never commit real client data, PII, or secrets.

## Good ways to contribute

- **New parsers** — a document type or format we don't handle well yet (e.g., transcripts, email threads, spreadsheets).
- **New model backends** — alternative local chat/embedding/reranker models or runtimes.
- **Evaluation harnesses** — golden-set questions, citation-accuracy scoring, retrieval-recall metrics.
- **UI** — the front end is dependency-light vanilla JS; there's lots of room for thoughtful, accessible improvements.
- **Performance** — faster ingest/OCR, smaller memory footprint, first-token latency.
- **Docs & examples** — a real demo GIF, a docker-only quickstart, a "bring your own corpus" guide.

## Dev environment

```bash
# Prereqs: Python 3.12+, Ollama running locally, (optional) Tesseract for scanned PDFs.
ollama pull qwen3:14b
ollama pull bge-m3

cd pipeline
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Run the full test suite (unittest, not pytest):
cd ..
python -m unittest discover -s pipeline/tests

# Run the app:
python -m pipeline.api      # → http://127.0.0.1:8000/app
```

The pipeline is plain Python modules under `pipeline/` (ingest → chunk → embed → retrieve → answer → verify), a FastAPI surface in `pipeline/api.py` + `pipeline/routes_*.py`, and a vanilla-JS UI in `pipeline/static/`. `DECISIONS.md` explains the why behind the architecture.

## Workflow

1. **Find or open an issue.** Look for [`good first issue`](../../labels/good%20first%20issue). Comment to claim it so we don't double up.
2. **Branch** from `main`: `feat/<short-name>` or `fix/<short-name>`.
3. **Test-first where it matters.** New behavior gets a test; anything touching parsing, retrieval, or verification *must* have one. Keep the suite green (`python -m unittest discover -s pipeline/tests`).
4. **Keep changes surgical** and match the surrounding style.
5. **Open a PR** describing what changed, how you verified it, and any trade-offs. Link the issue.

Small, focused PRs get reviewed fastest. Not sure where to start? Open an issue and ask — we're happy to point you at something.
