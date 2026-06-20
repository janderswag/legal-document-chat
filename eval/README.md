# eval/ — Golden eval workspace (tracked metadata only)

> This directory is **tracked in git**. It holds the M1 golden-eval **manifest schema, templates,
> and ground-truth metadata** — and nothing else. See `DECISIONS.md` D-28 and `CLAUDE.md`.

## What may and may not live here

**Allowed (tracked):** the manifest schema, templates, ground-truth metadata records, and short
`verbatim_span` snippets drawn **only from synthetic pilot documents**.

**Not allowed:** full source-document bodies, and any real attorney/client text — ever. Synthetic
source documents live under the git-ignored path **`documents/synthetic_corpus/`**, not here and
not under any unignored `corpus/`. This preserves the invariant that **document data is never
committable by default** (D-28; `.gitignore` ignores `documents/`).

## The M1 ground-truth manifest

The manifest maps each known answer (a "fact") to its exact source location and verbatim span, and
also enumerates the topics deliberately **absent** from the corpus (to test not-found refusal). It
is the source of truth for the golden eval set (M1-8) and the measurement step (M1-10..M1-13).

**Canonical file (to be authored in M1-6):** `eval/golden_manifest.jsonl` — one JSON object per
line, one line per `fact_id`. **Template:** `eval/manifest.template.jsonl` (one placeholder record).

JSONL is used (not CSV) because `ground_truth_fact` and `verbatim_span` routinely contain commas,
quotes, and newlines.

### Schema (one record per `fact_id`)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `doc_id` | string | yes* | Stable id of the source document (e.g. `msa-acme-001`). Null for not-found records. |
| `filename` | string | yes* | Filename under `documents/synthetic_corpus/` (e.g. `acme_msa.md`). Null for not-found records. |
| `document_type` | string | yes* | `contract` \| `pleading` \| `correspondence` \| `exhibit` \| `memo` \| `public_legal_text`. Null for not-found records. |
| `matter_or_client` | string | yes* | Matter/client the document belongs to (e.g. `Acme v. Globex`). Drives DRM/matter-scoping tests. Null for not-found records. |
| `page_number` | integer | yes* | 1-based page the fact appears on (per the document's explicit page markers). Null for not-found records. |
| `section` | string | no | Nearest heading/section breadcrumb (e.g. `Section 4 › 4.2 Indemnification`). |
| `fact_id` | string | **yes** | Stable unique id for this ground-truth fact (e.g. `F-001`). Primary key. |
| `ground_truth_fact` | string | **yes** | The known answer in plain language (what a correct response must convey). |
| `verbatim_span` | string | yes* | The exact text copied from the synthetic document that supports the fact. Short snippet only; from synthetic docs only. Null for not-found records. |
| `expected_absent_topics` | string[] | **yes** | Topics/questions deliberately **not** answerable from the corpus. Non-empty marks a not-found/refusal case; empty `[]` marks a present-fact case. |
| `notes` | string | no | Authoring notes: category, why it's tricky, DRM-pair linkage, etc. |

\* Required for **present-fact** records (`expected_absent_topics: []`). For **not-found** records
(`expected_absent_topics` non-empty), the source fields (`doc_id`, `filename`, `document_type`,
`matter_or_client`, `page_number`, `verbatim_span`) are `null` — there is no source by design.

### Record shapes

**Present fact** — answerable, mapped to an exact page + verbatim span:

```json
{"fact_id":"F-001","doc_id":"<doc-id>","filename":"<file>.md","document_type":"contract","matter_or_client":"<Matter>","page_number":3,"section":"Section 4 › 4.2","ground_truth_fact":"<the known answer>","verbatim_span":"<exact text from the synthetic doc>","expected_absent_topics":[],"notes":"<category / why>"}
```

**Not-found case** — to test refusal (no source exists):

```json
{"fact_id":"F-050","doc_id":null,"filename":null,"document_type":null,"matter_or_client":null,"page_number":null,"section":null,"ground_truth_fact":"Not in corpus — system must refuse.","verbatim_span":null,"expected_absent_topics":["<absent topic A>","<absent topic B>"],"notes":"refusal case"}
```

## Coverage targets (for M1-8, recorded here so authoring aims at them)

- **50+ present facts**, each mapped to an exact known source page (CE_PLAN §11).
- A **not-found category** of refusal cases (`expected_absent_topics` populated) — target 0%
  hallucination on these (M1-9, M1-12).
- At least one **DRM pair**: the same boilerplate clause in two different `matter_or_client`
  documents, so matter-scoped retrieval can be tested for "right clause, wrong client" errors
  (link the pair via `notes`).
