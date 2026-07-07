# Where Attorney Hours Actually Go — Jobs-to-be-Done and Feature Gaps for docuchat

_Agent report, 2026-07-07, verbatim (formatting lightly adjusted). All sources cited inline;
vendor-published figures flagged._

**Headline context.** Lawyers bill only ~2.6-2.9 hours of an 8-hour day; utilization averaged 38%
in 2025 (Clio Legal Trends benchmarks 2025). AI adoption exploded (79% per Clio LTR 2025; 83%
have access per the Factor ALSP survey, Mar 2026) but trust collapsed to ~22% (see §4). That gap
— high adoption + low trust + verification burden — is docuchat's wedge.

## 1. Jobs-to-Be-Done Inventory (ranked by hours consumed x willingness to pay)

1. **Deposition digesting/summaries** — ~20-25 pages/hr manual; a 200-page depo = ~8 paralegal
   hours. Outsourced: **$2.25/page human** (DepoExpress, Ditto), **$1/page AI** (SmartDepo,
   Dodonai); $300-$2,000 per transcript (Magna).
2. **Discovery review + privilege logs** — document review = ~70-73% of total eDiscovery cost;
   RAND: ~$14k review per GB. Privilege logging "one of the most time-consuming, expensive, and
   contentious components of discovery" (V&E 2024; ABA Business Law Today Nov 2024). Solos
   underserved: only 27% have litigation support software vs 73% of large firms (ABA 2024
   Solo/Small Firm TechReport).
3. **Medical-record review/chronology (PI, med-mal)** — outsourced nurse/paralegal ~$25-50/hr,
   per-provider fees ~$150; PI files routinely 800+ pages (MedSum Legal; Medico Legal Request).
4. **Chronology/fact-timeline construction** — CaseFleet charges $30-140/user/mo (AI tier $140).
5. **Contract review/clause extraction** — average lawyer took 92 min per 5-NDA set at 85%
   issue-spotting accuracy (LawGeex 2018, vendor study, still most-cited); contract review +
   summarization are the dominant in-house AI use cases (Factor, Mar 2026).
6. **Lease abstraction (CRE)** — 3-8 hrs/lease manual, $200-500/lease staff time; AI vendors
   ~$10/lease claiming 95-98% (vendor claims; Lextract 2026).
7. **Citation/record checking in briefs** — now existential: 1,313+ court proceedings involving
   AI-fabricated content as of April 2026 (496 involving licensed attorneys); sanctions to
   $55,597 in one matter; incidents 2-3/day late 2025 (GC AI tracker; HAQQ; Norton Rose
   Fulbright 2026).
8. **Exhibit management** — manual stamping/numbering/hyperlinking to testimony (AgileLaw; One
   Legal). Small-firm tools are presentation-oriented.
9. **Intake-document triage** — poorly benchmarked; among highest-strain tasks (Clio 2025 LTR).

**WTP signal check:** attorneys already pay per-page cash for #1 and #3, 70% of eDiscovery
budgets for #2, and $30-140/user/mo for #4. #7's WTP is driven by fear (sanctions) — a stronger
buying emotion than efficiency.

Hype check: Clio's "74% of billable work could be automated" is a vendor task-taxonomy estimate.
MIT Technology Review (Dec 2025) reported a study finding **average AI time savings of ~3%**,
with users reinvesting savings into correcting AI errors. Truth is task-dependent: mechanical
extraction/summarize jobs show real gains; judgment jobs don't.

## 2. Fit Against Docuchat's Hard Constraints (~14B local, cited+verified, locate-and-summarize)

