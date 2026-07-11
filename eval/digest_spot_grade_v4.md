# G-DIG value-correctness spot grade — digest-v4 (gate Step 4)

- **Extractor version:** `digest-v4 qwen3:14b` (pipeline/digest.py `EXTRACTOR_VERSION`)
- **Date:** 2026-07-10
- **Branch:** feature/matter-digest (extraction run against `pipeline/.lancedb`; graded via
  an isolated git worktree after the shared checkout was switched to `main` by a concurrent
  process mid-task — see Note at bottom)
- **Method:** `digest.pages_from_store` + `digest._groups` + `digest.extract_group(group, doc_id=0)`,
  the real extractor, no mocks. Two docs, zero facts dropped at the mechanical write gate.
- **Docs:** `nimbus_pemberton_msa.pdf` (Pemberton Logistics (Nimbus MSA)) — 22 facts extracted;
  `greenfield_castellano_lease.pdf` (Castellano Studios (Greenfield Lease)) — 24 facts extracted.
  46 facts total, 22 graded below (all 5 fact types, both docs, plus every anomaly found).

## CRITICAL check: date_iso literal-presence

**Zero non-null `date_iso` values across all 46 extracted facts (checked programmatically).**
No date_iso violation is possible in this run — the mechanical gate in `gate_facts` correctly
nulled every `date_iso` it produced, including on two facts that are otherwise bogus date_events
with no date content at all (rows 21–22 below). Docuchat did not store a single fabricated or
non-literal date in this run.

## Graded facts

