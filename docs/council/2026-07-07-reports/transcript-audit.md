# Adversarial audit: transcript readiness of legal-doc-intelligence

_Agent report, 2026-07-07. Verbatim._

## Verdict up front

**Transcripts are effectively unsupported today.** The pipeline is a genuinely well-built
contracts/pleadings QA system (the mechanical verifier and matter isolation are better than most
commercial tools), but it has zero transcript-aware code, zero transcript eval coverage, and its
most likely real-world transcript inputs either get rejected at upload or silently degrade to
uncitable output. The project already knows this: transcript support was designed and then
explicitly deferred (`DECISIONS.md:483-491`, D-56), while the marketing site simultaneously
promises transcripts "cited to the exact line" (`site/index.html:104-105`, `:17`) — a gap the
repo itself flags as an unresolved contradiction (`TASKS_M2.md:237-240`).

## 1. Transcript structure: nothing is preserved

- **No page:line concept anywhere.** The chunk schema is `{source_filename, matter,
  document_type, page_number, section, char_start, char_end, text}` (`pipeline/kb_ingest.py:39-44`,
  `pipeline/retrieval.py:19-21`). No line numbers, no speaker, no exhibit refs, no errata
  awareness.
- **What a citation looks like today:** the verifier emits `{filename, page, chunk_id, span,
  char_start, char_end}` (`pipeline/verifier.py:117-124`) — "Drakemoor_Dep.pdf, page 45" plus a
  verbatim quote. An attorney citing a brief needs "Drakemoor Dep. 45:12-46:3."
- **Worse for the most common formats:** a `.txt` transcript (the standard ASCII delivery) is
  ingested as a *single page_number=1 record* (`pipeline/extractors.py:51-58`), so every citation
  into a 300-page deposition reads "page: 1." The highlight/thumbnail endpoints are PDF-only
  (`pipeline/routes_kb.py:105`), so a `.txt` citation cannot be visually verified in the UI.
- **`document_type` is squatted by extractor provenance.** `kb_ingest.py:41` stores
  `p.get("source", "doc")` — i.e. `"pymupdf"`/`"tesseract"`/`"txt"` — into the `document_type`
  field. (Contrast `chunking.py:150-154`, the eval-corpus path, which stores a real
  manifest-sourced `document_type` — the live KB path regressed this.)
- Also lost relative to the eval path: the KB embedding text has an always-empty section
  breadcrumb, `f"[Matter: {slug} | Section: ]"` (`kb_ingest.py:43`), vs. the richer SAC line in
  `chunking.py:150`.

## 2. Chunking: 900-char windows butcher testimony structure

`_chunk_pages` cuts every 900 chars, extending to the next newline within 200 chars
(`kb_ingest.py:17,30-45`). Transcript lines are short (~60 chars), so cuts land at *arbitrary*
lines with no awareness of Q/A pairs, speaker turns, or examination segments:

- **Answer orphaned from question:** a chunk starting "A. Yes, that's correct." retrieves with no
  antecedent question; the inverse leaves the answer in a chunk that didn't make top-5.
- **Speaker misattribution:** "BY MR. SMITH:" and "THE WITNESS:"/"MR. JONES: Objection" live at
  turn boundaries; once windowing separates the designation from the text, colloquy between
  attorneys is indistinguishable from testimony. Nothing in the system prompt
  (`pipeline/answering.py:40-70`) mentions speakers.
- **Line-number gutter pollution:** the design doc itself names stripping the gutter as a "cheap
  interim win" (`docs/superpowers/specs/2026-06-21-transcripts-design.md:16-17`) — never done.
  Gutter digits degrade embeddings and can false-reject verbatim quotes: `_norm` keeps digits
  (`answering.py:83-95`, `verifier.py:31-69`), so a model quote "Q. Did you" won't
  substring-match chunk text "12 q. did you".
- **Short answers are a verifier trap:** standalone quotes under 15 normalized chars are never
  span-mapped (`answering.py:213-215`, `_QUOTED_RE` at `:80`). Deposition answers are frequently
  "Yes." / "I don't recall." — and `locate_span` matches the *first* occurrence in the chunk
  (`verifier.py:79-82`), so char offsets (and any future line derivation) can silently point at
  the wrong "Yes." on the page.

## 3. Long-document behavior: retrieve-then-answer structurally fails transcript workflows

- **Scale math:** a 300-page deposition is ~350-600 chunks. Chat is hard-wired to `top_k=5`
  (`answering.py:316`) with `NUM_CTX = 8192` (`answering.py:36`). Five 900-char chunks is ~1% of
  the transcript.
- **"Summarize what witness X said about the contract"** retrieves 5 fragments and, per Rule 1 of
  the system prompt, answers *only* from them (`answering.py:46-48`). The refusal doesn't fire
  because the fragments are relevant — so the system produces a confidently *partial* summary
  presented as complete. **The verifier guarantees no false statements; it cannot guarantee
  completeness**, and nothing in the UI says "built from 5 of 480 chunks."
- **"Every mention of Exhibit 14" / chronologies / testimony indexes** are unanswerable by
  construction: no exhaustive-scan mode exists. The grid (`pipeline/grid.py:67-101`) still
  evaluates each cell with `top_k=5` (`grid.py:74`).
- **Wasted asset:** hybrid BM25+RRF exists and correctly applies the matter pre-filter to both
  arms (`retrieval.py:91-97`) — exactly what exact-phrase testimony lookup needs — but the chat
  path never passes `hybrid=True` (`answering.py:263`).

## 4. Formats: common transcript deliveries are rejected or silently degrade

Accepted: `.pdf`, `.docx`, `.txt`, `.md` only (`routes_kb.py:27,59-60`; `extractors.py:72`).

