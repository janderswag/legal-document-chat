# Adoption Verdict Input — docuchat v0.5.0 vs the Real Alternatives (as of tonight)

Role: market analyst. Date: 2026-07-11, evening (post v0.5.0 release). Builds on
`mkt-attorney-adoption.md` (this morning) and `../2026-07-10-reports/market-2026.md` — competitor
tiers, pricing ladder, survey data, and the Heppner/ABA-512 privilege architecture are established
there and cited by reference. This report answers one question for the owner: **is docuchat,
tonight, valuable enough for an attorney to rationally pick over the alternatives — and which
attorney?**

---

## 1. What changed tonight: the morning's objections, re-scored against v0.5.0

This morning's adoption report (`mkt-attorney-adoption.md` §C–E) named a specific set of
disqualifiers. Tonight's release closes most of the workflow ones:

**CLOSED tonight (v0.5.0):**
- ~~"Multi-minute synchronous spinner with no partial results — the single most disqualifying UX
  gap"~~ → Review is now a streamed background job: skeleton instantly, first clause on screen in
  seconds, ~9s/clause live fill, cancelable. This is exactly the "progressive delivery" fix §C
  prescribed as the only way a local tool competes with sub-minute cloud norms.
- ~~"The review evaporates on navigation — not billable, not defensible, not delegable"~~ →
  Persisted runs, zero-second reopen, staleness flag when the matter's documents change.
- ~~"No save/export = not work product"~~ → Copy / Markdown / **Word red-flag report** export,
  per-clause verification status preserved, retrieval-scope caveat printed on the export. This is
  the Bloomberg-Law red-flag-report genre §D said the grid maps onto.
- ~~"All-or-nothing granularity"~~ → per-clause cells, single-document scope, attorney-declared
  doc-type filter (never guessed), add-your-own-question row.
- (Ingestion side) Gmail now walks labels of any size; email **attachments are searchable child
  documents**; watched folders with live heartbeat; "Every mention" exhaustive true-count search
  promoted and verifier-aligned.

**STILL OPEN (be honest — these survive tonight):**
1. **Not in Word.** No add-in, no Track Changes redlines, no suggested language. Structural, and
   partially deliberate: Vals VLAIR shows AI losing to lawyers at redlining (79.7% human vs
   ~59–65% best AI) and beating them at document Q&A (94.8% vs 70.1%) — docuchat sits on the
   winning side by scope. But it means docuchat does not compete for the negotiation job at all.
2. **No editable checklist/playbook.** A generic clause list tells a transactional attorney what
   they already know; the firm's positions are the value. Queued next cycle.
3. **Per-document retrieval scoping.** The false-"potentially missing" ceiling stands; exports
   carry a caveat instead of a fix. A wrong "missing" flag in a red-flag report is the tool's most
   dangerous output tonight.
4. **Raw model quality and speed.** qwen3:14b locally is below the frontier cloud tools that
   themselves score below lawyers on hard tasks; 21 clauses ≈ 3 minutes vs a sub-minute cloud
   norm (mitigated, not erased, by streaming + never re-paying a completed run).
5. **Connectors.** OAuth tier (Outlook, OneDrive, Clio, NetDocuments, Read AI) still blocked on
   owner registrations; iManage unresearched. Live paths tonight: Gmail (IMAP key), watched
   folders, drag-in .eml/files. Cloud-DMS firms can't ingest cleanly yet.
6. **Mac-only.** No Windows build (starts next). Most small firms run Windows — this alone
   excludes the majority of the addressable market tonight.
7. **No Excel export** (CoCounsel recommends Excel for citation organization); minor but real.
8. **Zero distribution proof:** 4 known prospective users, no independent benchmark, no press,
   plus the "DocuChat" App Store name collision (market-2026.md §1 flag).

---

## 2. The five real alternatives, priced and scored against tonight's build