- **Strong fit:** deposition digesting (pure locate-and-summarize; page:line citation is exactly
  the verified-span primitive); transcript search/impeachment lookup; chronology construction
  (only explicitly dated facts, never inferred); record-cite checking of drafts vs the loaded
  corpus; clause/term extraction + contract/lease abstraction (per-field citation + honest "not
  present").
- **Possible:** medical-record chronology (bottleneck is OCR/scan quality, not the LLM);
  discovery first-pass topical triage (responsiveness/privilege are legal calls — surface and
  organize only); privilege log generation (metadata table for attorney-selected docs is
  mechanical; drafting privilege descriptions is judgment, out); exhibit management search side
  (Bates-aware retrieval); contradiction candidates (surfacing paired quotes is retrieval;
  declaring "contradicted" is a legal conclusion — the framing is the whole product decision).
- **Out of scope:** case-law citation checking (requires Westlaw/Lexis, which a no-cloud tool
  cannot query — do not pretend otherwise; scope to record cites); brief/motion drafting (where
  the sanctions bodycount is); deadline/docket management, filing (autonomous actions
  prohibited).

## 3. Transcript-Specific Value

**Pricing to displace:** human depo summaries $2.25/page standard 5-day turnaround; market range
$300-$2,000/transcript; AI services ~$1/page (SmartDepo; Dodonai from $30/mo for 200 pages). The
transcript itself costs $3-8/page from the reporter, ~75 pages per deposition hour (full-day depo
~200-300+ pages). A litigation-heavy solo taking 3-4 depos/month spends $600-2,400/mo on
summaries or ~24-32 paralegal hours. **A concrete, displaceable budget.**

**Delivery formats docuchat must ingest:** .PTX (RealLegal E-Transcript — proprietary standard,
signed, hyperlinked word index; exportable to PDF/Word); ASCII/.txt (ordered specifically for
litigation tools; preserves page/line structure as plain text); PDF full-size and condensed 4-up
with word index (the most common working copies).

**What litigators actually need from transcript search:** pinpoint page:line citations on every
result (impeachment is performed by reading from page and line — Holland & Knight impeachment
guide); by-witness and by-topic digests (admissions, denials, "I don't recall" inventory);
cross-transcript consistency views (same witness across deposition vs declaration vs
interrogatory answers; FRCP 32(a)(2)); exportable excerpt tables in Word (the artifact in the
trial binder is a table, not a chat log); errata awareness (a corrected answer supersedes the
original).

## 4. Trust and Quality Bar

**The ~22% statistic, verified and updated:** Factor ALSP survey (March 2026, 200+ in-house and
law firm leaders): **only 22.1% report high trust in AI outputs; 69.7% of outputs require
targeted edits or extensive rework**; high-trust teams are 3x more likely to report positive ROI
(Artificial Lawyer, Mar 23, 2026). Corroborating: Paragon Legal survey (Feb 2026, 250+): ~20%
high trust, 42% little-to-no trust, 67% have had to override/correct AI output, 58% would not
feel comfortable submitting an AI-drafted document to a court or regulator (Legal Cheek).
Wolters Kluwer 2026: trust/reliability concerns at 37% amid 92% adoption.

**Why the distrust is rational:** Stanford found purpose-built legal RAG tools hallucinate 17-33%
(Lexis+ AI, Westlaw AIAR), ~43% raw GPT-4 (Stanford HAI 2024; JELS 2025). Judicial doctrine
hardened to "do not trust until verified" (Thomson Reuters legal blog, 2026).

**What makes attorneys abandon a tool:** (1) errors that are hard to spot, forcing double-checks
of everything so net time saved rounds to zero (MIT Tech Review, Dec 2025); (2) one-trick tools
that don't fit the Word/PDF/binder workflow (HAQQ 2026); (3) rollout without training, quiet
abandonment after the first month (Waybound). Product implication: **the mechanical verification
badge on every span is not a feature, it is the entire retention story**, and any answer that
cannot be verified must visibly say so rather than degrade silently.

## 5. Security, Confidentiality, and What a Local Tool Must DEMONSTRATE

Ethics baseline: ABA Formal Opinion 512 (Jul 2024) under Rule 1.6 — informed client consent (not
engagement-letter boilerplate) before inputting client info into a self-learning tool. **A
genuinely local, non-training tool sidesteps the consent problem entirely — a sellable legal
distinction.** Rule 1.1 Comment 8 makes evaluating the tool the lawyer's personal duty. State
opinions (Oregon 2025-205 etc.) and outside counsel guidelines increasingly restrict cloud AI.

Records retention: client files generally ~5 years (ABA), 6-7 in many states, longer for
minors/criminal (WSBA; ISBA). Docuchat's index/embeddings become part of the matter file: needs
per-matter export and provable deletion. Cyber insurance is now an audit, not a checkbox
(screenshots/policy exports instead of attestations; MFA; at-rest encryption; immutable backups).

**A local tool must demonstrate, not claim:** zero-egress proof (runs air-gapped; "network
activity: none" panel); no telemetry, verifiable; encryption at rest keyed per matter; per-matter
isolation, export, provable deletion; an audit log of every Q/A/citation (Rules 5.1/5.3
supervision; the artifact shown to a judge or client if challenged); a one-page security fact
sheet mapped to cyber-insurance and OCG questionnaire language.

## 6. Top 8 Feature Opportunities (ranked; trap in each)

1. **Transcript-native ingestion + page:line citation engine** (M) — trap: citing PDF page
   numbers instead of transcript page:line; condensed 4-up transcripts, cover pages, errata break
   naive pagination. A wrong page:line cite in court is instantly discrediting.
2. **Deposition digest generator with Word export** (M) — trap: paraphrase drift ("did not recall
   approving" -> "denied approving") — the classic small-model failure. Mitigation is docuchat's
   DNA: quote verbatim, verify the span, label connective tissue as unverified paraphrase. Output
   must be a Word table, not a chat bubble.
3. **Record cite-checker for drafts** (M) — verified/mismatched/not-found report against the
   loaded corpus. Trap: attorneys will expect case-law validation too; must loudly partition
   "record cites: checked" vs "legal authorities: not checkable offline."
4. **Cross-document chronology extractor** (M) — CSV/Word export. Trap: date inference (relative
   dates, ambiguous formats, hallucinated years). Extract only explicit dates with verbatim
   spans; mark relative dates unresolved.
5. **Contradiction-candidate finder** (L) — paired verbatim quotes with both cites. Traps:
   "contradiction" is a legal conclusion (say "candidate inconsistency"); false-positive floods
   burn trust — precision over recall; a 14B model should retrieve and pair, not adjudicate.
6. **Clause/term abstraction tables across document sets** (M) — per-field pin cite, explicit
   NOT FOUND, amendment-chain awareness. Traps: forcing an answer when absent (fabricated renewal
   options are the canonical abstraction error); amendment chains silently superseding base
   terms — extract per-document, surface conflicts, never merge silently.
7. **Provable-privacy pack** (S/M) — network kill-switch with live egress indicator, per-matter
   encrypted stores, audit log, provable deletion, exportable security fact sheet. Trap: claiming
   instead of demonstrating; forgetting the index itself is client-confidential (unencrypted
   embeddings on a stolen laptop = a Rule 1.6 incident).
8. **Medical-record chronology mode for PI** (L) — OCR-hardened, duplicate detection, provider
   index. Trap: the scans are the bottleneck; a misread dosage or date in a demand package is a
   malpractice-grade error. Every extracted value shows its source image crop; low-confidence OCR
   renders as "illegible p.412," never a guess.

**Sequencing logic:** 1 -> 2 -> 3 form one coherent story ("transcripts in, verified digest out,
draft checked against the record") and attack a budget attorneys already spend in cash. 7 is
cheap and wins the *purchase* decision even though it wins no demos. 5 and 8 are moats but only
after the citation engine is bulletproof — both die instantly if a single pin cite is wrong.

**Strategic caution:** the market's stated problem is no longer access to AI (83%) but
defensibility of output (22.1% high trust). Do not market "chat with your documents" — a
commodity claim in 2026. Market **"every answer carries a verified pin cite you can read into the
record."** That is the sentence that matches how the profession now buys.
