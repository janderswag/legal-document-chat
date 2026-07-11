# Council — Adoption Verdict (2026-07-11, evening)

> The owner's question tonight, verbatim: **"Is this valuable enough yet for attorneys to use
> vs other applications?"** Not roadmap talk — an adoption verdict.
> Secretary's synthesis of the nine-seat evening council. Seat verdicts are reproduced verbatim.
> Builds on the morning reports in `docs/council/2026-07-11-reports/` (hours old, still valid).

## 1. The question and tonight's state

v0.5.0 was released tonight (published as Latest, 2026-07-11T20:43Z), executing this morning's
council plan (`docs/council/2026-07-11-council-review-compare-and-ingestion.md`) end to end:
contract review is now a streamed, cancelable, persisted background job (~9s/clause, zero-second
reopen, staleness flags, single-doc scope, attorney-declared doc-type filter, custom questions,
Copy/Markdown/Word exports carrying per-clause verification status plus the retrieval-scope
caveat); Gmail walks past the 500 cap and attachments become searchable child documents landing
in Unfiled behind a suggest-then-confirm chip; watched folders got a native macOS picker, split
guards, and a live heartbeat; "Every mention" was promoted with verifier-aligned true counts; the
Core Four catalog shipped and the engine is untouched (63/63 + 9/9 + 0 golden gate identical).
Honestly still missing: OAuth connectors (Outlook first, blocked on owner registrations),
iManage, the Windows build, per-document retrieval scoping (the false-"potentially missing"
ceiling — caveated, not cured), editable playbooks, matter export/sharing, a RAM gate, bundled
OCR, and subfolder recursion in watched folders. The owner has exactly 4 known prospective
users; pricing is free/open for now. Against that state, each seat was asked for an adoption
verdict: would a real attorney use this tonight, versus what they use today?

## 2. Seat verdicts (verbatim)

### Attorneys and staff

## Maria (solo litigator (returning))
**VERDICT: Yes — I would put a live matter into it this month, conditional on the paper path: bundle Tesseract, because a litigation file is half scanned exhibits and an unbundled OCR binary makes half my file invisible.**

Credit is exact: every demand I made this morning shipped as demanded. Review streams (~9s/clause), survives quit, and exports a Word red-flag report carrying the scope caveat (routes_clauses.py:94-149); Gmail walks past the 500 cap and my attachments — my key documents ARE attachments — are searchable child documents (gmail.py:206-211, connsync.py:186-208); the folder picker is a real macOS dialog; "Every mention" sits at the top of Document Hub with verifier-aligned true counts. That last piece plus span-cited chat and .ics deadlines is the litigator's actual product: privilege checks, coverage checks, "every place this date appears" across a multi-hundred-document production — exactly the crossover where the market report is right that the $20 chatbot loses on both privilege (Heppner) and verifiability, and ctrl-F loses on absence.

Now the honesty. Review & Compare, tonight's headline, offers a litigator nothing (eng-week-one-reality item 8), and its false "potentially missing" is caveated, not cured — I will trust that tab exactly as far as the caveat line. My real blocker is duller: scanned PDFs require `brew install tesseract`, and watched folders skip subfolders, so my Pleadings/Correspondence/Discovery tree doesn't just land. I will do the brew install once; no attorney I'd refer will. Against my current workflow — Preview, ctrl-F, and guilt — this wins on any matter over about fifty documents, which is most of mine.

Tips my yes: bundle Tesseract (subfolder recursion right behind it) — scanned discovery IS the litigation file, and it has to just work.

## Rosa (managing partner, 6-attorney firm (returning))
**VERDICT: No — there is no firm I would deploy this in tonight, mine included; the only viable unit is one privacy-driven individual attorney on a 16GB Mac with Gmail, and I will not pilot even that associate until the false-"potentially missing" flag is fixed rather than caveated.**

