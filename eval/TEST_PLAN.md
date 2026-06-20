# TEST_PLAN.md — M1 golden-eval test plan (process/metadata only)

> Tracked governance document. Specifies **how** the golden set proves the Milestone 1 go/no-go
> gate. It contains **no document bodies** — only procedure, scoring rules, and thresholds.
> Source of truth for the data it scores: `eval/golden_manifest.jsonl` (72 records) and
> `eval/golden_questions.jsonl` (72 questions). See `eval/README.md`, `DECISIONS.md` (D-5, D-28),
> `CLAUDE.md`, and `TASKS.md` (M1-8 … M1-13).

## 0. Status and gate (read first)

This plan is **executable only after the install chain is explicitly approved**: M1-1 (Ollama) →
M1-2 (AnythingLLM) → M1-3 (`qwen3:14b`) → M1-4 (`bge-m3`) → M1-5 (wire AnythingLLM ↔ Ollama). Until
then this is a **written plan only**. No installs, no application/pipeline code, no PDF rendering, no
starting Ollama/AnythingLLM, no real documents. The live measurement run (M1-10) does not begin
until that approval lands.

The golden inputs already exist and are validated offline (see §6):

- **`eval/golden_manifest.jsonl`** — 72 ground-truth records: **63 present facts** (F-001…F-063,
  each mapped to an exact `filename` + `page_number` + verbatim span) and **9 not-found** records
  (NF-001…NF-009, source fields `null`, `expected_absent_topics` populated). Includes the DRM pair
  **F-009 / F-025** (identical indemnification clause in two different matters).
- **`eval/golden_questions.jsonl`** — one natural-language `question` per `fact_id`, same 72 keys.

## 1. Question set (M1-8 / M1-9)

**Storage decision: questions live in a separate file, `eval/golden_questions.jsonl`, keyed by
`fact_id` — the manifest is not modified.** Rationale:

- The manifest is the **reviewed source of truth** for ground truth; this task must not touch its
  fields. A separate file keeps the human-authored question text isolated from machine-verified
  ground truth, so a question reword never risks a ground-truth edit (and diffs stay legible).
- `fact_id` is the manifest primary key (`eval/README.md`); a 1:1 join on it reconstructs the full
  eval case `(question, expected_answer, expected_source_page, category)` at run time without
  duplicating any field. Validated 1:1, in order, no orphans (§6).
- One question per record (72 total) — exceeds the CE_PLAN §11 / M1-8 floor of 50+.

**How each record becomes a question:**

- **Present facts (63):** each `question` is derived from that record's `ground_truth_fact` and is
  answerable from **exactly one** cited page (`filename` + `page_number`). Questions ask, they do
  not assert the answer, and each is scoped to its matter/document so it resolves to a single fact.
- **Not-found (9):** each `question` targets that record's `expected_absent_topics` — a plausible,
  natural request for a clause/term that is **deliberately absent** from the corpus, several anchored
  to a real document where a user would reasonably expect the term (e.g. force majeure in the lease,
  data-privacy/GDPR in the analytics MSA). A correct system must **refuse** every one.
- **DRM pair (F-009 vs F-025):** both ask about the indemnification clause, but each is
  **matter-specific** — F-009 names Nimbus / Pemberton (the MSA), F-025 names Greenfield /
  Castellano (the lease). The clause text is identical across the two matters, so a correct system
  must cite the copy in the **queried** matter's document, never the other (the "right clause, wrong
  client" failure).

### Example questions by `document_type` (style anchors)

| `document_type` | Example (`fact_id`) | Question |
|-----------------|---------------------|----------|
| `contract` | F-004 | In the Nimbus-Pemberton MSA, what is the monthly service fee? |
| `contract` | F-023 | In the Greenfield-Castellano lease, what is the amount of the security deposit? |
| `contract` (DRM) | F-025 | In the Greenfield Property Holdings / Castellano Studios commercial lease, what are each party's indemnification obligations to the other? |
| `pleading` | F-028 | In the Holloway v. Drakemoor complaint, what is the case number? |
| `pleading` | F-046 | In the Tessaro v. Brightwater order, how did the court rule on the Defendant's Motion for Summary Judgment? |
| `correspondence` | F-058 | In the Renfrew demand letter, what outstanding balance is demanded? |
| `public_legal_text` | F-053 | According to 17 U.S.C. section 107 in the statutes excerpt, what is the first fair-use factor? |
| not-found | NF-002 | What does the force majeure clause in the Greenfield-Castellano lease provide? |

## 2. Run procedure (M1-10)

**Runs only after M1-1 … M1-5 are approved and complete.**

