# docuchat — next-cycle plan and product direction

_Written 2026-07-10, end of the v0.3.x overnight+morning session. Read this after
RUN_STATE.md top entry. Canonical to-do list + the strategy decided with the owner._

## Where we are

v0.3.2 shipped (28 live connectors, one-click in-place updates, Gmail TLS fix,
WKWebView upload fix, self-healing startup). The keychain incident is resolved
(data reset; owner still has NO Time Machine backup). Two research drafts from
this cycle await the owner's read and gate the biggest items below:
`docs/2026-07-10-memory-design-draft.md` and
`docs/2026-07-10-speed-to-insights-draft.md`.

## Product strategy decided this session (do not relitigate)

- **Single-user love first.** A firm will not buy a collaboration tool that
  individual attorneys don't already want. Win the solo product before adding
  multi-user weight.
- **Sharing = firm-owned APPLIANCE, never cloud.** Multi-attorney sharing
  (roles owner/attorney/paralegal/read-only, shared matters, audit, immediate
  revocation) is real and important for the business, but the right model is one
  docuchat on firm-owned hardware (the Mac Studio in the roadmap) that attorneys
  reach over the LAN. Cloud sync would give away the privilege-safe
  differentiator that separates us from cloud competitors. This is a Milestone
  4-5 lift (it requires binding beyond loopback — currently forbidden by hard
  rule #4 — plus real auth/sessions/concurrency, which the loopback-no-auth
  model deliberately avoids). Foundations already exist: matter isolation +
  per-matter crypto keys (D-73), hash-chained audit log (D-72).
- **Cheap local sharing stepping-stone = matter export/import.** Encrypted
  matter bundle, handed off via AirDrop/USB/firm share, imported by another
  install. Covers handoffs and second opinions with NO server. On-brand.
- **Urgency = derived deadlines, NOT manual priority grading.** A high/med/low
  importance flag is a generic coordination feature that pays off only with
  multiple users; skip it for now. Legal urgency is driven by DEADLINES
  (statute of limitations, response windows, filing/discovery cutoffs). docuchat
  should DERIVE these from the documents and surface them PROACTIVELY — a
  deadline you must remember to ask for is the one you miss. Deadline math is
  high-stakes (calendar vs court days, jurisdiction, service dates): surface the
  cited source LANGUAGE and let the attorney confirm the computed date; never
  silently assert a date.
- **Slash commands are on-demand ACTIONS** (`/summarize`, `/compare`,
  `/timeline`, `/find`, `/digest`) over features we already have. `/deadlines`
  is a convenience shortcut, NOT the home of the deadline feature.
- **Speed is a model problem, not a parsing problem.** We parse ONCE at ingest;
  retrieval is matter-scoped (~100ms) and stays flat from 100 to 10,000 docs
  because each query only searches its matter (proven in eval/SCALE_EVAL.md:
  dense top-5 at ceiling across 50 matters / 5,114 chunks). The ~6-12s wait is
  the local 14B LLM (fixed cost, corpus-independent). The stress case to design
  for is ONE enormous matter (thousands of docs in a single matter). The real
  speed unlock is the precomputed matter digest below.

## Prioritized to-do (next cycle)

**KEYSTONE (highest leverage — one build powers three features):**
1. **Precomputed matter digest / memory M-2.** At ingest, extract entities,
   dates, parties, amounts, and a timeline into a small structured, inspectable,
   span-verified layer (design in the memory draft §M-2). This one layer powers:
   (a) speed-to-insight (answer "who are the parties / what's the fee" instantly,
   skipping the full retrieve+generate loop), (b) an instant matter-overview on
   open, and (c) deadline extraction below. Owner-gated by 63/63 golden (D-79);
   read the memory draft with the owner FIRST.

**HIGH:**
2. **Deadline extraction + proactive urgency surfaces** (on top of the digest):
   extract deadline language at ingest; a "Deadlines" section on the matter
   overview; a cross-matter "due this week" view (the real replacement for
   manual importance grading); `/deadlines` as a secondary shortcut. Every date
   cited to source language; attorney confirms. This is the roadmap's sleeper
   feature and the legal-native answer to "urgency."
3. **Memory M-1 query rewriting.** The answer path is stateless today — thread
   history is stored but never used, so follow-ups ("and the late fee?")
   retrieve on a bare fragment and fail. Smallest diff in the memory draft,
   fixes a real broken UX. Gated by the new G-MT multi-turn golden class.

**MEDIUM:**
4. **Slash commands** in the chat composer over existing features
   (summarize/compare/timeline/find/digest). Cheap polish, on-brand, makes the
   product feel expert. Short brainstorm on the command set first.
5. **Matter export/import** (encrypted bundle). The local sharing stepping-stone.
6. **Owner registrations for the Planned connectors** (owner action; list in
   `docs/2026-07-10-connector-registrations.md`): Clio Manage + NetDocuments
   first, then the Microsoft Entra app (covers Outlook/OneDrive/Word/OneNote),
   Read AI outreach. Unlocks the Planned tier.

**LOWER / DEFERRED:**
7. Speed ENGINE wins behind the golden gate (second-pass overlap, FTS-at-ingest)
   — the zero-risk quick wins already shipped in v0.3.x; these are the next tier.
8. Business-model decision (license key vs seats) — gates the real Billing build.
9. Windows build (owner box + Azure signing).
10. Firm appliance / multi-user sharing — the big future (M4-5), NOT now.

## Verification debt to confirm first thing next session

- The v0.3.2 WKWebView upload fix and the startup self-heal were logic- and
  unit-tested but NOT exercised in the real packaged app. Confirm profile-photo
  and document uploads work in the installed app.
- The one-click in-place updater got its first real-world run (owner updating
  v0.3.1 → v0.3.2). Confirm it succeeded (or fell back cleanly).

## Owner action (personal, not product)

Set up Time Machine. `tmutil destinationinfo` = no destinations. A solo
attorney machine that will hold real client files with zero backup is the
biggest standing risk.