I buy for six attorneys, and firm math is unforgiving. All six seats are on Microsoft 365, and Microsoft retired app passwords for IMAP in Sept 2024 (session-close doc), so tonight's genuinely excellent email truth work simply does not exist for an Outlook firm: no OAuth, no email path, full stop. Half my machines are Windows. There is no matter export or sharing, so an associate's persisted review runs are trapped on her laptop outside the matter file, which is a supervision and continuity failure, not a roadmap item. There is no editable playbook, and encoding the firm's positions across attorneys is precisely why firms buy review tools (mkt-attorney-adoption: Spellbook, DraftWise, and Gavel all lead with it, and a fixed 4-type checklist tells my senior people what they already know). Worst, Review still emits false "potentially missing" on its namesake job (eng-week-one-reality item 5); for a solo that burns trust, for a supervising partner it is the documented "false sense of security" malpractice vector, and a caveat line does not discharge my duty. Credit is due and real: span-verified citations nobody else ships, persisted runs, honest exports, and post-Heppner the local privilege architecture is the strongest firm argument this product has. That is why this is a gate list, not a burial. Minimum for a one-associate pilot: false-missing actually fixed via per-document scoping, matter export so work product reaches the firm file, and the RAM gate. Outlook OAuth and Windows gate the other five seats.

Tips my yes: the engine-gated per-document scoping fix, so a partner can trust a "missing" flag enough to sign the review.

## David (transactional attorney (returning), THE contract-review user)
**VERDICT: Conditional yes. Contract Review enters my weekly workflow tonight as the intake-and-diligence pass on every new contract, and the caveat converts "potentially missing" from a trap into a usable triage list; it does not enter as my negotiation tool, and the missing signal stays a triage list, not a clearance, until per-document retrieval scoping ships.**

This morning I said I would not run this on a 40-page MSA because I'd be left holding nothing. Tonight all three disqualifiers are dead in code, not slides: skeleton instantly and ~9s/clause streamed (21 clauses in about 3 minutes, which I spend reading the recitals anyway), runs persisted with zero-second reopen and staleness flags, and a Word red-flag report where red flags lead, every row carries its verification status, and Sam's caveat is on every export (routes_clauses.py:118-155). The caveat's exact sentence, "not located, not that it is absent," is the honest framing that lets me use the signal: "potentially missing" now means "go read those sections yourself," which is precisely how I'd task an associate. That is billable, attachable diligence work product. So yes: single-doc review, doc-type filter, my own questions, export to the file. Weekly.

The honesty cut: single-doc scope is a classification post-filter, not retrieval scoping (clauses.py:97-98, grid.py:7). My MSA's clauses still compete matter-wide for top-5, on matters v0.5.0's Gmail ingestion just made fatter. The false-missing rate rises exactly as the product succeeds at ingestion, and one confirmed-false "missing" I spot-check erodes the tab's namesake signal. Also true: the export is a memo, not a redline; Spellbook keeps the negotiation job, and my custom questions don't persist between runs.

Tips my yes: per-document retrieval scoping, the engine-gated fix that makes "potentially missing" mean what the tab's name promises.

## Patricia (tech-skeptic solo (returning))
**VERDICT: Conditional yes — the lunch-table pitch finally works, but only if I survive the first hour, so: conditional on the first-run wall (model download, RAM, scanned PDFs) not killing me before I ever see a cited answer.**

One-sentence test: for the first time it passes. "It reads your whole matter file on your own Mac and answers with page citations you can click and check." I can say that. Here is what I would actually say at lunch, as someone who pastes contracts into ChatGPT like everyone else at my table: a federal judge just held that what you type into a consumer chatbot is not privileged (Heppner), ChatGPT cannot cite a page it actually read, and it forgets your matter the moment the window closes. This thing never leaves your laptop, every claim carries a file-and-page span you can verify in one click, "Every mention" gives real counts instead of vibes, and a review survives quitting the app and exports to Word with its own honesty caveat printed on it (routes_clauses.py confirms it). And it costs nothing. That is a genuinely better story than my $20 habit.

First-five-minutes test: still fails cold. Minute one I hit a 10.5GB, 20-to-60-minute model download; if my Mac has 8GB there is no warning before it swap-thrashes; my scanned PDFs, the core of a paper practice, need a Homebrew Tesseract install I will never do; and the tab named Review can flag "potentially missing" clauses that are not missing, which is the one lie a skeptic never forgives twice. The bundled sample matter is lovely craft, but it demos your documents, not mine.