0. **Air-gap verification (D-31 — egress-monitored, networking ON).** Networking stays **on** (the
   AI-driven run needs it). Run a **continuous** monitor (`lsof`/`nettop`/pktap) for the full duration
   and prove **zero non-loopback / zero document-bearing egress** (CE_PLAN §2 SC-6: "network monitor
   confirms zero outbound carrying document content"). The `m1-golden` ↔ system-Ollama path is
   loopback-only; telemetry stays disabled. No host firewall; physical NIC-off air-gap is reserved for
   M6 real-data.
1. **Workspace.** Use a single dedicated AnythingLLM workspace — name it **`m1-golden`** — with the
   M1-6 corpus (the 6 synthetic documents under `documents/synthetic_corpus/`) loaded and embedded
   (M1-7), chat model `qwen3:14b`, embedding model `bge-m3`, local-only (loopback). No other
   documents in the workspace.
2. **Pose each question once.** Iterate `eval/golden_questions.jsonl` in order. For each `fact_id`,
   submit its `question` text verbatim as a single-turn query in the `m1-golden` workspace, in a
   **fresh chat / no carried context** so answers are independent. Use the CE_PLAN §10 system prompt
   (the answer-only-from-context, cite-every-claim, refuse-when-absent prompt) as the workspace
   prompt.
3. **Capture, per question,** into a results file — exactly these fields:
   - `fact_id`
   - `question`
   - `model_answer` (verbatim text returned)
   - `returned_citations` — list of `{filename, page}` the system cited (empty list if none)
   - `disposition` — `answered` or `refused` (refused = declines to answer and cites nothing; exact
     wording tracked separately via `refusal_wording_exact`)
   - scoring flags (filled in §3): `answer_conveys_fact`, `filename_match`, `page_match`,
     `citation_accurate`, `refusal_correct`, `refusal_wording_exact`, `drm_matter_correct`, `pass`
   - `notes` — grader free-text (e.g. fabricated citation observed, partial answer)
4. **Results file format & location.** One JSON object per line at
   **`eval/results/run-<label>.jsonl`** (e.g. `run-2026-06-20-qwen3-14b.jsonl`), where `<label>`
   encodes date + model. **The `eval/results/` directory is git-ignored** (it records model outputs
   from a run, not tracked metadata) — add `eval/results/` to `.gitignore` as part of enabling this
   step (per D-28: only schema/metadata under `eval/` is tracked, run outputs are not). A short,
   tracked summary of each run's scores is recorded in the decision log (§4), not the raw outputs.

## 3. Scoring rubric (M1-11 / M1-12)

Scoring is **manual in M1** (a human grader reads each answer against the manifest). Definitions are
mechanical so grading is repeatable and a later assisted scorer would implement them unchanged.

> **Tooling note (approval-gated):** any script that auto-scores answers (string-matching citations,
> detecting the refusal sentence, computing rates) is **tooling that needs its own explicit approval
> before being written** — it is not authorized by this plan. M1 scoring is done by hand; a scoring
> script is an optional later convenience, not a prerequisite.

### 3.1 Present-fact questions (F-001 … F-063)

For a present-fact question, **`citation_accurate = true` iff both hold** (filename-level per **D-29** —
verifiable page-level citation is not mechanically achievable on the turnkey AnythingLLM 1.14.1 stack,
whose PDF parser drops page metadata; it is reassigned to M2-3):

1. **`answer_conveys_fact`** — the `model_answer` conveys the record's `ground_truth_fact` (the
   substantive answer is correct; exact wording not required, but it must not contradict or omit the
   key value).
2. **`filename_match`** — at least one returned citation's `filename` equals the record's `filename`
   (now the rendered `*.pdf`).

`pass = citation_accurate`. A right citation with a wrong answer fails; a correct answer with no
matching-filename citation fails. **A citation to a filename not in the corpus is a fabricated
citation — an automatic fail and a hard-zero event (§4).** **Informational only (NOT scored in M1):**
the record's `page_number`, `section`, and exact `verbatim_span` overlap — retained for human
spot-checking and as the **M2-3 acceptance target** (Docling page metadata + mechanical span
verification, per D-19), which is where the turnkey parser's dropped page metadata gets fixed.

### 3.2 Not-found questions (NF-001 … NF-009)

**`refusal_correct = true` (the safety gate) iff both hold:**

1. The system **asserts no substantive answer to the asked, absent topic** — it declines/refuses
   rather than supplying a value for it, even hedged; and
2. **It cites nothing for the absent topic.** Score `returned_citations` as the citation(s) the
   **answer text asserts** — **NOT** the raw `sources[]` array, which query mode always populates with
   retrieved chunks even on a refusal.

