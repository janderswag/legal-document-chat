# G-DIG inventory build report

## Revision 2 (post first G-DIG run, coordinator feedback)

1. **Renfrew matter corrected** to `Pemberton Logistics (Nimbus MSA)` for all
   `renfrew_demand_letter.pdf` entries — the store's actual `matter` value was
   verified by querying the LanceDB chunks table directly; `golden_manifest.jsonl`
   was right, `corpus_manifest.jsonl` wrong. (Resolves the ambiguity flagged in
   "Matter field" below.)
2. **All `span_contains` needles shortened** to the distinctive core — the literal
   date / amount / name plus at most a few anchoring words — because the scorer
   matches bidirectionally against tight extractor spans (e.g. "entered into and
   effective as of March 14, 2024" → "March 14, 2024"; "shall not exceed
   $568,200" → "$568,200"; party needles are the bare entity name).
3. **One collapse:** MSA Article 7.2 previously had two entries ("After the first
   ninety (90) days, either party may terminate" and "ninety (90) days' prior
   written notice"). Both facts live in the same sentence and both cores reduce to
   a 90-day period, so they were collapsed into the single entry "ninety (90)
   days' prior written notice". Total is now **38** (was 39): party 8,
   date_event 21, amount 9 (MSA date_event 9 → 8). No other same-core duplicates
   existed — checked mechanically: zero duplicate (doc, type, normalized-needle)
   triples.
4. Re-validated: JSON parses; all 38 needles verbatim-verified against the source
   text under the verifier normalization (**38/38, 0 failures**).

Sections below are the revision-1 report, kept for provenance; where they conflict
with the above (counts, renfrew matter), revision 2 governs.

## Docs considered and chosen

Candidates surveyed from `eval/corpus_manifest.jsonl` (21 entries, 4 document types:
contract, pleading, correspondence, public_legal_text). `public_domain_statutes.pdf`
was excluded — it's reference text, not matter-scoped (matter_or_client = "Public
Domain (Reference)"), so it has no parties/deadlines/amounts a digest would surface.

Chose **4** docs (source text read end-to-end from the `.md` sources under
`documents/synthetic_corpus/`, which are the pre-PDF text used to build the corpus):

1. **nimbus_pemberton_msa.pdf** — long MSA/contract (the plan's "one long
   MSA/contract" slot). Richest single doc: term, fee, notice, and liability
   structure.
2. **holloway_v_drakemoor_complaint.pdf** — pleading (the plan's "one pleading"
   slot). Short (3 pages) — only 6 facts, all a competent reader would want
   (parties, incident/contract/filing dates, damages figure).
3. **renfrew_demand_letter.pdf** — correspondence (the plan's "one correspondence
   set" slot). A 2-page demand letter referencing the Nimbus MSA above — same
   fact-cluster, different document.
4. **greenfield_castellano_lease.pdf** — a second contract (lease), added because
   docs 1-3 alone totaled only 27 facts, short of the ~30-60 target. This is a
   substitution for the plan's single "correspondence set" being too thin
   (`pemberton_renewal_email.txt`, the only other same-matter correspondence
   candidate, is a 2-sentence internal email with exactly one extractable fact —
   an amount — and no party or date; adding it would have contributed almost
   nothing). The lease is a different matter (Castellano Studios), independently
   rich (parties, term/renewal dates, four distinct dollar figures), and gave a
   fourth clean party/date/amount cluster instead.

## Entry counts

| doc | party | date_event | amount | total |
|---|---|---|---|---|
| nimbus_pemberton_msa.pdf | 2 | 9 | 3 | 14 |
| holloway_v_drakemoor_complaint.pdf | 2 | 3 | 1 | 6 |
| renfrew_demand_letter.pdf | 2 | 4 | 1 | 7 |
| greenfield_castellano_lease.pdf | 2 | 6 | 4 | 12 |
| **total** | **8** | **22** | **9** | **39** |

## Matter field

`matter` for each entry is the exact `matter_or_client` string in
`eval/corpus_manifest.jsonl` for that filename (that's the field `chunking.py`'s
`load_doc_metadata` reads verbatim into the store's `matter` column — confirmed by
reading `pipeline/chunking.py` lines 40-53 and `pipeline/kb_ingest.py`/`digest.py`'s
`pages_from_store`, which filter on `matter = '<value>'` exactly).

**Ambiguity flagged, not silently resolved:** `eval/corpus_manifest.jsonl` lists
`renfrew_demand_letter.pdf`'s matter as **"Renfrew Holdings (Demand)"**, but
`eval/golden_manifest.jsonl` (fact IDs F-056..F-063) tags the same file with matter
**"Pemberton Logistics (Nimbus MSA)"** — and the letter's content is unambiguously
about the Nimbus MSA (it demands payment under that agreement). This is a
pre-existing inconsistency between the two manifest files, not something I
introduced. I used the `corpus_manifest.jsonl` value ("Renfrew Holdings (Demand)")
because that file is the one `chunking.py` actually reads to populate the store's
`matter` column — golden_manifest is not consulted by the ingest/chunking path. If
the real eval store ends up built with the other value, every `renfrew_demand_letter.pdf`
row's `matter` field in `eval/digest_inventory.json` needs a one-line find/replace.

## Exclusions

- Attorneys/law firms (Sabrina Voss, Tobias Renfrew, Renfrew & Volk LLP, Voss &
  Harland LLP) were **not** logged as `party` facts. The digest schema's own
  `role` examples (`provider/client/plaintiff/defendant/landlord`) are all
  parties-to-the-matter, not counsel of record — an attorney's byline isn't the
  same class of "who's in this dispute" fact.
- Punitive/exemplary damages in the Holloway complaint ("according to proof") —
  no verbatim numeric span to anchor an `amount` fact to.
- `defined_term` and `key_ref` type facts (e.g., "Statement of Work", Invoice Nos.
  INV-20418/20455/20489, Case No. CV-2024-08817, MSA Section 6.1) were out of
  scope — the task asked only for party/date_event/amount.
- Scanned twins (`scan_*.pdf`) were not given separate entries; only the
  born-digital filename is referenced, matching the convention in
  `eval/golden_manifest.jsonl` and the example file.

## Validation

- `python3 -c "import json; json.load(open('eval/digest_inventory.json'))"` — parses
  cleanly.
- Every `span_contains` fragment was checked against the actual doc text
  (`documents/synthetic_corpus/*.md`, the pre-PDF sources) by reimplementing
  `verifier._norm_map`'s exact normalization (lowercase, whitespace collapse, quote
  drop, hyphen-linebreak join) and confirming the normalized needle is a substring
  of the normalized haystack: **39/39 passed, 0 failures**.

## File not committed

`eval/digest_inventory.json` is left untracked in the working tree, per instructions
(`git status --short eval/` shows it as `??`).