| Real-world input | What happens today |
|---|---|
| Full-size born-digital PDF depo | Works; page numbers correct; no lines; gutter pollutes chunks |
| ASCII `.txt` (standard delivery) | Whole file is page 1; citations say "page: 1"; no highlight view. **Silent degradation — status shows "ready".** |
| `.ptx` / E-Transcript / `.lef` | Rejected at upload, generic "unsupported type". Fail-loud, at least. |
| Condensed 4-up PDF | Ingests "successfully": PDF sheet number != transcript page — every cite off ~4x; block order can scramble. **Silent and confidently wrong.** |
| OCR'd scan | Per-page Tesseract routing fails loud on low confidence (`ingestion.py:149-160`) — genuinely good — but OCR'd gutters produce garbage digit runs. |

## 5. Eval: zero transcript coverage

All 72 golden facts target 6 documents (MSA, lease, complaint, SJ order, statutes excerpt, demand
letter). Not one question targets Q/A-format content. The only "deposition" artifact in the whole
corpus is a 3-line prose *summary* fixture, typed as `"pleading"`, absent from the golden set.
**Every quality claim this project makes is unmeasured for transcripts.**

## What already works better than expected

1. **The verifier substrate is transcript-ready:** page-relative offsets with the invariant
   `page_text[char_start:char_end] == chunk.text` (`kb_ingest.py:20-23`) mean page:line can be
   *derived* from verified offsets without touching the verifier — the deferred design exploits
   exactly this (`2026-06-21-transcripts-design.md:35-39`).
2. **Matter isolation is properly hard** (allowlist-validated pre-filter before similarity, both
   hybrid arms scoped; grid per-document citation post-filter).
3. **Fail-loud discipline** on OCR and unsupported types is real.
4. **A complete, verifier-preserving transcript design already exists** — but its v1 defers
   Q/A-speaker chunking and ASCII/E-Transcript formats (`:47-49`), i.e. the actual arrival format
   and the chunking fix, which this audit rates co-equal in value to page:line.

## The 5 highest-value transcript features (verifier + matter isolation preserved)

**F1. Transcript-aware ingestion with page:line citations (M).** Detect the numbered gutter (PDF)
or line-number prefixes + form-feed/"Page N" headers (ASCII); emit per-line records alongside
clean page text (gutter stripped, embeddings de-pollute); store the line-map per (doc, page) in a
sidecar; chunks keep the existing schema. After the *existing* verifier confirms a span, map
verified offsets through the line-map to render "45:12-18". Requires fixing the `document_type`
squatting and a user "this is a transcript" toggle (no auto-detect). *Naive failure:* trusting
model-asserted line numbers, or deriving lines on a condensed 4-up PDF — a confidently wrong
"45:12" is worse than page-only. Must disambiguate repeated short spans ("Yes.") before line
derivation.

**F2. Speaker-turn / Q-A-pair chunking (M).** Parse turns (`Q.`, `A.`, `THE WITNESS:`,
`MR. X:`, `BY MR. X:`), cut only at pair boundaries (~900-1400 chars), never splitting a Q from
its A within a page. Carry `speaker`, `examining_attorney`, `exam_segment` metadata into
`embedding_text` and context labels. Chunks stay page-bounded so the offset invariant holds; a
pair spanning a page break becomes two chunks sharing an `exchange_id` (prior lines ride in
`embedding_text` only, never in `text`). *Naive failure:* cross-page chunks breaking the offset
invariant (verifier false-rejects everything); regex misparse on OCR text mislabeling an
attorney's objection as testimony — misattribution with a verified quote attached is a
malpractice-grade error, so unparseable regions must fall back to speakerless chunks, never
guessed speakers.

**F3. Deposition digest mode — map-reduce, not top-k (L).** `POST /transcripts/{doc_id}/digest`:
iterate ALL chunks in page order in batches (~10 pages per local LLM call), extract topic-tagged
testimony bullets each with a verbatim span, run `verify_answer` per batch with that batch's
chunks as grounding, keep only verified bullets, group by topic into a page(:line)-cited digest.
Stream progress over SSE like the grid. *Naive failure:* shipping "summarize" over `top_k=5` and
calling it a summary; or a reduce step writing synthesized prose carrying no citations — the
reduce must only reorder/group verified bullets. Budget honestly: ~40-60 local qwen3 calls for a
300-pager; needs a progress UI.

**F4. Exhaustive testimony lookup — "every mention of X" (S-M).** Retrieval-only, no generation:
hybrid BM25+dense with `candidate_k` = all chunks of the target doc (or normalized
substring/fuzzy scan), return every hit as a page(:line)-cited quote list. Zero hallucination
surface. Wire `hybrid=True` into the chat path while there. *Naive failure:* quietly capping at
top-k and labeling it "all mentions" — if truncated, the UI must say "first N of M"; label the
mode "exact and near matches."

**F5. Contradiction surfacing across transcripts/documents (L).** For a topic, pull each
witness's verified testimony via F4, pair candidate statements (same matter only), ask the LLM to
flag tension. Display ONLY the two side-by-side verified quotes with cites; "possible tension" is
advisory prose, never a citation, never the word "contradiction" as a legal conclusion. *Naive
failure:* the model asserting contradictions between paraphrases it wrote itself (compare
verbatim verified spans only); cross-matter pairing leaking privileged testimony (pair generator
takes matter-scoped inputs only).

**Sequencing:** F1+F2 ship together with transcript eval fixtures (synthetic 50-page depo with
known page:line facts, Q/A-boundary questions, speaker-attribution traps), because today the eval
set cannot detect any transcript regression at all. F4 is the cheapest real win. Also fix:
`document_type` squatting (`kb_ingest.py:41`) and the landing page's "exact line" transcript
claim (`site/index.html:104-105`), currently untrue in every input format.
