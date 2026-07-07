# Competitive Landscape: AI Legal Document Intelligence (as of July 7, 2026)

_Agent report, verbatim (formatting lightly adjusted). Method: 5 parallel research threads (~120
searches/fetches), followed by an adversarial fact-check pass on the 10 most load-bearing claims.
Pricing marked (unverified) where only third-party estimates exist._

**Headline conclusion:** The cell docuchat occupies — one-click local desktop app +
legal-specific + mechanically verified page/span citations + free/open-core — **is empty as of
mid-2026**. Nobody combines all four. But each ingredient individually is under attack: local
doc-chat is being commoditized by free OSS (AnythingLLM, Lavern), citation checking is converging
from multiple directions (Midpage, Clearbrief, GC AI), and the privilege argument just became
case law working in your favor (*U.S. v. Heppner*). The window is real but time-boxed.

## 1a. Cloud incumbents

- **Harvey** — sales-gated; secondhand ~$1,200-2,000/seat/mo mid-market, $50k-300k+ annual
  contracts (unverified; eesel.ai 2026). Cloud (Azure); no on-prem. Self-reported ~0.2%
  claim-level hallucination on BigLaw Bench (harvey.ai/blog/biglaw-bench-hallucinations);
  LLM-based citation matching, no independent audit. Deposition summarization workflows
  (Releasebot Jul 2026). BigLaw/enterprise.
- **CoCounsel (Thomson Reuters)** — partially public via configurator: solo all-states Westlaw
  Advantage + Essentials = $639.20/user/mo 1-yr; tiers ~$104-639 (TR configurator; CostBench Jun
  2026). Cloud only. "Grounded in Westlaw" + KeyCite; Stanford found 33-34% hallucination on the
  2024-era Westlaw AI (JELS 2025). Deposition prep + transcript review (Casetext heritage).
- **Lexis+ with Protégé** — sales-gated; ~$128-494/user/mo (unverified). Cloud; **BYOK
  customer-held encryption keys added May 7, 2026** (LawSites) — closest incumbent move toward
  customer data control, still not on-prem. May 2026 Shepard's Verify Trust Markers check cites
  *exist*, not that they *support*.
- **Spellbook** — ~$99-350/user/mo (unverified). Cloud Word add-in; contract-grounded; markets
  zero-data-retention with OpenAI + Anthropic as the privacy answer (spellbook.legal/security).
  $50M Series B Oct 2025.
- **Paxton AI** — **PUBLIC $499/user/mo or $2,999/yr** (verified from paxton.ai/pricing 7/7/26;
  circulating $199 is stale). Cloud. AI Citator verifies cites exist; self-reported 94% on the
  Stanford benchmark. Medical chronologies (PI); "Casetext alternative."
- **Robin AI** — **dismembered**: managed services to Scissero Dec 2025; Microsoft acqui-hired
  the ~18-person tech team into the Word org Jan 2026 (Artificial Lawyer; Legal IT Insider).
  Strategic signal: Microsoft may build legal AI natively into Word.
- **Luminance** — enterprise licenses hundreds of thousands/yr (unverified); on-prem installs
  offered for data-residency enterprise deals. CLM, no case-law verification.
- **Everlaw** — per-GB sales-gated (~$18-35/GB/mo unverified); Oct 2025 Deposition Analyzer +
  Review/Writing Assistant folded into base rate free (LawSites Nov 2025). Cloud only; FedRAMP.
  **Deep Dive: cited Q&A across TB-scale corpora (GA Oct 2025)** — the closest cloud analog to
  docuchat's roadmap goal.
- **Relativity (aiR)** — consumption per-GB; aiR for Review/Privilege/Case Strategy standard at
  no extra cost early 2026. **Relativity Server (on-prem) sunsetting — no new matters after Jan
  1, 2028**, gen AI cloud-only (LawSites Jan 2025) — the biggest on-prem legal platform is
  EXITING the category, stranding privacy-first demand.
- **Clearbrief** — **$300/user/mo** Solo & Small Teams. Cloud Word add-in. **The closest
  citation-trust competitor:** sentence-level matching of assertions to record evidence,
  color-coded match scores, hallucinated-cite check via Lexis; Legalweek 2026 Litigation Tech of
  the Year. Depo transcript summaries, cite-to-depo-page. Tiny ($8.2M raised).