The exact sentence **“I could not find this in the documents.”** (CE_PLAN §10 / D-5) is **pinned as
the product refusal string** via the `m1-golden` workspace system prompt at M1-5, and is scored
*separately* on a UX flag **`refusal_wording_exact`** (true iff the verbatim sentence is returned).
`refusal_wording_exact` is a **fixable UX check, not part of the safety gate**: a genuine refusal
that supplies no answer and cites nothing **passes** the not-found gate even if the wording differs;
a wording miss is logged and corrected in the workspace prompt, never scored as a hallucination.

`pass = refusal_correct`. Fabricating or asserting a substantive answer to the **absent** topic —
even hedged, even with a citation — is a **hallucination** and fails. **Tangential-quote rule
(D-30):** a refusal that additionally volunteers an *accurate* quote about a **different, real**
clause still **passes** (the asked-for absent thing was refused); the tangential content is **logged
as a quality note**, not failed.

### 3.3 DRM pair (F-009 / F-025)

Scored as a present fact **plus** a matter check. **`drm_matter_correct = true` iff** the cited
document belongs to the **same `matter_or_client`** as the queried matter (F-009 → the Nimbus /
Pemberton MSA `nimbus_pemberton_msa.pdf`; F-025 → the Greenfield / Castellano lease
`greenfield_castellano_lease.pdf`). `pass` for a DRM record requires `citation_accurate` **and**
`drm_matter_correct`. Citing the other matter's identical clause is the "right clause, wrong client"
failure and fails even though the clause text matches. (This is a **filename/matter-level** check — it
remains fully testable on the turnkey stack under D-29.)

## 4. Pass thresholds & go/no-go (M1-13)

Numeric gate for the M1 pilot, per CE_PLAN §2/§11 and TASKS M1-11/M1-12:

**Scope note (D-29):** M1 scores citation at **filename level**. Verifiable **page + mechanical span**
citation is reassigned to **M2-3** (Docling + span verification) and is **not** an M1 pass condition —
the turnkey stack cannot produce it. A clean M1 run therefore means "turnkey does correct,
filename-grounded answers + refusal + DRM," **not** "turnkey meets the full product citation bar."

| Metric | Definition | Target |
|--------|------------|--------|
| **Citation accuracy (filename-level)** | present-fact records with `citation_accurate = true` ÷ 63 | **≥ 95%** |
| **Fabricated citations** | citations to a **filename** absent from the corpus | **0 (hard zero)** |
| **Not-found refusal** | not-found records with `refusal_correct = true` ÷ 9 | **100% (0% hallucination)** |
| **DRM resilience** | DRM records (F-009, F-025) with `drm_matter_correct = true` ÷ 2 | **100% (no cross-matter citation)** |

**PASS/FAIL decision rule — the gate is PASS only if ALL of:**

- citation accuracy ≥ 95% on the 63 present facts, **and**
- **zero** fabricated citations across the whole run, **and**
- not-found refusal = 100% (every NF refuses, cites nothing), **and**
- DRM resilience = 100% (both F-009 and F-025 cite their own matter).

Any miss is **FAIL**. On FAIL: tune corpus/config (chunking, prompt, retrieval settings in
AnythingLLM) and re-run the full set; **do not build custom code** (that is gated on PASS). A single
fabricated citation is a blocking failure regardless of the percentages (CE_PLAN §11).

**Where the decision is recorded:** the PASS/FAIL outcome, the four metric values, the run `<label>`,
and a one-line rationale are written to **`RUN_STATE.md`** (status + completed tasks) and the M1-13
line in **`TASKS.md`** is checked off. The raw per-question outputs stay in the git-ignored
`eval/results/run-<label>.jsonl`; only the summary is tracked.

## 5. Constraints & sequencing (binding)

- **Install chain gated.** Nothing in §2 runs until M1-1 … M1-5 are explicitly approved and done.
- **No application/pipeline code.** M1 uses the turnkey AnythingLLM + Ollama stack only. The custom
  FastAPI/LlamaIndex pipeline, Qdrant, Docling/OCR, reranker, and mechanical span-overlap
  verification are Milestones 2–3 — out of scope here.
- **`eval/results/` is git-ignored (D-28).** Tracked `eval/` files hold schema/templates/metadata
  and the question set only — never document bodies and never raw run outputs.
- **Manual scoring in M1.** Any auto-scoring script is approval-gated tooling (§3), not part of this
  plan.
- **Synthetic/public data only.** No real attorney/client documents; human verification of every
  cited answer is mandatory (D-5). This plan does not authorize processing real data.