### (a) Spellbook / DraftWise / Gavel Exec — Word add-in contract review
- **Price:** Spellbook unpublished, third-party bands ~$99/user/mo (individual) to $149
  (professional), enterprise ~$199–350/user/mo after the late-2025 raise
  ([AI Vortex](https://www.aivortex.io/legal/compare/spellbook-pricing-2026/),
  [Costbench](https://costbench.com/software/ai-legal-tools/spellbook/)); Gavel Exec $160/user/mo
  ([Lawyerist](https://lawyerist.com/reviews/artificial-intelligence-in-law-firms/gavel-exec-review-artificial-intelligence-for-lawyers/));
  DraftWise unpublished, upmarket.
- **Better than docuchat tonight:** in Word (zero context switch); actual redlines via Track
  Changes; firm playbooks with preferred/fallback language; market benchmarking; instant cloud
  speed. The deliverable is the negotiation-ready .docx — docuchat's export is a findings report,
  not a markup.
- **What docuchat does that they CANNOT:** true on-device inference — Spellbook's "Most Private AI"
  is ZDR contracts over OpenAI/Anthropic APIs, documents still transit third-party clouds
  (market-2026.md §1, privacy-washing flag); mechanical span-verification of every cited cell;
  matter-wide Q&A across email + attachments + folders; exhaustive true-count "every mention";
  $0 vs ~$1,200–4,200/yr.
- **Head-to-head verdict:** the attorney negotiating 5+ contracts/month rationally keeps
  Spellbook. But the published Spellbook **anti-fit** — "<5 contracts/month, litigation practice,
  solo who can get 80% of the value from Claude at $20/month"
  ([AI Vortex](https://www.aivortex.io/legal/compare/is-spellbook-worth-it/)) — is precisely
  docuchat's fit. These products and docuchat mostly do not compete for the same job.

### (b) CoCounsel / Paxton — cloud legal assistants
- **Price:** CoCounsel $104–639/user/mo, often atop Westlaw; Paxton $499/user/mo or $2,999/yr
  (market-2026.md §1).
- **Better tonight:** legal *research* grounded in Westlaw/Practical Law/50-state law — docuchat
  deliberately does none; sub-minute cloud speed; 200-file review tables with Excel export;
  drafting; Paxton's AI Citator + confidence indicator; vendor accountability, SOC 2, support.
- **What docuchat does that they CANNOT:** documents never leave the machine (ABA 512 answered
  structurally, not contractually; Heppner-proof architecture); mechanical span verification —
  Stanford RegLab measured 17–33% hallucination in the incumbent research stacks
  (market-2026.md §5) while docuchat's every claim is verified-or-flagged against the source
  bytes; works offline; free vs $1,250–7,700/yr. ABA's own GPSolo questioned CoCounsel's solo-firm
  value ("Smart Assistant or Costly Add-On?"); Lawyerist called Paxton's $499 "steep for a
  one-person firm."
- **Verdict:** an attorney who needs case-law research buys one of these regardless — docuchat is
  not a substitute. For *document* work on their own matter files, tonight's docuchat does the
  cited-Q&A job with a stronger verification story at $0.

### (c) Clio Duo / MyCase IQ / Smokeball Archie — practice-management AI
- **Price:** Clio base $49–139/user/mo, Duo add-on gated behind sales; MyCase IQ $100–130/user/mo
  all-in; Smokeball Archie add-on unpublished (market-2026.md §1).
- **Better tonight:** lives inside the system of record — matters, billing, calendar, tasks,
  email filing are all one product; deadline extraction lands directly on the firm calendar;
  Smokeball's new Archie is in Word AND Outlook; 43% of buyers name "integration with trusted
  software" as a top criterion. The switching cost runs in their favor: the attorney is already
  paying and already in the app.
- **What docuchat does that they CANNOT:** local inference (all cloud-only; MyCase runs on
  OpenAI's API); span-verified citations (MyCase explicitly disclaims and tells users to verify);
  ingest and search *outside* the PM silo (a folder of discovery, a Gmail label, .eml drags);
  free without a PM subscription.
- **Verdict:** the firm already on Clio/MyCase rationally waits for its incumbent's AI rather than
  adopting a second app — unless the confidentiality objection bites (their AI is cloud) or the
  matter's documents live outside the PM. docuchat's Clio connector being OAuth-blocked hurts
  exactly here.

### (d) ChatGPT / Claude with uploads — the actual most common competitor
- **Price:** $20/mo (Plus/Pro tiers); Teams/Enterprise with ZDR more. 62–64% of solos and 2–9
  firms use or consider ChatGPT vs 36% of big firms (ABA, market-2026.md §2). This is what
  docuchat's target attorney is really using tonight.
- **Better tonight:** frontier model quality (far above qwen3:14b) on reasoning, drafting,
  summarizing; instant; zero learning curve; general-purpose (letters, marketing, research
  triage); ubiquitous.
- **What docuchat does that they CANNOT — and this is the strongest head-to-head in the deck:**
  1. **Privilege.** *US v. Heppner* (SDNY, Feb 2026, Rakoff) held consumer-**Claude** outputs NOT
     privileged even after sharing with counsel, because the ToS allowed training use and
     third-party disclosure — the exact tool, the exact tier, this attorney uses
     ([DLA Piper](https://www.dlapiper.com/en-us/insights/publications/2026/02/are-ai-generated-documents-privileged-key-takeaways-from-heppner),
     [Dorsey client alert](https://www.dorsey.com/newsresources/publications/client-alerts/2026/2/ai-attorney-client-privilege)).
     A 2026 cottage industry of firm alerts now warns lawyers off consumer chatbots for client
     documents ([GC AI](https://gc.ai/blog/chatgpt-for-lawyers),
     [McBrayer](https://www.mcbrayerfirm.com/blogs-intellectual-property-blog,claude-isnt-your-lawyer-and-the-information-you-share-with-it-isnt-privileged)).
     docuchat's answer is architectural: nothing leaves the machine, ever.
  2. **Verifiable citations.** Chatbots cite from context approximately and cannot be mechanically
     checked; docuchat pins every claim to file+page+span or says "could not find," with the
     1,745+ sanction cases and the $110K Oregon penalty as the cost of the alternative
     (market-2026.md §4).
  3. **A persistent matter workspace.** Hundreds of documents + a Gmail label + attachments +
     watched folders, standing digests, attorney-confirmed deadlines — vs re-uploading files into
     a context window per session, under upload caps.
  4. **True-count enumeration.** "Every mention" is an exhaustive verified count; an LLM
     fundamentally cannot promise exhaustiveness over a corpus.
  5. **Free**, and no consent/disclosure memo needed under ABA 512 / Texas 705 / Florida 24-1.
- **Verdict:** the chatbot stays for drafting and thinking. For *interrogating the client file*,
  tonight docuchat is the rational replacement, and Heppner is the one-sentence pitch.

### (e) DO NOTHING — ctrl-F, Spotlight, and a paralegal
- **Price:** $0 marginal, or a paralegal hour ($25–50). Still the majority behavior: only 18% of
  solos had firm AI adoption in the last independent ABA survey (market-2026.md §2).
- **Better tonight:** zero risk, zero setup, zero trust question, defensible by habit; for a
  20-document matter, honestly fine.
- **What docuchat does that ctrl-F CANNOT:** search by meaning, not string; one query across PDFs
  + email + attachments simultaneously; enumerate every mention of a name across a matter in
  seconds with page-pinned proof; surface deadlines with the source quote (a function LawToolBox
  charges $19–35/user/mo for); a standing matter digest. Setup cost tonight is one DMG install +
  drag a folder — no account, no policy memo, no vendor diligence.
- **Verdict:** for small matters, do-nothing rationally wins and docuchat should not pretend
  otherwise. The crossover is the multi-hundred-document matter — the discovery dump, the estate
  box, the lease portfolio — where reading everything is hours and ctrl-F misses paraphrase.

---

## 3. The honest adoption case

**Who rationally picks docuchat TONIGHT:**

A **Mac-using solo or 2–5 attorney firm** with a **document-heavy, matter-file practice** —
litigation discovery, estates/probate, PI files, family law, lease/vendor/diligence portfolios —
who tonight is either (a) pasting client material into consumer ChatGPT/Claude, or (b) drowning
in ctrl-F. For (a), docuchat is strictly safer post-Heppner and strictly more verifiable, at the
same price of free. For (b), it is the first tool whose adoption cost (one install, no account,
no cloud, no policy memo, $0) is actually below the do-nothing bar. The clinching situation: a
new matter arrives as a box of PDFs plus a Gmail thread with attachments, and the questions are
"what does the file say, where exactly, what deadlines are named, and every mention of X" — the
document-Q&A/extraction shape where AI independently outscores human lawyers (Vals 94.8% vs
70.1%) and where docuchat's verification makes the output usable, exportable, and defensible.
Note the inversion: the published Spellbook anti-fit (low contract volume, litigation, solo,
price-sensitive) is a large share of all solos, and it describes docuchat's ideal user exactly.

**Who rationally does NOT pick it yet — and why they're right:**
- **Windows attorneys** (most of the market): no build. Distribution, not product.
- **Transactional negotiators**: the job ends in a redlined .docx in Word; docuchat ends in a
  findings report. Spellbook/Gavel keep this segment until/unless docuchat ships playbooks and a
  Word-facing output — and per Vals, maybe it never should.
- **Research-need attorneys**: docuchat contains no law, on purpose. CoCounsel/Paxton/Descrybe
  are complements, not competitors.
- **Clio/MyCase-committed firms**: the incumbent's AI is coming to where their data already lives;
  docuchat's Clio connector is OAuth-blocked. Rational to wait.
- **Cloud-DMS firms (NetDocuments/iManage)**: no ingestion path tonight.
- **The prudence-maximalist**: 4 users, no independent benchmark, no vendor entity behind it, an
  open false-"missing" ceiling on the review grid (caveated, not fixed), and a name collision on
  the App Store. "Free and local" also means "no one to sue."

**Bottom line for the owner:** Yes — as of tonight, for the first time, there is a real attorney
for whom docuchat is the *rational* choice, not a curiosity: the Mac solo interrogating their own
matter file, especially one currently violating their own confidentiality instincts with a $20
chatbot. v0.5.0 closed the disqualifying workflow objections (spinner, persistence, export) that
made this morning's answer "not yet." What keeps the answer narrow is no longer product truth —
it is Windows, OAuth connectors, the playbook gap, and proof (users, benchmark, name). Those are
reach problems. The wedge is real, the wedge is defensible (Heppner + ABA 512 + span verification
are structural, not marketing), and the wedge is currently one platform and four prospects wide.

---

## Sources added tonight (beyond the two prior reports' source lists)
- Spellbook pricing bands 2026 — https://www.aivortex.io/legal/compare/spellbook-pricing-2026/ ;
  https://costbench.com/software/ai-legal-tools/spellbook/ (third-party estimates; Spellbook does
  not publish pricing)
- Heppner client-alert wave — https://www.dorsey.com/newsresources/publications/client-alerts/2026/2/ai-attorney-client-privilege ;
  https://gc.ai/blog/chatgpt-for-lawyers ;
  https://www.mcbrayerfirm.com/blogs-intellectual-property-blog,claude-isnt-your-lawyer-and-the-information-you-share-with-it-isnt-privileged ;
  https://thelegalprompts.com/blog/ai-attorney-client-privilege-heppner-ruling
- All other claims cite `mkt-attorney-adoption.md` (2026-07-11) and
  `../2026-07-10-reports/market-2026.md`, whose full source URLs are inline above where relied on.
