# Week-One Reality Audit — v0.5.0 as shipped tonight (2026-07-11)

Role: adversarial shipped-reality auditor. Method: read tonight's 10 commits, spot-verified every
headline claim in the actual code, then walked the honest week-one journey of a solo attorney who
downloads the DMG tonight. No roadmap credit given. Companion to `mkt-attorney-adoption.md`
(market context cross-referenced, not repeated).

---

## 0. Claims verification — the release is real

All four headline claims verified in code, not just in RUN_STATE prose:

| Claim | Verified where |
|---|---|
| Persisted review runs + exports | `pipeline/routes_clauses.py:94` (`GET /clauses/runs`, zero re-run), `:118` (docx export), caveat text at `:149-160`; UI stream/persist/epoch-guard in `pipeline/static/app.js` (~line 2609 on) |
| Gmail exclude-before-cap | `pipeline/connectors/gmail.py:206-211` — seen UIDs removed from the UID list BEFORE the 500 cap; module docstring documents the old pin-to-oldest-500 bug |
| Attachments as child documents | `pipeline/connsync.py:186-208` — `_eml_attachments`, same `_ALLOWED` gate + 25MB cap, unsafe names skipped, `attachment_of` provenance |
| Folder picker bridge | `desktop/launcher.py:542-572` — `choose_folder` via `create_file_dialog(FOLDER_DIALOG)`, window handle underscore-private (the CRITICAL from review, fixed) |

Commit `7266b27` alone is 1,885 insertions with 5 new test files. Tonight's tag is not vaporware.
Everything below assumes the code works as tested; the question is what a stranger's week feels like.

---

## 1. The week-one walk

**Persona:** solo attorney, mixed transactional/litigation practice, MacBook, Gmail (custom-domain
Workspace), a scanner, moderate tech comfort. Downloads docuchat tonight because "private, local,
free, cites its sources" sounded right.

### Day 1 — install and first answer

- 488MB DMG (`dist/docuchat.dmg`), signed and notarized: drag-to-Applications works, no Gatekeeper
  scare. Good.
- Ollama is silently bundled (`desktop/launcher.py:192-208`) — she never installs it. Genuinely
  good engineering.
- **STALL 1: the model wall.** First-run wizard needs qwen3:14b (9.3GB) + bge-m3 (1.2GB) and 15GB
  free disk (`routes_setup.py:61-62`). In-app progress bar exists (P1.5, real SSE pull), so it is
  honest waiting, but it is 20-60+ minutes of waiting on ordinary broadband before the app does
  anything. Competitors' first answer is 2 minutes after signup.
- **STALL 2 (silent, worse): no RAM gate.** The wizard checks disk and Tesseract, not memory. An
  8GB M1 Air owner — a large share of solo-attorney Macs — downloads 10.5GB and then gets a
  swap-thrashing, minutes-per-answer app with no warning and no explanation. Nothing tonight tells
  her the machine is the problem. This user churns and tells colleagues "it's slow."
- Onboarding: three skippable screens under a minute (app.js:315+), then the seeded Sample Matter
  (3 synthetic PDFs, suggested question, real page+span citations — `sample_matter.py`). The
  zero-setup first cited answer is a genuinely strong first-run moment. TTFT median 3.09s measured
  (`eval/LATENCY.md`), streamed. She clicks a citation, sees the highlighted span. This is the
  moment the product's promise lands, day 1, and it works.

### Day 2 — her own documents

- Drag-and-drop upload, 11 formats (`routes_kb.py:29`). PDFs/docx/eml all fine.
- **STALL 3: the 25MB cap.** Recorded depo exhibits, closing binders, and scanner output at
  600dpi routinely exceed 25MB. Rejection is honest but there is no "split it" help. She hits
  this in week one if she does litigation.
- **STALL 4: scanned PDFs need a manual Tesseract install.** OCR routing is built and careful
  (`ingestion.py`, per-page routing, fail-loud confidence), but the Tesseract binary is NOT
  bundled (`build_macos.spec` collects pytesseract only; wizard shows an advisory). A
  non-technical attorney will not `brew install tesseract`. Paper-heavy practices — exactly the
  local-first target — hit this on day 2 and perceive "it can't read my scans."
- Chat over her own matter: answers grounded, refusals honest, copy-with-citations works.
  "Every mention" (Move 5) is now top of Document Hub and the count matches the verifier's
  character contract — for a "find every reference to the easement" task this is excellent.

### Day 3 — Review & Compare