Tips my yes: a first run that reaches a cited answer on my own scanned PDF within minutes — bundle OCR, gate RAM, and never make me visit Homebrew.

## Elena (staff paralegal (new seat, kept))
**VERDICT: Conditional yes — I'd push my attorney to adopt tonight IF we're a Gmail/Mac shop that's already digital; the intake story still does not fit paper or Outlook, which is how half of a real firm's documents actually arrive.**

What v0.5.0 got right is exactly my job. Exclude-before-cap (gmail.py:206-211) means a 3,000-message matter label finally finishes instead of stalling at 500. Attachments as searchable child documents (connsync.py:186-208) matters more than the email body ever did — the attachment IS the document. Imports landing in Unfiled with a suggest-then-confirm "File to X" chip is how a careful paralegal actually files: never auto-sorted, always confirmed. The heartbeat ("watching · checked 12s ago") turns an invisible daemon legible, corrected re-scans now land via checksum identity, and "Every mention" with a true count is a genuine litigation sweep no chatbot can do — ChatGPT can't tell me a name appears exactly 37 times, and per Heppner its outputs aren't even privileged (mkt-adoption-verdict-input.md).

But be honest about the front door. Scan-to-folder is our paper intake, and it breaks twice: watched folders skip subfolders, so a scanner writing date-subfolders is never picked up (eng-week-one-reality.md item 6), and Tesseract isn't bundled, so the scan that does land is unsearchable without a Homebrew install (item 4). Most of legal runs Outlook — today's answer is "drag .eml files out by hand," which is me doing the connector's job. Gmail's app-password ritual is the highest-abandonment step and Workspace admins often disable it outright (item 2). The 25MB cap cuts off productions.

So: adopt for the four prospects, hand-held, Gmail-and-digital matters only.

Tips my yes: bundle OCR (Tesseract) plus subfolder recursion, so scanned paper — the way documents actually arrive at a firm — flows in and is searchable out of the box.

### Reviewer, design, engineering, ethics

## Aisha (legal-tech reviewer (returning))
**VERDICT: Conditional yes — I'd publish a "worth downloading" review tonight, but scoped hard to the Mac solo interrogating a matter file, with two printed warnings; it is not yet a general recommendation.**