- **Casetext (heritage)** — dead; standalone shut down April 1, 2025 post-$650M TR acquisition;
  legacy solos ($40-110/mo anchors) forced onto Westlaw bundles at ~5-10x (magnitude unverified).
  **The orphaned segment is docuchat's beachhead**; Paxton, NexLaw, August all chase it.

## 1b. Transcript/deposition tools

- **Steno Transcript Genius** — free with Steno depositions; Q&A pinned to testimony,
  contradiction detection; $49M Series C Mar 26, 2026 (PR Newswire).
- **Parrot** — bundled into court-reporting fees; page-line summaries, A/V sync; acquired by
  Filevine Apr 2025 (Filevine also sells real-time Depo CoPilot).
- **Lexitas Deposition Insights+** — bundled; 4 summary types incl. page-line; 100k+ summaries.
- **Esquire Intelligent Summary+** — hyperlinked page/line cites.
- **vLex Vincent (now Clio)** — hover-to-verify quotes; MP3/MP4 uploads; contradiction surfacing.
  Clio closed the **$1B vLex acquisition Nov 2025** + $500M Series G at $5B (LawSites).
- **Skribe.ai** — $379/hr live depo, video-synced transcript.
- **CaseMark / Dodonai** — from $25/summary; $0.02-1/page. **Depo summaries are commoditizing
  toward free/pennies.**
- **TranscriptPad** — $89.99 one-time or $600/yr LIT Suite; **LOCAL (iPad, offline)**; manual
  issue coding, page/line reports, no gen AI. Proof local+solo+litigation sells.
- **August** — $375/mo self-serve, launched Jan 2026 explicitly for solos "left behind by BigLaw
  tools" (LawSites).
- **DigitalOwl** — from $400/mo; click-to-evidence into medical records.

## 1c. Local / on-prem / self-hosted — THE KEY CELL