- Skeleton renders instantly, clauses fill ~9s each, cancel works, quit-and-reopen costs zero
  seconds, staleness chip appears if docs changed. Streaming UX is genuinely first-rate.
- **STALL 5: the fixed checklist.** Four doc types only — contract, lease, NDA, services
  agreement (`app.js:2619-2624`). Her employment agreement, purchase agreement, settlement
  agreement, or any litigation document gets the generic core set. Custom questions exist but
  are per-run typing, not a saved playbook. Every competitor's center of gravity (Spellbook,
  DraftWise, Gavel) is the attorney's OWN playbook; tonight there is a fixed taxonomy plus a
  text box.
- **STALL 6: false "potentially missing" — the trust burn.** Retrieval is matter-wide, not
  per-document; a clause present in the document can be flagged "potentially missing" because
  the matter's top-k went elsewhere. The caveat is on every export (routes_clauses.py:149) and
  it is honestly worded, but here is week-one psychology: an attorney runs review on a contract
  she knows, sees a clause she KNOWS is there flagged as potentially missing, and concludes the
  tool cannot be trusted for the one job the tab is named for. The caveat explains it; it does
  not un-burn it. This is tonight's single biggest product-quality ceiling, correctly identified
  as engine-gated, but tonight it is live in front of users.

### Day 4 — export

- Copy / Markdown / Word all work; the .docx is clean, red flags first, verification status and
  caveat carried. Good.
- **GAP: the export is a report, not a redline.** Market report section A is unambiguous: the
  unit of value in transactional review is a marked-up .docx with Track Changes she can send to
  the counterparty. Tonight's export is a memo ABOUT the contract. Useful as a checklist
  artifact; not the deliverable her workflow ends in. (Vals data cuts both ways: AI redlining
  underperforms lawyers anyway — but the buyer expectation is set by the category.)

### Day 5 — Gmail

- The connect drawer's steps are accurate and complete (gmail.py:52+: 2SV, app password, label).
- **STALL 7: app-password reality.** (a) Google Workspace admins frequently disable app
  passwords org-wide; a custom-domain attorney may discover mid-flow she cannot generate one
  at all, and the UI cannot know why. (b) Even when it works, it is a 5-step ritual across
  Google account settings — the single highest-abandonment step in the whole week. (c) The
  label workflow (make a label, apply it to relevant mail) is itself a new habit to teach.
- When it works: exclude-before-cap means a big label really does finish (500/pass, auto-sync
  every 30 min — a 3,000-message label completes in ~3 hours unattended), attachments become
  searchable child documents with provenance badges, imports land in Unfiled with a
  suggest-then-confirm chip. This pipeline is honest and well-built.
- **GAP: she uses Outlook.** Legal is disproportionately Outlook/Microsoft 365, and there is no
  key-paste path (Microsoft killed IMAP basic auth). Tonight's answer is "drag .eml files into
  a watched folder" — real, but manual. For an Outlook attorney the Email category is a
  "Coming" card.

### Day 6 — watched folder