| # | Doc | Fact type | Span (verbatim, verified) | value_json (key fields) | Verdict | Note |
|---|-----|-----------|---------------------------|--------------------------|---------|------|
| 1 | MSA | party | "Nimbus Analytics LLC, a Delaware limited liability company (\"Provider\")" | name=Nimbus Analytics LLC, role=provider, org_form=LLC | Faithful | |
| 2 | MSA | party | "Pemberton Logistics Inc., an Ohio corporation (\"Client\")" | name=Pemberton Logistics Inc., role=client, org_form=Inc | Faithful | |
| 3 | MSA | date_event | "March 14, 2024 (the \"Effective Date\")" | kind=event, label=Effective Date, date_text=March 14 2024, date_kind=explicit, date_iso=null | Faithful | date_iso conservatively left null despite a genuine explicit calendar date — a recall miss, not a fabrication; no violation |
| 4 | MSA | defined_term | "\"Services\" means the analytics, dashboarding, and reporting services..." | term=Services | Faithful | |
| 5 | MSA | amount | "$47,350" | value=$47,350, currency=USD, purpose=monthly service fee | Faithful | purpose correctly drawn from surrounding sentence (§4.1) |
| 6 | MSA | date_event | "payable in advance on the first day of each calendar month." | kind=obligation, date_kind=relative, anchor=calendar month | Faithful | |
| 7 | MSA | date_event | "Provider may adjust the monthly service fee... upon sixty (60) days' written notice." | kind=obligation, date_text=sixty (60) days, **date_kind=explicit**, anchor=null | Debatable | a 60-day notice window is a duration, not "a complete calendar date... written" — date_kind should be relative, as the model correctly labeled the analogous net-30 fact (#8). No date_iso stored, so no downstream harm, but the field is internally inconsistent with sibling facts. |
| 8 | MSA | date_event | "All invoices are due net thirty (30) days from the invoice date." | kind=obligation, date_kind=relative, anchor=invoice date | Faithful | |
| 9 | MSA | amount | "one and one-half percent (1.5%) per month" | value=1.5%/month, currency=null, purpose=late charge | Faithful | |
| 10 | MSA | date_event | "This Agreement shall have an initial term of thirty-six (36) months, commencing on the Effective Date." | kind=event, date_text=36 months, date_kind=explicit, **anchor=null** | Unfaithful | span literally states "commencing on the Effective Date" — anchor should be "Effective Date" but is null; date_kind=explicit is also wrong for a duration (same issue as #7) |
| 11 | MSA | amount | "$568,200" | value=$568,200, currency=USD, purpose=Provider's aggregate liability under this Agreement | Faithful | |
| 12 | MSA | key_ref | "8829 Marlberry Court, Suite 410, Dover, DE 19901" | ref_type=address, ref_value=(same) | Unfaithful | system prompt scopes key_ref to invoice/case/claim/docket/**section number** identifiers only ("Do NOT emit defined or quoted phrases as key_ref"); a street address is not an identifier number — fact_type is out of scope, even though the span itself is correctly located |
| 13 | Lease | party | "Greenfield Property Holdings LLC (\"Landlord\")" | name=Greenfield Property Holdings LLC, role=landlord, org_form=LLC | Faithful | |
| 14 | Lease | party | "Yara Castellano, an individual doing business as Castellano Studios (\"Tenant\")" | name=Yara Castellano, role=tenant, org_form=individual | Faithful | |
| 15 | Lease | party | (same span as #14) | name=**Castellano Studios**, role=tenant, org_form=individual | Unfaithful | duplicate party emitted from the identical span as #14; "Castellano Studios" is a d/b/a trade name, not "an individual" — org_form is wrong for this name, and splitting one party mention into two facts contradicts the "never emit the same fact twice" instruction |
| 16 | Lease | date_event | "commence on July 1, 2023" | kind=event, date_kind=explicit, date_iso=null | Faithful | same conservative-null pattern as #3 |
| 17 | Lease | date_event | "for a period of sixty (60) months" | kind=obligation, date_kind=relative, **anchor=July 1, 2023** | Faithful | correctly anchors the duration to the commencement date — the pattern MSA fact #10 got wrong |
| 18 | Lease | amount | "$9,275" | value=$9,275, currency=USD, purpose=monthly base rent | Faithful | |
| 19 | Lease | amount | "$250 plus five percent (5%) of the overdue amount" | value=(same), currency=USD, purpose=late charge | Faithful | |
| 20 | Lease | amount | "$18,550" | value=$18,550, currency=USD, purpose=security deposit | Faithful | |
| 21 | Lease | date_event | "IN WITNESS WHEREOF, the parties have executed this Lease." | kind=event, label=Execution of Lease, date_text=(entire span), date_kind=**explicit**, date_iso=null | Unfaithful | the span contains **no date information at all** — a witness clause, not a date. Labeling this date_kind=explicit falsely implies a calendar date is present. Gate correctly nulled date_iso, so no bad date was stored, but the fact itself should not have been classified as a date_event. |
| 22 | Lease | date_event | "16.1 This Lease shall be governed by the laws of the State of Ohio." | kind=obligation, label=Governing Law, date_text=(entire span), date_kind=**explicit**, date_iso=null | Unfaithful | same bug as #21: a governing-law clause has zero date content; date_kind=explicit is wrong. Two instances of this bug in one 3-page doc suggests a systematic model confusion between "explicit clause language" and "explicit calendar date." |

## Verdict counts (22 graded)

| Verdict | Count | Facts |
|---|---|---|
| Faithful | 16 | #1,2,3,4,5,6,8,9,11,13,14,16,17,18,19,20 |
| Debatable | 1 | #7 |
| Unfaithful | 5 | #10, #12, #15, #21, #22 |

## Summary

- **date_iso / CRITICAL:** none found. No non-literal date was stored in either document; the
  mechanical write gate held even on the two bogus date_event facts (#21, #22).
- **Real bug pattern found:** the extractor twice classified clauses with **zero date content**
  (a witness/execution clause, a governing-law clause) as `date_event` facts with
  `date_kind=explicit`. Harmless today only because `date_iso` stayed null by the gate's design;
  worth a prompt fix (date_event should require the span to contain actual date/duration
  language) before this ships past digest-v4.
- **Secondary pattern:** duration facts anchored implicitly in their own span text (e.g.
  "commencing on the Effective Date") sometimes get `anchor=null` and `date_kind=explicit`
  instead of `relative` (MSA #10 vs. the correctly-anchored Lease #17) — inconsistent, not
  dangerous, since no date_iso follows from either labeling.
- **key_ref scope creep:** one fact (`ref_type=address`) fell outside the system prompt's
  identifier-only scope for key_ref. Not dangerous (span is correctly located) but is a
  fact_type misclassification worth tightening in the prompt, mirroring the section/case/claim/
  invoice/docket restriction already called out for D-*-style key_ref bounding.
- **Duplicate/party split:** one d/b/a tenant was split into two party facts from the identical
  span, one of which mislabels a trade name as `org_form=individual`.

## Note on environment

Mid-task, the shared git working tree at `/Users/janderswag/projects/legal-doc-intelligence` was
switched from `feature/matter-digest` to `main` by what appears to be a concurrent process
(git status changed from "On branch feature/matter-digest" to "On branch main", and
`pipeline/digest.py` / `verifier.py` etc. disappeared, since they only exist on
`feature/matter-digest`). The extraction itself had already completed successfully before the
switch (results saved to scratch). To read page text for grading context without disrupting
whatever the other process is doing on `main`, a temporary git worktree was used
(`git worktree add .../wt-digest-v4 feature/matter-digest`) rather than checking out the branch
in the shared tree. No product code was modified and nothing was committed on either branch.