Scored head-to-head: vs ChatGPT-with-uploads it now wins outright, and that's the review's spine — Heppner (SDNY, Feb 2026) killed the consumer-chatbot workflow for client documents, and no chatbot can do span-verified file+page citations, a persistent matter workspace, or an exhaustive "Every mention" count, at the same price of free. Vs Spellbook it visibly lags and should say so: no Word, no Track Changes, no playbook; the Word export is a red-flag memo, not the negotiation deliverable — but Spellbook's own published anti-fit (<5 contracts/mo, litigation, solo) is exactly this tool's fit. Vs CoCounsel/Paxton it concedes research entirely and cloud speed (21 clauses ≈ 3 min vs sub-minute), while beating both on privilege architecture, verification (vs 17–33% measured hallucination in the incumbents), and $0 vs $1,250–7,700/yr. Credit where due: v0.5.0 deleted my prior disqualifiers — the blocking spinner is now a streamed, cancelable, persisted job with zero-second reopen, and exports carry per-clause verification status. My two printed warnings: the install funnel (no RAM gate on a 10.5GB model pull, 20–60 min wall, Tesseract unbundled so scanned paper — the target user's core case — silently fails) and the live false "potentially missing" on the Review tab, which is the app's most dangerous output even caveated. Headline: **"Free, local, and it shows its work: the first legal AI a solo can trust with the client file — just not yet with the redline."**

Tips my yes: fixing the false "potentially missing" via per-document retrieval scoping — a wrong red flag in an exported report is the one defect that can undo the verification story the whole product stands on.

## Jonas (principal product designer (new seat, kept))
**VERDICT: Conditional yes. The design now makes the value self-evident inside five minutes, conditional on one fix: the Review tab's "potentially missing" label must stop asserting what retrieval cannot yet honor.**

All five debts from my morning report (mkt-design-bar.md §e) closed in one session, verified in code tonight: Review streams skeleton rows with per-clause fill and a Run-to-Cancel swap, replacing the single static "this can take a moment" line that was the app's worst moment; runs persist and reopen in zero seconds with a staleness flag; watched folders got the native macOS picker plus a work-done heartbeat ("watching, checked 12s ago, N files added"); Every mention was promoted with labeled modes and the /find cross-link; the token sweep stopped the palette drift. Crucially, the differentiator is now legible without explanation: onboarding screen 3 states the verification contract in plain language (app.js:352-355), and every verified citation renders an inline thumbnail of the cited page with the span highlighted (app.js:1196-1206). No chatbot can show that in a demo, and no reading is required to see it.

But minute four is where the demo still dies. An attorney runs Review on a contract they know, sees "potentially missing" on a clause sitting on page 7 (app.js:2971; eng-week-one-reality friction 5), and the honesty brand collapses to chatbot level at the exact moment it was being proven. The caveat line (app.js:2614-2616) is a footnote; it cannot outshout a verdict-colored label. In a product whose entire moat is never claiming more than it verified, this is the one place the design lies. Secondary but real: the five minutes start only after a 20-60 minute model wall with no RAM gate, and Billing/Referrals remain dead chrome in primary nav, my own blacklist item 7.

Tips my yes: reword and visually demote "potentially missing" to retrieval-honest language ("not found in retrieved passages, check manually") tonight, ahead of the engine-gated scoping fix.

## Priya (head of engineering (returning))
**VERDICT: Conditional yes — the foundation holds for the 4 prospects and a slow trickle tonight, but a 100-download month breaks at install, not at load, and we'd never see it break: ship only after a RAM gate.**

The architecture itself is the one thing I don't fear at scale. There is no shared backend to fall over — 100 attorneys means 100 independent local instances, and the pieces that carry per-user load are genuinely solid: the D-90 runner is serial FIFO with persisted rows, event replay, and honest restart semantics; the engine is frozen (zero diffs, 63/63+9/9+0 golden gate identical); packaged smoke is 6/6 including the new review-SSE step; and the per-move adversarial review went five-for-five on real defects, including catching the js_api Window exposure before commit. That's shipped-quality discipline, not demo-quality.

What breaks first is the funnel, silently. No RAM gate: an 8GB M1 Air — a large share of solo-attorney Macs — downloads 10.5GB and swap-thrashes with no warning (eng-week-one-reality.md:42-44). Gmail app-passwords are undetectably disabled on many Workspace tenants. Tesseract isn't bundled, so scanned PDFs — the paper-practice core case — fail. Watched folders skip subfolders. And because we're local-first with zero telemetry by design, all 100 failures are invisible to us; the app just quietly earns a "didn't work" reputation we can't debug. Add the live false-"potentially missing" in Review — caveated, but it's a trust-burner on the tab's namesake job — and wide distribution this month converts strangers into detractors, not users.

Hand-held onboarding of the 4 prospects tonight: acceptable risk, yes. Open-throttle 100 downloads: no.

Tips my yes: a startup RAM gate (refuse-with-explanation under 16GB) — it's a day of work and it closes the only failure mode that is both silent and unrecoverable.

## Sam (ethics & security officer (returning))
**VERDICT: Conditional YES — v0.5.0 is safe tonight for a real attorney on real matters within its stated boundaries, conditional on a spoken (soon: on-screen) install disclosure covering four things; it is affirmatively safer than the chatbot workflow it replaces.**

I re-verified my riders in the shipped code, not the release notes: the scope-plus-verification caveat is on every Word export (pipeline/routes_clauses.py:149, and it leads the report, before the table); the folder-picker bridge is dialogs-only with the window handle underscore-private and test-pinned (desktop/launcher.py, the recursive-exposure lesson held); imports land in Unfiled behind suggest-then-confirm; the server binds 127.0.0.1 only with OLLAMA_ORIGINS pinned; the catalog is SQLCipher keyed from Keychain, connector credentials and matter files are keyvault-encrypted (connsync.py:131,152). Post-Heppner, this architecture is a privilege argument the $20 chatbot cannot make. The adopter market identified tonight is currently pasting client files into consumer Claude; moving them here is a security improvement, not a risk.

The conditions, told at install: (1) loopback is the auth boundary, so single-user Mac, FileVault on, no shared logins; (2) the Gmail app password is a full-mailbox credential, stored encrypted, revoke it if the machine changes hands, and Google silently kills it on password change; (3) Review's "Potentially missing" can be false, the caveat is honest but attorneys habituate to boilerplate, so treat Review as a checklist aid and never skip reading the contract; (4) no computed deadlines, not a docket, verify every citation. My one product-truth worry is (3): a label the engine cannot fully honor, on the tab's namesake job, is an ethics debt even caveated. Fix it before widening past the four hand-held prospects.

Tips my yes: a first-run disclosure screen that states these four boundaries in the app itself, so the safety case stops depending on who installs it.

## 3. The verdict tally

**Yes: 1 · Conditional yes: 7 · No: 1** — and even the one flat "Yes" carries a named condition.

| Seat | Verdict | Named condition(s) |
|---|---|---|
| Maria (solo litigator) | **Yes** (live matter this month) | Bundle Tesseract; subfolder recursion right behind it |
| Rosa (managing partner) | **No** (no firm unit tonight) | Gate list: per-doc scoping fix for false-missing, matter export, RAM gate; then Outlook OAuth + Windows for the other five seats |
| David (transactional) | **Conditional yes** (weekly diligence pass) | Per-document retrieval scoping before "missing" is a clearance, not a triage list |
| Patricia (tech-skeptic solo) | **Conditional yes** (lunch pitch works) | Survive the first hour: bundle OCR, RAM gate, no Homebrew, cited answer on her own scanned PDF in minutes |
| Elena (paralegal) | **Conditional yes** (Gmail/Mac digital shops only) | Bundle Tesseract + subfolder recursion so paper intake flows |
| Aisha (reviewer) | **Conditional yes** ("worth downloading," scoped, two printed warnings) | Fix false "potentially missing" via per-doc scoping; install-funnel warning stands until RAM gate + bundled OCR |
| Jonas (design) | **Conditional yes** (value self-evident in five minutes) | Tonight: reword/demote "potentially missing" to retrieval-honest language, ahead of the engine fix |
| Priya (engineering) | **Conditional yes** (4 prospects + slow trickle only) | Startup RAM gate (refuse-with-explanation under 16GB) before any wide distribution |
| Sam (ethics/security) | **Conditional yes** (safer than the chatbot it replaces) | First-run disclosure screen stating the four boundaries in-app |

Notable convergences: every seat, including the No, credits the same core — span-verified
citations, the persisted streamed review, email/attachment truth, "Every mention," and the
post-Heppner privilege architecture. And every seat, including the Yeses, names the same top
defect — the false "potentially missing" on the Review tab's namesake job.

## 4. The owner's question, answered honestly

Yes — tonight, for a specific attorney, against a specific alternative: a **Mac solo (or a
paralegal-backed solo) on Gmail with a mostly digital matter file**, versus the **$20
consumer-chatbot habit** they actually have, docuchat is already the better tool and arguably
the only defensible one post-Heppner — it wins on privilege, on verifiable file+page citations,
on exhaustive "Every mention" counts, on a matter that persists, and on price, and David will
run it weekly and Maria will put a live matter in it this month. It is **not** yet valuable
enough for a firm (Rosa's No is structural: no Outlook, no Windows, no matter export, no
playbook), not a negotiation tool versus Spellbook (the export is a memo, not a redline), and
not survivable for a cold stranger who hits the first-run wall (10.5GB download, no RAM gate,
unbundled OCR, skipped subfolders) or who catches one false "potentially missing" — the single
defect eight of nine seats flagged as the trust-burner. The honest verdict: valuable enough
tonight for the 4 hand-held prospects and a slow referral trickle in the beachhead persona;
not yet valuable enough to open the throttle to strangers, and the gap is three named,
buildable items, not a mystery.

## 5. "Tips my yes" leaderboard — vs the next-cycle queue

Ranked by how many seats named it as the tipping item (tip) or a hard warning (warn):

| # | Item | Tips | Warns | Queue status (session-close doc) |
|---|---|---|---|---|
| 1 | **Fix false "potentially missing" via per-document retrieval scoping** | Rosa, David, Aisha | Maria, Patricia, Elena-adjacent, Jonas, Priya, Sam | **Queued** — but buried inside "the engine-gated batch in one future 63/63 cycle," unprioritized among Ollama timeouts / M-1 rewriting / fact-router |
| 1b | ↳ Interim: reword + visually demote the label to retrieval-honest language, tonight | Jonas | Sam ("ethics debt even caveated") | **Not in queue at all** — a same-night UI-only stopgap the queue doesn't know about |
| 2 | **Bundle Tesseract (OCR) + watched-folder subfolder recursion** | Maria, Elena, Patricia (as part of first-run) | Aisha, Priya | **Not in queue at all** |
| 3 | **RAM gate (refuse-with-explanation under 16GB) / first-run wall** | Priya, Patricia (as part of first-run) | Rosa, Aisha, Jonas, Sam | **Not in queue at all** — Priya prices it at a day |
| 4 | **First-run disclosure screen (Sam's four boundaries, in-app)** | Sam | — | **Not in queue** |
| 5 | **Matter export/sharing** | Rosa (gate item) | — | **Queued** (with the day-one background-job rider) |
| 6 | **Outlook OAuth + Windows** | Rosa (gates her other five seats) | Elena | **Queued** — Outlook is the queue's #1 item |

**The mismatch, plainly:** the queue leads with connectors (Outlook OAuth, iManage research) —
which only the No vote gates on — while the council's three highest-frequency tipping items are
either absent from the queue entirely (bundled OCR + subfolder recursion; RAM gate; Jonas's
same-night label demotion; Sam's disclosure screen) or buried without priority inside the
engine-gated batch (per-document scoping, which THREE seats named as their single tipping item
and which four more flagged as the product's most dangerous output). Adoption, as measured by
the seats, needs: (a) the label demotion tonight, (b) OCR + recursion + RAM gate this week —
none touch the engine — and (c) per-document scoping promoted to the front of the next 63/63
engine cycle. Outlook OAuth stays valuable but it converts Rosa's firm, not the beachhead solo.

## 6. What the council explicitly warns AGAINST doing next

1. **Do not open the distribution throttle.** No launch posts, no directory listings, no
   100-download month until the RAM gate, bundled OCR, and the false-missing label fix land.
   Zero telemetry means every funnel failure is silent and unrecoverable; wide distribution now
   "converts strangers into detractors, not users" (Priya). Four hand-held prospects only.
2. **Do not treat the caveat as the fix.** Rosa ("does not discharge my duty"), Sam ("attorneys
   habituate to boilerplate"), and Jonas ("a footnote cannot outshout a verdict-colored label")
   all converge: the caveat bought tonight's conditional yeses; it does not buy the next ones.
3. **Do not chase the redline / Spellbook's negotiation job.** David and Aisha are explicit:
   Spellbook keeps that job, and Spellbook's published anti-fit is exactly this product's fit.
   The Word red-flag memo is the right deliverable; deepen diligence, don't imitate drafting.
4. **Do not sell firms yet.** Rosa's No is structural (Outlook, Windows, export, playbook);
   pitching a firm before those exist burns the strongest future argument (the post-Heppner
   privilege architecture) on a demo that can't survive procurement.
5. **Do not ship new headline features before the front door works.** Patricia, Elena, Priya,
   and Jonas all locate the failure at first run, not at feature depth. The next visible work is
   intake and install truth, not a new tab.
6. **Do not redo this morning's research.** The reports in
   `docs/council/2026-07-11-reports/` are hours old and load-bearing in every verdict above;
   build on them.