- Native macOS picker opens (the bridge is real), heartbeat row ("watching · checked 12s ago ·
  N files added"), corrected re-scans land, checksum identity prevents dupes. Solid.
- **STALL 8: no subfolders.** Attorney matter folders are nested by convention
  (Client/Matter/Pleadings, /Correspondence, /Discovery). The copy honestly says subfolders are
  not imported — so her existing folder tree does NOT just work; she must point at each leaf or
  flatten. The scanner-tray use case works perfectly; the "watch my matter folder" use case
  half-works.

### Day 7 — settling in, or leaving

- Practice Management connector column is 100% "Coming" (Clio, NetDocuments, MyCase, Lawmatics,
  Actionstep, LEAP, Litify — all dead cards, app.js:2036-2044). A Clio user reads this as a
  promise wall.
- **Billing and Referrals are placeholder nav tabs** (app.js:3242-3281) pinned in the primary
  nav of a free product. To a trust-sensitive first-week user this reads as scaffolding shipped
  to production; it dilutes the "finished, careful tool" signal everything else works hard for.
- Mac-only. Windows attorneys (the majority of the profession) cannot even start the week.
- No matter export/sharing — whatever she builds is locked in the app; she cannot hand a matter
  brief to co-counsel except via per-answer copy and review exports.

---

## 2. (a) Friction that exists tonight (ranked by expected week-one drop-off)

1. **No RAM check** — silent unusable-slowness on 8GB Macs after a 10.5GB download.
2. **Gmail app-password ritual** — highest-abandonment step; Workspace-admin-disabled case is
   undetectable and unexplained.
3. **10.5GB / 20-60min model wall** before first use (honest progress bar mitigates, does not
   remove).
4. **Tesseract not bundled** — scanned documents, the paper-practice core case, need a Homebrew
   command nobody in the persona will run.
5. **False "potentially missing" in Review** — live tonight, caveat notwithstanding; burns trust
   on the tab's namesake job.
6. **Watched folders skip subfolders** — real matter trees need leaf-by-leaf setup.
7. **25MB upload cap** with no guidance on oversized files.
8. **Placeholder Billing/Referrals tabs** in primary nav.
9. Fixed 4-type review taxonomy; custom questions not persisted as a playbook.

## 3. (b) Capability gaps vs what a paying attorney needs

1. **Outlook** — for most of legal, email ingestion effectively does not exist tonight.
2. **Windows build** — most of the profession excluded at the download link.
3. **Word-native output** — review ends in a memo, not a redline/Track Changes .docx; the
   category's deliverable is not producible.
4. **Editable playbooks** — firm positions cannot be encoded; review is generic.
5. **Practice-management/DMS connectors** (Clio, NetDocuments, iManage) — zero live; the
   integration-with-trusted-tools buying criterion (43% in survey data) is unmet.
6. **Per-document retrieval scoping** — the engine ceiling under gap 5(a); until fixed, Review
   accuracy is structurally capped.
7. **Matter export/sharing/handoff** — no way to get a matter out.
8. **Litigation surface** — deadlines/digest/every-mention help, but Review & Compare offers
   litigators nothing; half the persona's practice is chat-only.

## 4. (c) Genuinely excellent and differentiated

1. **The trust architecture is real and nobody else has it.** Mechanical span verification with
   never-false-accept, file+page citations that highlight the exact span, honest refusals,
   "not confirmed" states shown as such, caveats on every export. Competitors assert
   accuracy; this product demonstrates it per-claim. Against a market where 43% of non-users
   cite accuracy fear, this is THE differentiator.
2. **Local-first is absolute and verifiable** — loopback-only, egress-monitored in eval, no
   account, no cloud, free. The 37% data-security objection evaporates. No mainstream
   competitor can copy this without abandoning their architecture.
3. **First-run craft**: bundled Ollama, in-app model pull with real progress, seeded sample
   matter reaching a cited answer with zero setup, sub-minute onboarding. Day-1 wow moment
   exists and works.
4. **The job runner UX**: instant skeleton, live clause fill, cancel, zero-second reopen,
   staleness honesty, epoch-guarded streams. This is better streaming discipline than most
   funded legal-tech products.
5. **Email/folder ingestion honesty**: exclude-before-cap, attachments as first-class searchable
   children with provenance, suggest-then-confirm filing (never silent auto-file), heartbeats,
   fail-loud scan errors. Every design choice favors the attorney's ability to trust the corpus.
6. **"Every mention"** — a true exhaustive count aligned with the verifier is precisely the
   diligence primitive attorneys ask for and chat-only tools fake.
7. **Engineering discipline as a moat**: 63/63 golden gate, packaged smoke gate, five-for-five
   adversarial reviews catching a critical before ship. The defect rate a first week exposes
   will be low.

---

## 5. Verdict on the owner's question

**"Is this valuable enough yet for attorneys to use vs other applications?"**

Yes — for a narrow, real attorney: Mac (16GB+), privacy-motivated, Gmail-based, paper/transactional
practice, tolerant of a one-evening setup. For that attorney, tonight's product does the
document-Q&A job (where AI measurably beats lawyers — Vals: 94.8% vs 70.1%) with verifiable
citations no competitor offers, at a price (free) that removes the category's loudest objection.
The four known prospects should be onboarded this week, sitting next to them, because the walk
above predicts exactly where each will stall (RAM, Gmail app password, scans, subfolders).

No — as a general-market answer. The week-one funnel leaks at install (Windows, RAM, model wall),
at email (Outlook), at paper (Tesseract), and at the namesake Review tab (false "potentially
missing", fixed checklist, no redline output). Tonight the product is a superb *document
intelligence* tool wearing a *contract review* label it cannot yet fully honor.

The honest positioning for week one: sell the trust and the search ("ask your matter anything,
verify every answer, nothing leaves your machine"), treat Review as a checklist assistant with
its caveat front and center, and fix the two silent trust-burners (RAM gate, false-missing) before
widening the funnel — because in this market, per the adoption research, a burned attorney does
not come back and tells five colleagues.