**True local (attorney's own machine):**
- **Elephas** (elephas.app) — closest commercial neighbor: Mac-native, marketed at lawyers,
  optional 100% offline via Ollama, per-matter knowledge bases, solo pricing. **But:**
  general-purpose, no legal PDF/Bates handling, no citation verification, macOS-only.
- **Generic OSS lawyers actually use:** AnythingLLM (open-source, Ollama-native), LM Studio, Msty,
  Jan, GPT4All, Open WebUI. Lawyer-targeted setup guides proliferating (Local AI Master Apr 2026;
  Medium/CodeX 2026). DIY, no legal citation layer, no attorney first-run UX.
- **Legal-specific OSS:** **Lavern** (Apache 2.0 multi-agent legal system, Jun 2026, LawSites),
  LawGlance (statute RAG). **No credible OSS project does legal doc chat with verified page/span
  citations as a packaged desktop app.**

**On-prem server (firm data center):** Zanus AI (air-gap appliance, cited answers, no public
price), Luminance enterprise installs, Reveal Private Deployment (harvesting Relativity Server
refugees), Venio, ayfie. All firm-level, none solo-priced.

**Private cloud/VPC (still cloud):** Alexi Private Cloud (Jun 2025), Lexis Protégé BYOK
(May 2026), Jylo. The incumbents' answer — contractual privacy that deliberately blurs "private."

**Verdict: nobody occupies local + solo + legal-specific + verified citations.** Elephas lacks
legal + verification; Zanus lacks solo + desktop; Clearbrief lacks local + price; TranscriptPad
lacks AI; OSS lacks packaging + verification.

## 2. The Citation-Trust Angle

- Charlotin's AI Hallucination Cases database: ~1,450-1,490 tracked decisions worldwide by May
  2026, 1,000+ US (damiencharlotin.com/hallucinations; GC AI tracker).
- Escalation: Wadsworth v. Walmart (Feb 2025, pro hac revoked — fakes from the firm's OWN
  in-house AI tool); Johnson v. Dunn (Jul 2025, partners removed + bar referral); Coomer v.
  Lindell (renewed sanctions Apr 2026); **Couvrette (D. Or., Apr 2026): ~$110k combined, largest
  to date** (ABA Journal); Nebraska attorney indefinitely suspended (Apr 2026); **LNU v. Blanche,
  No. 24-4790 (9th Cir. Jun 3, 2026) — first precedential federal appellate sanctions opinion**
  (opinion PDF verified; Volokh).
- Rules: **NY 22 NYCRR Part 161 (effective Jun 1, 2026)** — signing a filing certifies careful
  independent review (nycourts.gov). 600+ judicial AI entries, 100+ requiring
  disclosure/verification (Law360 tracker). ABA Op. 512 + Texas Op. 705 + 35 state bars impose a
  verification duty. CNA tells firms to prohibit relying on AI citations without human
  verification; 60%+ of carriers now ask about AI at renewal (legalaigovernance.com).
- Stanford RegLab (peer-reviewed JELS 2025): Lexis+ AI >17%, Westlaw >34% hallucination despite
  "hallucination-free" marketing. Best independent scores (Vals, Oct 2025) top out ~78-81%.

**Is anyone doing mechanical span verification? Not fully — but the flank is closing:** Midpage
red-underlines quotes failing verification (quotes only); Clearbrief does sentence-level
assertion-to-record matching (model-similarity scoring, post-hoc on a draft, not generation-time
blocking); GC AI "Exact Quote" advertises character-locked citations; Paxton/Shepard's Verify
check existence, not support; Harvey's verification is itself LLM-based, unaudited.

**The specific claim "every sentence in every answer is programmatically checked against the
exact source span with page+span pinpoint, and unverifiable output is blocked" is unclaimed by
anyone** — confirmed by the AI Law Librarians synthesis (Feb 19, 2026: no vendor offers automated
per-claim verification). Caveat: frame it as verifying *document* assertions (the Wadsworth
lesson: in-house "grounded" tools fail too); publish the verification mechanism (open-core helps)
and invite independent benchmarking.

## 3. The Privilege/Confidentiality Angle

**Heppner is real and is the single best marketing event.** *United States v. Heppner*, No. 25
Cr. 503 (JSR) (S.D.N.Y.), bench ruling Feb 10, 2026, written opinion Feb 17, 2026 (verified via
docket + DOJ; opinion mirrored by Akin). Holding: defendant's **consumer Claude** chats
organizing his defense were neither privileged nor work product: (1) an AI is not a lawyer,
(2) **the consumer terms of service (data collection, third-party disclosure) destroyed any
reasonable expectation of confidentiality**, (3) counsel didn't direct the use. Key dicta:
outcome might differ for counsel-directed use of a **non-public tool** — precisely a local-first
architecture (WLF Apr 2026; Harvard Law Review Blog Mar 2026).

Honest split: ***Warner v. Gilbarco*** (E.D. Mich. Feb 10, 2026) protected a pro se plaintiff's
ChatGPT materials as work product (Proskauer; Akin on the divergence). But the surrounding record
pushes one way: NYT v. OpenAI preservation order (all consumer ChatGPT logs incl. user-deleted
preserved; 20M-conversation sample ordered produced Jan 2026); Altman: "no legal confidentiality"
for ChatGPT (Jul 2025, TechCrunch); Anthropic consumer terms (Aug 2025): training opt-out
default, retention up to 5 years; Fortis v. Krafton (Del. Ch. Mar 2026): CEO's ChatGPT logs
became central evidence. Bar guidance: ABA 512 informed consent before client data in
self-learning tools; **California (May 2026) moving AI duties into enforceable Rules of
Professional Conduct** — Rule 1.6 "reveal" includes inputting client info into AI, plus a duty to
verify every AI output (LawSites May 2026); NC (Jan 2026), Texas 705, DC 388, Florida 24-1,
Oregon 2025-205 all in the same direction.

**How competitors answer the objection:** uniformly with *contract*, not *architecture* — SOC 2 +
no-training flow-downs + ZDR + tenant isolation + BYOK. Spellbook actively argues self-hosting is
"costly, fragile" vs managed ZDR — expect this FUD in every deal. Docuchat's counter: Heppner
turned on *terms of service*; local-first has no terms to turn on. Market as "confidentiality by
architecture, not by contract," never as a legal guarantee.

## 4. Pricing White Space

Solo pricing mid-2026: Westlaw solo floor ~$133/mo, all-states+AI ~$400-639 (configurator);
Lexis solo from ~$114 + unpublished Protégé premium; Paxton $499 (verified); Alexi $299
(unverified); Clearbrief $300; August $375; Clio Duo needs the $129 Complete tier; MyCase IQ $89;
**Midpage $99/mo (verified, cheapest legal-specific)**; ChatGPT Plus $20. Free: vLex Fastcase via
60+ bar associations (research, not doc chat); Steno depo summaries free with reporting.

**The $20-50/mo legal-specific slot is empty.** 71% of solo firms report using AI (Clio 2025);
**62% of solos use/consider ChatGPT** (ABA Tech Survey via LawSites Mar 2025) — solos are already
doing exactly the unsafe thing Heppner punishes. Displaced Casetext solos carry $40-110/mo
anchors.

**Local-first demand evidence (honest read: real pain, thin direct WTP):** HN thread on Heppner
("running your own LLM on your own hardware..."); one documented $35,000 + $1,200/mo self-hosted
Llama 3 70B RAG build for a mid-size firm (r/n8n May 2025); lawyer-specific local-LLM how-to
content proliferating; a vendor blog pegs solo WTP "under $50/month" (self-serving but consistent
with the gap). Gap: no proven cohort saying "I'd pay $30/mo for local." The realistic competitor
at that price is **free OSS**, so the paid tier must sell convenience + legal verification +
support, not local inference itself.

## 5. Threats (ranked)

1. **OSS commoditization (highest, immediate).** AnythingLLM/LM Studio/Msty/Jan free local doc
   chat; Lavern free legal-specific Apache 2.0 (Jun 2026). Defense: verification layer,
   legal-grade PDF/OCR/Bates/exhibit handling, transcript page-line awareness, zero-config
   install — the moat is never "local" alone.
2. **Local model quality on long documents.** No open-weight model has a published legal
   benchmark; long-context degradation documented for small models. Mechanical verification is
   the right mitigation (converts a quality problem into a coverage problem), but expect "local
   models are worse" in every bake-off. Publish your own benchmark.
3. **Hardware ceiling.** AI PCs are 55% of 2026 shipments (Omdia) but the attorney installed base
   skews old/8-16GB; near-term TAM is disproportionately Apple Silicon Macs. Ship a graceful
   small-model tier.
4. **OS-level local AI making "local" table stakes (12-24mo).** Apple Foundation Models 3 (Jun
   2026) gives every Mac app a free on-device ~3B model + OCR; Microsoft Phi Silica expanding.
   These commoditize *inference*, not the legal workflow. Real second-order threat: **Microsoft
   building legal AI into Word** (the Robin AI acqui-hire points there).
5. **Incumbents going private-ish (low near-term).** No evidence Harvey/TR/Lexis will ship
   on-prem; BYOK/VPC are contractual privacy. Watch: Lexis BYOK muddying "private"; Everlaw Deep
   Dive already delivers thousand-document cited Q&A in cloud.
6. **Naming collision (housekeeping, act now):** **docuchat.io is an active, established cloud
   "DocuChat" doc-chat SaaS** ($14-31/mo, EU/GDPR positioning) — verified live 7/7/26. Real
   trademark/SEO conflict + "isn't DocuChat a cloud tool?" confusion undermining the local-first
   message. Consider renaming before launch marketing.
7. **Depo-summary commoditization.** Steno gives AI summaries away free with reporting; Dodonai
   at pennies/page. Sell privacy + cited cross-transcript search at case scale, not summaries.

### Strategic synthesis

The four-quadrant cell (local, solo, legal, mechanically verified) is empty; the two macro events
of early 2026 — Heppner (privilege) and LNU v. Blanche + NY Part 161 (citation certification) —
are the demand drivers for each half of the wedge. The credible bear case is not an incumbent; it
is free OSS plus OS-level models eroding "local" while docuchat is still building. Speed to a
polished, verifiable v1 and an independent benchmark submission matter more than feature breadth.
Unverified items to re-check before publishing externally: all sales-gated seat prices, the
Casetext 5-10x repricing magnitude, attorney-hardware capability (no survey exists).
