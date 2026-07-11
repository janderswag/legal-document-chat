# RUN_STATE.md — Current project status

> Single source of truth for "where are we right now." Update this after every working session.
> Read at the start of each session alongside `CLAUDE.md`.

_Last updated: 2026-07-11 (overnight sprint)_

## Status

**2026-07-11 overnight — v0.4.1 RELEASED: CONNECTORS FOR REAL + deadline calendar export
+ chat fixes. The "Make It Real" council sprint (docs/council/2026-07-10-council-make-it-
real.md) executed end to end. OWNER'S MORNING TEST: click "Update available v0.4.1" →
Settings → Connectors (28 services now listed and connectable — paste a key per the steps
in docs/2026-07-10-connector-registrations.md) → import lands in Unfiled → drag onto a
matter → open the matter → confirm a deadline → "Add to calendar" puts it in Calendar.app
with the source quote.** What shipped: (1) ROOT CAUSE of the unclickable connectors found
and fixed — PyInstaller never bundled the dynamically-discovered adapters
(pkgutil.iter_modules is invisible to static analysis; collect_submodules added to BOTH
specs), so every prior release shipped an EMPTY connector registry despite green source
tests; third instance of the source-tested/bundle-broken class. (2) The institutional fix:
build_macos.sh now runs desktop/smoke_packaged.sh automatically — launches the real built
.app headless against a scratch dir (guards: refuses without explicit env, never touches
the real data dir/port 8000, never touches the production Keychain key) and asserts 28
services + upload→ready + overview 200 + bundle version == appversion; SKIP_SMOKE=1 is the
only (loud) escape. v0.4.1's gate run: SMOKE PASSED. (3) Connect→import→Unfiled→drag
proven end-to-end in tests for Gmail/Zoom/Fireflies (191 connector tests green); catalog
verified honest, zero demotions needed. (4) Deadline → calendar: .ics export on confirmed
deadline rows, ATTORNEY'S date only (review found + killed a fallback to the document's
date), RFC 5545 escaped/folded, source quote in DESCRIPTION; persistent "not a complete
docket" disclaimer per ethics seat. (5) Copy-with-citations on every answer (WKWebView-safe
clipboard, honest failure feedback). (6) Owner's chat-splitting bug: root cause = any
failure between generation and the SSE done event lost the thread_id so the next send
forked a thread; citation enrichment AND message persist are now guarded (answer always
delivered), catalog got PRAGMA busy_timeout=5000 (background digest/ingest workers write
concurrently). (7) Trust polish: sample-matter suggested questions wait for readiness
(and sample docs are now digest-enqueued at seed — review caught a first-screen false
"could not be processed" path, fixed with a backfill-done guard); TM-exclusion failure
surfaces in Settings; overview empty state distinguishes building / no facts / N
unprocessable. (8) README rewritten (Heppner positioning per ethics wording, zero
em-dashes, all numbers traceable to eval artifacts) + docs/demo.png is now a real
screenshot of the matter overview. Review discipline paid every round: 6 sprint reviews
each found a Critical or Important finding, all fixed same-night (incl. Windows spec
silent no-op, smoke-mode safety guards, .ics date fallback, unguarded persist,
stuck-signal false positive). Answer path untouched all night (verified byte-identical;
the v0.4.0 63/63 gate stands). **⚠️ OWNER FOLLOW-UPS:** OAuth connectors
(Clio/Google/Microsoft/Read AI) still need your registrations; a real-account connector
pass is your highest-value manual check; WKWebView digest-confirm smoke in the updated
app; STILL no Time Machine backup.**

**2026-07-10 evening — MATTER DIGEST (M-2 keystone) BUILT AND GATED on branch
`feature/matter-digest` — NOT yet merged; owner actions at the end of this entry.**
The next-cycle plan's #1 item is implemented end-to-end: at ingest, a background pass
extracts span-verified facts (parties, dated items incl. deadlines, amounts, defined
terms, key refs) per document into `matter_facts`, mechanically gated by the existing
D-19 verifier normalization (`verifier.locate_span` — the LLM proposes, the check
disposes; a failed span is dropped and counted, never stored). Attorney judgment lives
in a separate `fact_review` table keyed by content hash (survives re-extraction);
**docuchat never computes a deadline date** — relative deadlines show source language +
an empty date field the attorney fills (owner-chosen design, spec:
docs/superpowers/specs/2026-07-10-matter-digest-design.md). The matter page now opens
overview-first (deadlines with confirm/dismiss, timeline, parties & amounts, collapsed
key terms — every row cited with click-through to the highlighted PDF span); digest
extraction runs on its own background queue (never delays time-to-searchable, yields
to chat) with a one-shot startup backfill; kill switch `LDI_MATTER_DIGEST=0`.
**GATES PASSED:** (1) full golden run on the branch: **63/63 present + 9/9 not-found +
0 rejected claims** (eval/results/run-matter-digest-gate.jsonl; answer path verified
byte-identical from the golden-run commit to HEAD — the fencing test pins that
answering/verifier/retrieval import nothing from the digest). (2) **G-DIG extraction
recall (new gate class): PASS at extractor digest-v4** — parties 8/8 (100%), amounts
9/9 (100%), date_events 18/21 (86%) vs targets 90/85/85, **0 spans dropped at the
mechanical gate**, against a hand-labeled 38-fact inventory over 4 corpus docs
(eval/digest_inventory.json + report). Getting there took four extractor iterations
worth knowing about: v1 groups blew the constrained-decode timeout (fix: 2-page/3000-
char groups + 600s cap + num_predict guard so stuck decodes terminate); v2 exposed that
the model routes party names/date kinds into wrong JSON fields (fix: deterministic
gate-side fallbacks using only verified content) and skips secondary amounts; v3's
"extract EVERY" prompt caused key_ref over-extraction spirals on definition-dense
pages (fix: key_ref bounded to identifiers + per-page fallback ladder so one bad group
can't blank a doc). Process: 8-task subagent plan, per-task adversarial reviews, and a
whole-branch final review that caught two Criticals pre-merge (Ollama outage would
have stamped permanent empty digests; the hub's 2s poll wiped the attorney's date
entry mid-typing) — both fixed + regression-tested. 50 digest tests green; pre-existing
env-dependent suite failures confirmed unchanged via stash-diff. **⚠️ OWNER ACTIONS:**
(1) packaged-app WKWebView smoke before release — specifically: open a matter, type a
deadline date, Confirm, watch the row flip to "confirmed by you" (WKWebView focus
behavior is exactly where this feature could differ from browser QA); (2) merge
decision on `feature/matter-digest`; (3) follow-up ticket: the SAME apostrophe-in-href
breakout we fixed in the new overview exists PRE-EXISTING in injectChips/
renderAnswerHtml (app.js ~1140-1160) — one small fix + test, separate diff; (4) value-correctness
spot grade DONE (eval/digest_spot_grade_v4.md): **zero date_iso violations across all
46 extracted facts** (the never-store-a-non-literal-date rule holds); 16/22 graded
faithful, 5 unfaithful — all labeling-quality issues (two no-date spans typed as
date_event, one address as key_ref, one d/b/a org_form, one missing anchor), none a
trust-surface risk since spans are verified and dates null; queue for an extractor v5
pass, not a blocker; (5) STILL no Time Machine backup.**

**2026-07-10 overnight — v0.3.2 RELEASED (uploads fix + self-healing startup). Keychain
incident RESOLVED. Owner action list at the very bottom.** Owner's fresh v0.3.1 download
would not launch ("docuchat could not start / port 8000" — a misleading message). ROOT
CAUSE: the data dir at `~/Library/Application Support/docuchat/` SURVIVES an app reinstall,
and its `.kb_catalog.db` was still encrypted with the master key overwritten in the D-81
incident, so the fresh app crashed opening it (confirmed: current key → "file is not a
database"). Delete-and-redownload cannot fix this because it never touches the data dir.
IMMEDIATE FIX (owner's machine): detached the leftover KB volume + moved the poisoned dir
aside to `~/Library/Application Support/docuchat.locked-20260710` (preserved, unrecoverable
synthetic data) → app starts clean. PRODUCT FIX (v0.3.2): `startup_recovery.py` runs first
at startup; if the catalog won't open with the current master key it moves the whole
encrypted data set aside (never deletes) and starts fresh — guarded so healthy/plain/
missing/empty/transient-keychain-lock states never touch data (7 tests). Also v0.3.2: the
WKWebView upload bug is fixed — profile-photo AND document uploads threw "The string did
not match the expected pattern" because fetch was handed a File object as body (WKWebView
rejects File/Blob bodies; Chromium accepts them, so browser QA missed it); all three upload
sites now send `await f.arrayBuffer()`. Landing demo re-skinned to the light-cream app
design (was stale dark-navy), live on docuchat.app. v0.3.2 signed+notarized+stapled,
Gatekeeper accepted, published as Latest — owner is on v0.3.1 so this is the FIRST real-
world test of the one-click in-place updater (v0.3.1 app should show "Update available
v0.3.2"). **⚠️ STILL NO Time Machine backup (`tmutil destinationinfo` = none) — owner
should set one up; a solo attorney machine with zero backups is its own risk.**

**2026-07-10 overnight — v0.3.1 RELEASED (security patch on top of v0.3.0).**
Post-release security review (skill + adversarial subagent) of the v0.3.0 diff found ONE
High: `connectors/gmail.py` opened `IMAP4_SSL(HOST)` with no ssl_context → CPython default
is an UNVERIFIED context (CERT_NONE), so a network MITM could present any cert, capture the
Google app password, and read the mailbox. FIXED: passes `ssl.create_default_context()`
(CERT_REQUIRED + check_hostname), regression-tested. Also hardened two defense-in-depth
items: Nextcloud forces https:// (Basic-auth password never cleartext) and connsync runs
the import fallback filename through the KB path sanitizer. The updater verify chain
(HTTPS + codesign + pinned Team ID before any swap), all 27 other adapters (httpx verify=True),
credential sealing, and UI esc() all reviewed clean. v0.3.1 signed+notarized+stapled,
Gatekeeper accepted, published as Latest. **⚠️ `tmutil destinationinfo` = NO destinations
configured — the keychain-incident recovery (restore login.keychain-db from a 07-07..07-09
backup) is NOT available; owner should accept the fresh re-seed and set up Time Machine.**

**2026-07-10 overnight — v0.3.0 RELEASED TO PRODUCTION: LIVE CONNECTORS (D-81) + in-place
updates + new site demo. ⚠️ READ THE KEYCHAIN INCIDENT PARAGRAPH BELOW FIRST.**
Release live and marked Latest (signed + notarized + stapled, Gatekeeper "accepted /
Notarized Developer ID"; releases/latest redirect verified). **Golden gate PASSED
pre-release: 63/63 present + 9/9 not-found + 0 rejected claims** (run-v030-gate) — the
engine is grade-identical with the speed quick wins in. Site deployed (Pages) with the
four-beat demo + updated security table. Jake's installed 0.2.0 app will show "Update
available v0.3.0" (opens the download page; TRUE in-place updates begin for users ON
v0.3.0 at the v0.4.0 jump — that path is unit-tested but gets its first real-world run
then).
Owner-directed overnight cycle (design spec: docs/superpowers/specs/
2026-07-10-connectors-v030-design.md). Shipped to main: (1) **connector platform** —
every one of the 65 catalog entries re-verified against CURRENT vendor API docs by an
11-agent research pass; 28 went LIVE with real adapters (paste a self-serve key ->
tested -> sealed via the Keychain master key -> documents import through the upload
path into the Document Hub with provenance + dedupe + optional 30-min sync; disconnect
deletes the key), 20 stay honestly Planned (need docuchat-registered developer apps —
owner action list in docs/2026-07-10-connector-registrations.md; Read AI turned out
OAuth-only, REVERSING the old "no registration gate" note), 17 DELETED (no user-reachable
pull path — incl. Evernote's suspended API and Filevine's zeroed downloads). 189 connector
tests green; live-verified in the preview (bad key -> honest error, nothing stored).
(2) **True one-click in-place update** (updater.py): download release DMG -> codesign
verify with team id PINNED -> rename-aside swap + rollback -> relaunch; failure leaves
the running app untouched. (3) **All 51 catalog brands have real bundled logos** (zero
letter tiles). (4) **Site**: hero demo rebuilt as four beats (cited answer / folder drop
/ connector import / one-click update) matching the current app IA; security copy now
lists connector + update-download egress honestly. (5) **Speed quick wins** (research
docs in docs/): bge-m3 pinned warm + preloaded, system-prompt KV warmed — no engine
semantics change. Memory design draft awaiting owner review (docs/2026-07-10-memory-
design-draft.md). Hub folder upload verified live (drag a folder OR "Upload an entire
folder…" picker).

**⚠️ KEYCHAIN INCIDENT (2026-07-10 04:59Z) — owner must read.** A pre-existing keyvault
bug (found tonight, now FIXED + test-pinned): any failed Keychain READ was treated as
"key missing" and add-generic-password **-U** then silently REPLACED the master key. A
sandboxed dev-server launch tonight triggered exactly that, so the machine's docuchat
master key was overwritten: the INSTALLED app's catalog and this checkout's dev catalog
are now undecryptable ciphertext (all synthetic data per hard rule #1 — no client data
exists on this machine). Nothing was deleted: the dev catalog is preserved at
pipeline/.kb_catalog.db.locked-20260710 and the installed app's data is untouched at
~/Library/Application Support/docuchat/. RECOVERY: restore ~/Library/Keychains/
login.keychain-db from any Time Machine backup made 2026-07-07→07-09 (the drive wasn't
mounted tonight), or accept a fresh start (the app self-seeds). The KB VOLUME key
(kb-volume-key-v1) was NOT touched. The fix ships in v0.3.0 and matters for real users:
without it, one locked-keychain moment = permanent data loss.

**2026-07-10 — v0.2.0 RELEASED TO PRODUCTION (signed + notarized, Gatekeeper-accepted).**
GitHub release live and marked Latest; docuchat.app download button serves it
(releases/latest redirect verified); site deployed with the D-78 security caveat; in-app
update checker verified against the live release (current 0.2.0 = latest v0.2.0, quiet —
flips to "Update available" at v0.3.0). v0.2.0 contains everything from D-75..D-80 (IA v3
+ Document Hub filing, onboarding/profile/memory, watched folders + folder upload, .eml/
.html/.vtt/.srt/.csv/.json import, connector catalog, billing/referrals pages, update
notifier, window-first launcher) on the unchanged 63/63-gated engine (model swap rejected,
D-79). Build recipe that worked: in ~/projects/legal-doc-intelligence (has corpus/eval/
build venv): `APPLE_DEV_ID_APP='Developer ID Application: Jake Anderson (8W2KYM5Y4J)'
NOTARY_PROFILE=docuchat-notary BUNDLE_OLLAMA=1 ./desktop/build_macos.sh`, then gh release
create with dist/docuchat.dmg. NEXT-CYCLE QUEUE (owner picks): (1) first API connector —
Clio Manage (blocked on owner registering a Clio developer app) or Read AI (no
registration gate, can start now); (2) background job center; (3) business-model decision
(license key vs seats) gates the real Billing build; (4) Windows build (owner box + Azure
signing); (5) Lock app; (6) deadline extraction; (7) formats needing deps: .msg/.mbox/
rtf/xlsx/zip + audio/video via local transcription; (8) Sparkle-style in-place updates.

**2026-07-09 late session (D-79 + UX-9/10 + connector strategy).** Model benchmark DONE:
qwen3.5:9b REJECTED (46/63 vs 63/63; abbreviates verbatim spans with `...` — verifier
rightly rejects; speed win marginal, p90 worse). qwen3:14b stays pinned (D-79). Shipped to
main: folder upload (webkitdirectory + recursive folder drop, strays skipped not errored,
UX-9); window-first launcher (instant branded splash instead of ~20s Dock bounce; live-
handles cleanup preserves the D-59 no-orphan guarantee; reaches users at next release,
UX-10). Connector roadmap decided in discussion (owner): Tier-2 import-only APIs next —
Clio -> notetakers (Read.ai first) -> CourtListener -> IMAP -> .msg, behind a "Connected
imports" switch with D-78-style disclosure. OWNER QUEUE unchanged: certs -> release cut.

**2026-07-09 UX cycles MERGED TO MAIN (owner-approved): D-75/D-76/D-77/D-78 all live on
main; `ux-v2` deleted.** Users get this when the next release is CUT — still blocked on
signing certs (desktop/SIGNING.md). At release-cut time: bump appversion.py, tag, and add
the site security caveat ("zero outbound except an optional daily version check").

**2026-07-09 UX-7/UX-8 cycles — owner-directed nav v3 + update check, SHIPPED on `ux-v2`
(D-77, D-78).** UX-8: one-click "Update available" above Billing — the ONE fenced
non-loopback call (daily GitHub version tag; lazy, toggleable in Settings > System,
disclosed; site security copy needs the "except optional version check" caveat at merge). After viewing
the UX-6 preview the owner redirected the IA: nav is now Chat / Chat History / Document Hub /
Review & Compare / Settings with Billing + Referrals pinned at the bottom. The Document Hub
is the filing cabinet: upload anything -> Unfiled (a real lazily-created matter) -> drag onto
matter folder cards to file (POST /kb/documents/move: DEK re-encrypt, re-index, 409 under
source-matter hold; per-row Move-to fallback). Search folded into the hub as "Find in
documents"; Chat is a single pane again. Billing = honest Pilot/free plan card + license-key
plan (no fake Upgrade buttons); Referrals = docuchat.app share link (rewards arrive with
licensing). UI-verified live incl. upload->Unfiled->move->drawer. OWNER QUEUE: preview at
127.0.0.1:8001/app -> approve -> merge ux-v2.

**2026-07-09 UX-6 cycle — Granola-inspired shell + profile/memory/connectors, SHIPPED on
`ux-v2`, AWAITING OWNER PREVIEW (D-76).** Owner benchmark vs Granola; billing/referrals/
sign-out/"personality" rejected as fake or off-brand surfaces (owner invited the pushback —
see D-76 for the reasoning and the honest equivalents shipped instead). Live on the branch:
light rounded sidebar with profile block (photo upload works), Settings sectioned
Profile | Connectors | Memory | System, Erase-all-data (typed confirm, hold-blocked),
teachable memory (fenced out of cited answers, tripwire-tested), watched-folder connectors
(e2e-verified: dropped file -> auto-ingest -> ready -> span-cited answer), .eml import,
onboarding polish. OWNER QUEUE: preview at 127.0.0.1:8001/app -> approve -> merge ux-v2;
decide the business model (license key vs subscription) before any billing build. Next
cycles queued: background job center; model tier benchmark; Lock app; deadline extraction.

**2026-07-09 UX-2 cycle — first-real-user feedback + attorney board -> SHIPPED on branch
`ux-v2`, AWAITING OWNER PREVIEW (D-75).** Owner filed the first real-user feedback batch
(hello triggers retrieval; tab-switch loses work; 8-item nav confuses; no onboarding;
"(Demo)" label; no compare picker); a 4-persona attorney board unanimously converged.
Shipped: small-talk gate (greetings never retrieve — canned uncited reply); IA v2 (nav
8 -> 5: Matters / Chat / Search / Review & Compare / Settings; matter = the case file with
upload + docs + chats + tools inside; history is a rail in Chat; review + compare are tabs,
launchable from a matter); lossless view switching (views build once — navigation never
destroys an in-progress chat/review/comparison); compare document picker (posts doc_ids);
onboarding (3 skippable screens; local-only profile: name + practice areas via /profile,
no contact fields by design; greeting + practice-tailored prompts; editable in Settings);
sample matter renamed "Sample Matter" with a label migration for existing installs.
Model stays qwen3:14b: the RAM-tiered Qwen upgrade path is research-mapped but gated on
its own golden-gate benchmark cycle (D-75). OWNER QUEUE: preview `ux-v2` at
127.0.0.1:8000/app and approve -> merge to main; then next cycles: background job center,
model tier benchmark, firm-name-at-export. (Standing queue from D-74 still open: delete
plaintext asides; approve site-preview; buy certs.)

**2026-07-07 encryption cycle — SHIPPED AND GATED (D-73, D-74).** The Move 4 deferred half
is live: measured prototype first (eval/ENCVOL_PROTO.md: attach 443.8ms median, +36.8ms
first-query overhead = 480.6ms, within the 500ms budget; per-matter volumes rejected at
~0.4s x N), then per-unit rehearse-migrate-drill: SQLCipher catalog (Keychain master key,
header-detect connect, rename-aside), KB store inside an AES-256 APFS sparse bundle mounted
AT `.lancedb_kb` (query path byte-identical; mounted first at startup, ejected on quit),
per-matter DEK-encrypted natives across upload/ingest/view/export (ingest scratch lives
INSIDE the mounted volume; export surrenders checksum-verifiable plaintext), and crypto-shred
at disposition — the certificate EARNS "Purge (cryptographic erase)" for originals only when
every native was encrypted and the DEK destruction happened; derived data honestly stays
Clear-inside-encrypted-volume. **[GATE] golden 63/63, NF 9/9, 0 rejected — grade-identical
to m1-secondpass (new mechanical scorer pipeline/score_golden.py); scale eval identical to
the D-69 baseline (dense golden 98%, all other classes 100%, pool 100%).** 394 tests green.
OWNER QUEUE: delete the plaintext asides after verifying real queries
(`pipeline/.kb_catalog.pre-enc-*.db`, `pipeline/.lancedb_kb.pre-encvol-*`); approve
site-preview (now incl. the updated security.html encryption block); certs -> first build.

**2026-07-07 roadmap execution — ALL MOVES 0-5 COMPLETE (D-68..D-72).** Move 2 (D-70):
transcript engine — user-designated transcripts get DERIVED page:line citations (verified
offsets through a line map; ambiguous spans fall back to page-only; condensed 4-up sheets fail
loud); deposition digest map-reduces ALL pages with per-bullet mechanical verification and
exports a Word table; live e2e cites p.4:14 on a synthetic depo. Move 3 (D-71): trust pack —
TrustedHost + Origin guards (rebinding/CSRF proven blocked live), Ollama version floor +
OLLAMA_ORIGINS, digest-pinned model pulls, Time Machine/Spotlight exclusions reported in
Settings. Move 4 (D-72): retention — legal holds (block disposal, 409), export-everything zip,
disposition with an HONEST Clear certificate (NIST 800-88r2 App. C model; Purge only when
crypto-shred ships), hash-chained audit log with tamper detection; per-matter ENCRYPTION
deferred by design (docs/2026-07-07-retention-encryption-design.md — needs its own cycle).
Move 5: verification-methodology page + pin-cite positioning. SITE: all customer-facing changes
live on the pushed `site-preview` BRANCH (2e transcript claims, 3d security page + security.txt,
5a/5b verification page + lede) — preview at 127.0.0.1:8090; merge to main only after owner
approval. 359 tests green; standing gate 63/63. OWNER QUEUE: approve site-preview; buy certs
(desktop/SIGNING.md) then build_macos.sh; Windows build on owner box; encryption cycle next.

**2026-07-07 roadmap execution — Moves 0-1 COMPLETE (D-68, D-69).** Move 0: the ~90-doc
allowlist bomb is fixed (matter-scoped retrieve p95 191ms @150k chunks, gate
grade-identical); ingest is serialized + instrumented with interactive priority (/chat
median unchanged during a 300-doc bulk ingest); site honesty patch shipped (NOTE: it
rode along on a backend push without owner preview — copy-accuracy only; process fixed:
future site work goes on a site-preview branch). Move 1: standing scale eval built
(`eval/SCALE_EVAL.md`; 5,114 chunks, 50 large matters, per-class); data kept hybrid AND
rerank OFF (both measured harmful); production chunking is now section-aware with full
SAC + document_type/provenance/doc_date schema (golden recall@5 81%->98%, pool 100%;
`reingest_kb.py` migrates old stores); refusal-triggered anchor-fed second pass; GET
/search with exhaustive "every mention" + BM25 modes and a Search view. **[GATE] 63/63 —
best ever; the second pass recovered F-026 (open since D-40).** 331 tests green. Next:
Move 2 (transcript engine: page:line derived from verified offsets, speaker-aware
chunking, transcript eval fixtures, depo digest + Word export), then Move 3 trust pack,
Move 4 retention build, Move 5 eval-methodology page.

**2026-07-07 session (P0-P3 speed/onboarding/packaging/site, D-63/D-64/D-65).** PUSHED to main:
(1) **P0 speed** — the app UI's default answer path is now SSE `/chat/stream` (retrieved passages
render first, tokens stream, verifier-confirmed citations replace everything on done; verifier
untouched); production inference is warm + right-sized (`keep_alive=30m`, `num_ctx=8192`, startup
preload; launcher starts a managed flash-attention Ollama when none runs). **[GATE] re-run: 62/63 =
98.4%, 0 fabrications — grade-identical to M2-8a.** Cold-start cliff closed (post-preload
`load_duration` 0.141s). TTFT median 3.45s under heavy machine load (see `eval/LATENCY.md` caveats);
<3s target still honestly unmet. (2) **P1 onboarding** — fresh installs seed a synthetic Sample
Matter (cited answer with zero setup, e2e-tested); guided first-run empty states + persistent
default active matter; the setup wizard now DOWNLOADS models in-app with a progress bar
(pinned-model allowlist). (3) **P2 packaging** — frozen-launcher relaunch bug fixed (in-process
uvicorn under `sys.frozen`); macOS build kit (`desktop/build_macos.spec/.sh`, entitlements,
notarization flow) + `desktop/SIGNING.md` owner checklist; **certs are the only missing input**
(Apple Developer ID + notarytool profile; Azure Trusted Signing/OV for Windows). LOCAL, HELD for
owner preview on `127.0.0.1:8090` (commit `fa2b6fb`, do NOT push until approved): honest site
platform claims (no "available today" for never-shipped artifacts; run-from-source is the primary
card) + privilege-safe wedge lede. 313 tests green. Next: owner approves site preview -> push;
owner buys certs -> run `desktop/build_macos.sh` end-to-end and cut the first release.

**2026-07-07 council (D-66).** Six-agent council (3 measured code audits + 3 cited market sweeps)
synthesized in `docs/council/2026-07-07-council-scale-transcripts-trust.md`. Critical: the app is
unusable at ~90 docs due to a full-store scan in the matter allowlist (`retrieval.py:36`,
measured); dense-only retrieval already fails exact-term queries; transcripts are effectively
unsupported while the site claims "exact line" (copy fix owed); security proof gaps enumerated
(Ollama hardening, at-rest encryption, backup exclusions). Market: the
local+solo+legal+verified-citations cell is empty; Heppner + sanctions wave are the demand
events; docuchat.io naming collision needs an owner decision. Proposed roadmap Moves 0-5 in the
council doc — **adoption + sequencing await owner sign-off; site copy fix and Move 0 scale bombs
are the immediate candidates.**

---

**🎉 MILESTONE 2-3 COMPLETE (2026-06-20, D-44).** All M2 build tasks done + independently
Tester-confirmed: page-accurate ingest → chunk+SAC → LanceDB → matter-pre-filter → grounded answering →
**mechanical span verification**, exposed over a **loopback FastAPI surface** (M2-7, D-41) and packaged
as **single-service Docker Compose** (M2-9, D-43). **M2-8 = FINAL PASS** at the page+span bar (D-40):
**62/63 = 98.4% (≥95%)**, **0 displayed fabrications**, NF 9/9, DRM 2/2, under egress-monitored SC-6
(D-31). The custom pipeline **delivers the verifiable page+span citation the turnkey stack proved
impossible** (M1, D-29). **Still owner-gated, NOT started:** M4-5 production hardware (after the attorney
demo; no purchase on spec, D-21/D-22) and M6 real attorney data (onsite, written approval; hard rules
#1–#2). Relay is **idle at a clean milestone boundary** awaiting owner direction. _History below is the
M1 record._

---

**🎉 MILESTONE 1 COMPLETE — M1-13 = PASS (filename level); M2-3 build AUTHORIZED (owner, 2026-06-20,
D-33).** Full 72-question run done + independently reproduced, egress-monitored (0 non-loopback, SC-6,
D-31). Final metrics: **citation 63/63 = 100%** (filename, D-29/D-32), **0 fabricated**, **NF refusal
9/9 = 100%** (substance, D-30), **DRM 2/2**. The turnkey AnythingLLM+Ollama stack is validated for
grounded local RAG + filename grounding + not-found refusal; verifiable **page+span** citation is
proven impossible on it → reassigned to the now-authorized **M2-3 custom pipeline** (D-13..D-20). No
hardware purchase yet (M4-5). **Next: M2-3 planning** (custom FastAPI + LlamaIndex + Docling +
Qdrant/LanceDB + reranker + mechanical span verification) — see `BUILDER_STATE.md` §7 carry-forwards;
M2 writes application code + needs new installs, each owner-gated. ✅ RESOLVED (owner, D-29): M1-7c proved AnythingLLM 1.14.1's PDF parser flattens pages
(empty chunk metadata) → verifiable page-level citation is impossible on the turnkey stack. M1 is now
scored at **filename level** (answer-correctness + filename grounding + DRM + refusal); **verifiable
page+span citation is reassigned to M2-3** (Docling + mechanical span check, per D-19). The page-level
miss is itself a primary M1-13 go/no-go input justifying the M2-3 build — not a silent pass.**

The CE_PLAN is finalized and validated. No application code exists and none should be written until
the Milestone 1 turnkey pilot proves citation accuracy. The repo holds planning/governance docs plus
the tracked `eval/` golden manifest; synthetic source documents live only under the git-ignored
`documents/synthetic_corpus/`.

Project lives at `~/projects/legal-doc-intelligence/` (moved out of `~/Desktop/` on 2026-06-19 so no
unrelated parent `CLAUDE.md` bleeds in) and is now a git repo. The proposal-agent on the Desktop is
untouched.

## Active milestone

**Milestone 1 — Turnkey pilot, citation accuracy proven (fake docs).**
Ollama + AnythingLLM, `qwen3:14b` + `bge-m3`, sanitized corpus, 50+ golden eval questions, measure
citation accuracy + not-found refusal. This milestone is the go/no-go gate before any custom code or
hardware purchase. See `TASKS.md` for the M1 checklist.

## Completed tasks

- Read and confirmed `README.md` and `CE_PLAN.md` (17 sections) as source of truth.
- Created `CLAUDE.md` (project governance + safety rules + M1 scope).
- Created `TASKS.md` (Milestone 1 checklist only).
- Created `DECISIONS.md` (decisions locked from CE_PLAN).
- Created this `RUN_STATE.md`.
- **Governance fix (Reviewer-required):** corrected the M1-6 corpus path. Synthetic source
  documents must live under the git-ignored `documents/synthetic_corpus/` (never an unignored
  `corpus/`); only metadata/templates are tracked under `eval/`. Recorded as decision **D-28**;
  defined the M1 ground-truth manifest schema in **`eval/README.md`** with a tracked template
  `eval/manifest.template.jsonl`.
- **M1-6 — Sanitized corpus assembled.** Authored 6 synthetic documents under the git-ignored
  `documents/synthetic_corpus/` (MSA, commercial lease, complaint, summary-judgment order,
  public-domain statute excerpts, demand letter) covering all four required `document_type`s, each
  with the page-1 banner and explicit `===== PAGE N =====` markers. Built the tracked ground-truth
  manifest **`eval/golden_manifest.jsonl`**: **63 present-fact records** (each verified to appear on
  its cited file+page) + **9 not-found records**, including a **DRM pair** (identical indemnification
  clause in two different matters, F-009/F-025). A verification script confirmed all spans resolve,
  absent topics are truly absent, corpus bodies are git-ignored, and only `eval/` metadata is
  tracked.

- **M1-8 / M1-9 — Golden eval question set + test plan.** Authored `eval/golden_questions.jsonl`
  (72 questions, one per `fact_id` — 63 present + 9 not-found, validated 1:1 with the manifest) and
  the tracked `eval/TEST_PLAN.md` (run procedure, scoring rubric, thresholds, go/no-go). Added
  `eval/results/` to `.gitignore` so raw run outputs are never committed.
- **Refusal-scoring decision (owner-approved).** The not-found safety gate scores on substance
  (refuses + cites nothing); the exact CE_PLAN §10 / D-5 sentence is pinned via the M1-5 workspace
  prompt and tracked as a separate UX flag `refusal_wording_exact`, not a hard-zero fail. Encoded in
  `eval/TEST_PLAN.md` §3.2. (Promote to a DECISIONS.md entry once the prior agent's uncommitted edits
  are committed.)
- **M1-1 — Ollama installed and verified.** Installed via Homebrew (native formula, no Docker;
  Ollama 0.30.10). Server confirmed on `127.0.0.1:11434` (`/api/version` round-trip) and bound to
  **loopback only** (`lsof`/`netstat` show `127.0.0.1:11434 LISTEN`, not `0.0.0.0`); `OLLAMA_HOST`
  unset. No public exposure.
- **M1-2 — AnythingLLM installed and launched (owner-approved fresh install).** `brew install
  --cask anythingllm` 1.14.1 (native macOS app, no Docker) → `/Applications/AnythingLLM.app`.
  Launches cleanly (Electron main PID 12860 + GPU/Renderer helpers). On launch it opened **three
  listeners, all loopback-only**: `127.0.0.1:3001` (internal server), `127.0.0.1:8888` (collector),
  and a **bundled `llm serve`** at `127.0.0.1:64562` — **no `0.0.0.0/*`**. Scope held: no workspace,
  no document load, no model pulled by us, no Ollama wiring. **Note for M1-5:** AnythingLLM ships its
  own embedded Ollama/llm runtime; wiring must point at the SYSTEM Ollama (`127.0.0.1:11434`,
  `qwen3:14b`/`bge-m3`), not the bundled engine.
- **M1-3 — `qwen3:14b` pulled to the SYSTEM Ollama (owner-approved).** `ollama pull qwen3:14b` on the
  system instance (`:11434`, not the bundled `:64562` engine). `ollama list` shows `qwen3:14b`
  (digest `bdbd181c33f2`, 9.3 GB; models dir ~8.6 GB on disk). Trivial `/api/generate` returned
  exactly `ok` (`done_reason: stop`); first call 5.89s total (5.47s model load, sub-second eval) —
  warm first-token comfortably under the <3s target. Binding re-verified **loopback-only**
  (`127.0.0.1:11434`), `OLLAMA_HOST` unset. The model-registry download was the only outbound traffic.
- **M1-4 — `bge-m3` pulled to the SYSTEM Ollama (owner-approved).** `ollama pull bge-m3` on the
  system instance (`:11434`, not the bundled `:64562` engine). `ollama list` shows `bge-m3:latest`
  (digest `790764642607`, 1.2 GB; models dir ~9.7 GB on disk with both models). `/api/embed`
  round-trip returned a genuine **1024-dim numeric vector** (not chat text) — confirms it works as an
  embedding model. Binding re-verified **loopback-only**, `OLLAMA_HOST` unset. Registry download was
  the only outbound traffic.

- **M1-EH (app-level) — AnythingLLM telemetry disabled + egress characterized.** Set
  `DISABLE_TELEMETRY='true'` in AnythingLLM's own `storage/.env` (backup `.env.m1eh.bak`); did not
  touch the bundled-engine wiring. Restart **log-confirmed** `[TELEMETRY DISABLED] … no events will
  send` (before: `[TELEMETRY SENT]` server_boot/onboarding/workspace_created, leaking config
  metadata to Mintplex over Cloudflare — now stopped). Measured before/after launch egress: the
  data-bearing **anonymous-telemetry HTTPS (Cloudflare)** is gone, but a **residual at launch
  remains — Chromium DoH/encrypted DNS to the ISP** (`doh-01/02.spectrum.com`, Charter), which **no
  AnythingLLM setting controls**. No document-bearing egress (no docs loaded); system Ollama
  (`:11434`) zero outbound; loopback listeners (`:3001/:8888` + bundled `llm` on an ephemeral
  loopback port) intact. **Zero app-outbound was NOT achieved by app-level alone.**
- **M1-5 — AnythingLLM wired to the SYSTEM Ollama (owner-approved).** Via the unauthenticated
  loopback API `POST /api/system/update-env` set `LLM_PROVIDER='ollama'`,
  `OLLAMA_BASE_PATH='http://127.0.0.1:11434'`, `OLLAMA_MODEL_PREF='qwen3:14b'`
  (digest `bdbd181c33f2`), `EMBEDDING_ENGINE='ollama'`,
  `EMBEDDING_BASE_PATH='http://127.0.0.1:11434'`, `EMBEDDING_MODEL_PREF='bge-m3:latest'`
  (digest `790764642607`) — **system instance, not the bundled `:64562` engine**;
  `DISABLE_TELEMETRY='true'` preserved. Created the **`m1-golden`** workspace (chatProvider `ollama`,
  chatModel `qwen3:14b`) with the CE_PLAN §10 grounded-citation system prompt (refusal sentence
  pinned per TEST_PLAN §3.2). Round-trip via `/api/v1/workspace/m1-golden/chat` returned a coherent
  `qwen3:14b` reply and `/api/ps` on `:11434` then showed `qwen3:14b` loaded → proves the system
  instance served it. Listeners all loopback (`:11434`, `:3001`, `:8888`); telemetry still disabled.
  _Notes: (a) this AnythingLLM 1.14.1 build's HTTP `stream-chat` route swaps into agent mode, so the
  stable round-trip/eval path is the **v1 API** (`/api/v1/workspace/{slug}/chat`); a loopback-only
  API key was minted in the app DB for this (secret NOT committed). (b) `qwen3:14b` is a thinking
  model — replies include `<think>…</think>`; strip/handle at M1-10. (c) harmless stale
  `ANYTHINGLLM_MODEL_PREF='qwen3-vl:4b-instruct'` remains in `.env`, unused now that provider=ollama._
- **M1-7 — Synthetic corpus embedded into `m1-golden` (owner-approved).** D-11 digests re-verified
  before embedding. Uploaded all 6 docs from `documents/synthetic_corpus/` via the v1 API (original
  filenames preserved) and embedded via **`bge-m3` on `:11434`** (`/api/ps` showed `bge-m3:latest`
  load during the embed; before: empty). **6/6 embedded, error: None**; LanceDB namespace
  `m1-golden.lance` created; loopback-only; telemetry still disabled. **Per-doc chunk count = 1
  each (total 6)** — docs are small (317–809 tok) and the M1-5 `EMBEDDING_MODEL_MAX_CHUNK_LENGTH=8192`
  makes each whole doc one chunk. **Risk:** with 1 whole-doc chunk and Markdown having no real pages
  (the `===== PAGE N =====` markers are inline text), AnythingLLM cannot emit page-level citations as
  configured → likely fails M1-11 `page_match`. **For M1-7b:** lower chunk size and/or revisit the
  deferred PDF-render path before M1-10.
- **M1-7c — Page-faithful PDF re-ingest (owner-approved; KEEP page-level).** Rendered all 6 docs to
  paged PDFs (no-install headless Google Chrome `--print-to-pdf`, one physical page per
  `===== PAGE N =====` marker) under git-ignored `documents/synthetic_corpus/pdf/`. Fidelity: PDF
  page counts == manifest max page (3/3/3/2/2/2); **63/63 present-fact spans on the correct page** (62
  exact via PDFKit + 1 confirmed `twenty-four` hyphen-wrap artifact). Manifest filenames updated
  `.md`→`.pdf` (**extension-only**, 63 records, proven identical after stripping extension). Replaced
  the Markdown in `m1-golden`, lowered chunk size (`EMBEDDING_MODEL_MAX_CHUNK_LENGTH='1000'`),
  re-embedded the 6 PDFs via `bge-m3` on `:11434`: **6/6 clean, chunks 6→16**; loopback-only;
  telemetry disabled; no corpus bodies tracked. **🚩 Blocking finding:** AnythingLLM 1.14.1's desktop
  PDF parser **flattens pages into one `pageContent` blob; chunk metadata is empty (no page field)**,
  so chunks carry no page number — page-faithful PDFs alone do **not** make the turnkey stack emit
  page citations. M1-7b's live probe is decisive; feeds M1-13 go/no-go.
- **M1-7b — Query mode + 32K context + validity probe (owner-approved).** Persisted **query mode**
  on `m1-golden` (DB `chatMode='query'`); raised context to **32768**, **verified effective** via
  `/api/ps` (`qwen3:14b context_length=32768`, no OOM); §10 grounded/refusal prompt active. Probe via
  v1 query chat (`<think>` stripped, sessionId per Q): F-001 → "March 14, 2024" + citation
  `nimbus_pemberton_msa.pdf` (matches manifest); F-004 → "$47,350" + same file (matches);
  NF-001/002/003 → exact **"I could not find this in the documents."** (refused, no substantive
  claim). **Query mode FIXES the M1-5 "Blue." world-knowledge leak.** Loopback-only; telemetry off.
  **🚩 M1-10 scoring note:** query mode **always** returns a `sources` array (retrieved chunks) even
  on refusal — §3.2 "cites nothing" must be judged on the **answer's asserted** citations, not the
  `sources` array, else every NF false-fails. Present-fact answers self-assert a page in prose but
  page is unverifiable (D-29) → score **filename only**.
- **M1-10/11/12 — Full golden run + measurement (owner-approved).** Posed all **72** questions via v1
  query chat (fresh sessionId/Q, single-turn, `<think>` stripped); 72/72 captured, 0 errors →
  git-ignored `eval/results/run-2026-06-20-qwen3-14b.jsonl`. **Egress-monitored (D-31, networking ON):
  74 snapshots, 0 non-loopback, max established=2 (loopback only)** → SC-6 met
  (`egress-2026-06-20.log`). **Manual grading** (no auto-scorer; read each answer vs the manifest,
  per D-29/D-30 → `grades-2026-06-20-qwen3-14b.md`): **citation accuracy 63/63 = 100%** (≥95%),
  **fabricated filenames 0**, **NF refusal 9/9 = 100%** (exact D-30 sentence; no asserted citation),
  **DRM 2/2 = 100%** (F-009→Pemberton MSA, F-025→Castellano lease; no cross-matter). Perf
  (informational): mean 19.2s, max 77.9s total/Q (thinking model; first-token not separately
  instrumented), no OOM at 32K. **All four §4 gates met → Builder RECOMMENDS M1-13 PASS.**

_Synthetic/public-domain content only; no application/pipeline code, no PDFs, no real documents.
Install + wiring chain (M1-1…M1-5) complete and verified loopback-only; M1-EH app-level telemetry
disable done; M1-10 air-gap is **egress-monitored** (D-31), not physical disconnect._

## Next task

**✅ docuchat.app launch batch SHIPPED + LIVE (D-61, Tester GREEN ×8 on `b1acb0a`, 2026-06-30).** 276/276,
baselines byte-identical, app untouched, Windows branch + POSIX green, phone-leak guard clean, CSP renders.
**Deployed:** pushed `main` (`c2b5595`), GitHub Pages enabled (Actions build), custom domain set, cert
provisioned → **`https://docuchat.app` is live with a valid Let's Encrypt cert + Enforce-HTTPS on**; www→apex
301; CSP/referrer/security.txt in place. **Lone open item (owner decision):** gold link text `#9a7727` on
white = 4.16:1, just under WCAG AA 4.5:1 (buttons fine) → darken link-gold or make body links navy. **Still
owner-side:** run the Windows build on a Windows box → `docuchat-setup.exe` → attach to Release (button stays
"soon" until then); swap the official Product Hunt badge SVG; optional Cloudflare-proxy HSTS hardening.

**(superseded plan) ▶ docuchat.app launch batch (D-61, owner-directed 2026-06-30; Builder prompt emitted).** Rebrand
public `site/` → **docuchat.app** + repalette to **navy/light-gray/white + GOLD** (60-30-10), recolor the
logo lock-shield gold + ship it as inline SVG, add **Cal.com** "book a call" + email + GitHub +
**Product Hunt** badge + OSS star/share/PR band + `at1.png` problem illustration, strip em-dashes, broaden
"solo attorney". **Windows: scaffold only** (PyInstaller `.spec` + build script + `desktop/WINDOWS_TEST.md`
+ launcher cross-platform fixes — owner builds the `.exe` on Windows). **Deploy:** GitHub Actions Pages
workflow for `site/` + `site/CNAME=docuchat.app`. **DNS already wired by Planner** (Cloudflare apex+www
CNAME → janderswag.github.io, DNS-only; apex resolves to GitHub Pages IPs). Planner finishes Pages
custom-domain + Enforce-HTTPS after the first deploy. Marketing-site-only; pipeline/verifier/air-gap app
untouched. _Absorbs the v1.1 "broaden copy" + root-route items below; the v1.1 launcher hard-kill +
wizard auto-pull remain a separate desktop batch._

**✅ T-CLAUSE DONE (D-52, Tester-confirmed GREEN ×6 + Planner-verified, 2026-06-21).** Contract Review
clause checklist complete end-to-end (5 layers, no stubs): 20-clause taxonomy + `extract_clauses()`
3-status classify + loopback API + UI panel + tests. Never-false-accept held on every path; 159/159 suite;
baseline byte-identical; 0 non-loopback (PID-scoped). **2 yellows → folded into T-TBL step-0:** add doc_id
post-filter regression test; commit untracked files. KB matter slug = `pemberton-demo`.

**✅ T-TBL DONE (D-53, Tester GREEN ×7 + Planner-verified + committed, 2026-06-21).** Docling TableFormer
tables end-to-end: extraction (offline, no runtime fetch) → markdown-per-table chunks (self-relative
offsets, `[TABLE]` tag) → KB-scratch embed/index → **span-verified** table answers ($132,300 cite on
`exhibit.pdf` p2) → source viewer. **Never-false-accept holds for table chunks** (fabricated/altered values
reject); **offset-routing per D-51** (table self-relative, prose PyMuPDF byte-identical, never mixed);
`has_tables` gating; 175/175; baselines byte-identical; PID-scoped 0 non-loopback. Committed (governance +
feature). **Carry-forwards:** TABLEFORMER_REVISION code-enforce (a); prune synthetic KB matters before demo (c).

**✅ M-ENRICH backlog COMPLETE (D-55, Tester GREEN 240/240 + Planner closeouts + committed, 2026-06-21).**
T-GRID + B1–B6 + C1/C2 + D1 all done; never-false-accept holds across grid/streaming/fuzzy; bounded
concurrency; no leak; baselines byte-identical; 0 non-loopback. Closeouts applied: canonical
`scripts/baseline_hash.sh` (+ re-pinned audit canon above); empty leftover dir removed; A0 import-time
air-gap fix (yellow closed, 20 table tests green). **F-026 fix PROVEN** (C1: top-k×N+rerank → None→rank3)
but baseline-affecting → **owner decision to adopt** (not self-applied). `eyecite` held `[GATE]`.

**✅ Desktop packaging v1 DONE (D-59, Tester GREEN + committed `c0400cb`):** macOS pywebview launcher +
in-app first-run wizard + landing page; 257/257; baselines untouched; footprint pywebview+pyobjc.
**✅ Landing redesign DONE (Planner-built live, `7ea6c43`, 2026-06-30):** white incident.io-style hero,
**animated demo** (`site/demo.html`), setup stack-diagram. _Pending uncommitted: "transcripts" in hero lede._
**🍎 Distribution finding (D-60):** direct notarized download works WITH Ollama (Phase B path); **Mac App
Store is BLOCKED by the Ollama dependency** (sandbox + self-contained) → launch direct-download first, sell
via license keys (App Store needs embed-the-engine, a later milestone).

**▶ NEXT: Desktop v1.1 follow-up (Builder prompt emitted).** Landing-page tweaks (attach `docs/demo.png`;
add a **non-clickable** demo-video placeholder; **broaden copy from "solo attorneys" → any attorney
office/practice**) + launcher **hard-kill hardening** (signal handler / process-group so a killed launcher
can't orphan the child). Then: **Windows pass** (owner's machine), then Phase B (embed engine + in-app
model download + frozen bundle) + signing + Store/monetization. Banked: owner's freemium pricing idea
(10 free / $20 / $50) — flagged for an enforcement-strategy brainstorm at the Store phase (OSS+local+MIT
makes doc-count paywalls hard to enforce). Demo video = owner-produced.

**(prior) ▶ Desktop packaging v1 (D-58 spec, owner-greenlit 2026-06-29).** Make the app downloadable +
add an onboarding flow + a landing page. **v1 scope (locked):** (1) landing page (`site/`, frontend-design
skill, GitHub Pages/Releases, local-testable); (2) **in-app first-run wizard** detecting Ollama + models
and guiding setup; (3) **macOS pywebview/tray launcher** around the existing FastAPI. **Deferred:**
PyInstaller-frozen bundle, **Windows (sequenced AFTER Mac — owner has a Windows machine to test on)**,
signing/notarization (Phase B). **Approved install: `pywebview`** only; else `[GATE]`. Wrap-don't-rewrite
(pipeline + verifier untouched); keep loopback-only + no telemetry at runtime. Builder prompt emitted;
recommend the Builder `/clear` first (big fresh-domain task). Loop cadence to align with the owner's
Obsidian flow. Spec: `docs/superpowers/specs/2026-06-29-desktop-app-distribution.md`.

**🌐 PROJECT OPEN-SOURCED (D-57, 2026-06-22):** public repo **github.com/janderswag/legal-document-chat**
(MIT). Pre-flight audit clean (no secrets/PII/real data in tree or history); `.gitignore` hardened; public
README/CONTRIBUTING/LICENSE + 12 topics + 5 good-first-issues; relay/governance docs kept at root → **ongoing
commits are public.** `origin` now set.

**▶ RELAY IDLE — at owner direction (2026-06-21).** Transcripts were brainstormed to a complete design but
the **build is DEFERRED / held in reserve** (D-56): depositions already work as normal Document-Hub uploads
(verified, page-level cites); page:line precision is built only if a real deposition proves page-level isn't
enough. Builder is clear-safe (`BUILDER_STATE.md` refreshed). **Queued owner decisions (none auto-start):**
adopt the F-026 fix (C1 proven, baseline-affecting), approve `eyecite` (`[GATE]` install), build the cheap
transcript gutter-strip, or pick OcrMac/MPS. **Parked future work (D-56):** transcripts page:line build;
agent personality for attorney comms. Owner-gated milestones unchanged: G-LAT latency, M4 UAT, M4-5
hardware, M6 real data.

### Audit canon (pin — stops audits diverging on representation; D-47/D-52/D-53/D-55)
- **Canonical hash script (use this ONLY — CWD-independent, all roles):** `scripts/baseline_hash.sh`.
- **Baseline store hashes (must stay constant; mtimes 2026-06-20), per that script:**
  `.lancedb=537146cf…`, `.lancedb_full=d329c91e…`, `.lancedb_hyb=07f04972…`. _(Supersedes the old
  path-sensitive `13b242de…`/`0df0525c…`/`51e13b31…` — same bytes, stable representation, D-55.)_
- **Egress-log line format:** `[timestamp] pid=<PID> sample=<n> established_nonloopback=<n> ollama_loopback=<n>`;
  monitors **PID-scoped** (`lsof -a -p PID -iTCP`) — a system-wide sample is not pipeline proof.

_History below is the M-ENRICH kickoff + M1 record._

---

**(Prior) T-CLAUSE-1 — clause-extraction core + taxonomy (M-ENRICH, D-49/D-51, 2026-06-21).** Owner
directed an OSS deep dive (9 repos → `docs/research/2026-06-21-oss-evaluation.md`); a second independent
Tester cross-eval converged (D-51). Adoption roadmap greenlit; all four threads in `TASKS_M2.md` →
M-ENRICH (T-CLAUSE → T-TBL → T-GRID; T-TRANS separate). **Owner picked clause-checklist FIRST** (cheapest,
attorney-legible, prose clauses don't need tables; becomes the grid's columns). Tables (T-TBL-1, model
fetch already approved) move to NEXT. **Comprehensive Builder prompt for T-CLAUSE emitted — one complete
feature end-to-end** (owner workflow preference, `[[feedback-builder-comprehensive-prompts]]`): CUAD-informed
clause taxonomy + `extract_clauses()` over the existing `answer()`+verifier (**span-verified per clause**,
D-19/D-38; refused → advisory "potentially missing", non-citable) + loopback API route + a **Contract
Review** panel in the SAM-style UI + tests at every layer. **No new install.** Test-first; baseline
`.lancedb`/M2-8 byte-identical (read-only); loopback-only + **real** egress samples (D-47). Relay resumes
Planner→Builder→Reviewer→Tester. Rationale: `DECISIONS.md` D-49/D-51. _Prior "owner direction" boundary
(below) resolved into this roadmap._

---

**Milestone 2-3 substantively COMPLETE (D-42) — owner direction needed for the next milestone.**
**✅ M2-7 = done** (D-41, Tester-confirmed 2026-06-20): thin FastAPI loopback surface (`pipeline/api.py`)
over `answer()` — `POST /answer` + `GET /health`, bound `127.0.0.1:8000` only, no auth, no action
routes (PUT/DELETE/PATCH → 405), matter validated against the D-35 allowlist, **HTTP body
byte-identical to a direct `answer()` call** (no model-asserted page reintroduced), 0 non-loopback
egress (`eval/results/egress-2026-06-20-m2-7.log`), clean shutdown. Install was FastAPI+uvicorn, pinned.
**Only M2-9 (Docker Compose, D-20) remains in M2 — deferred + owner-gated (new Docker/Compose install);
do NOT start without explicit owner approval.**

**✅ M2-8 = FINAL PASS at the page+span bar (D-39/D-40), independently Tester-confirmed (2026-06-20).**
M2-8a landed the verifier normalization fix — **`html.unescape` + strip backslash-escaped quotes**,
applied **symmetrically** to span + chunk text (on top of collapse-ws / `-\n`→`-`) — plus the F-042
**alternate-page** rule (TEST_PLAN §6.5) encoded in the verification path. Targeted re-run flipped
exactly **F-014** (`\"`) and **F-016** (`&quot;`) → verified (both chunk-derived **page 1**), **zero**
other facts changed (no regressions / no spurious verifications); conservative-failure invariant HELD
(a self-authored escaped-but-false span still rejects — no false-accept). **Final metrics:** page+span
citation **62/63 = 98.4% (≥95%)**, **0 displayed fabrications** (hard zero), **NF refusal 9/9 = 100%**,
**DRM 2/2 = 100%** (no cross-matter). **F-026 is the lone genuine miss — NOT force-passed** (a
retrieval-recall gap: page-1 caption occurrence not surfaced → model falsely refused; revisit via
top_k/reranker/chunking, `TASKS_M2.md` Risks). Loopback-only re-verified
(`eval/results/egress-2026-06-20-m2a.log`, 0 non-loopback, SC-6/D-31); raw re-run →
git-ignored `eval/results/run-2026-06-20-m2-rerun.jsonl`. **The custom M2-3 pipeline clears the
verifiable page+span bar the turnkey stack proved impossible (M1, D-29).**

**✅ SAM-style local UI COMPLETE (D-48, Tester-confirmed 2026-06-20). Next = OWNER DIRECTION.** The
SAM-inspired, **100% local/air-gapped** UI is built + independently verified (7 tasks 🟢, commits
`77a3b88`→`0e7abdb`): left nav (New Chat · Matters · Document Hub · Chat History · Settings), matter-scoped
upload+chat with chunk-derived/span-verified citations, retrieved-page thumbnails + **cited-span
highlight**, privacy "100% local · 0 outbound" badge. Dedicated **`.lancedb_kb`** store; eval stores +
M2-8 byte-identical; 88 egress rows, 0 non-loopback; product boundary held (no drafting/advice/actions/
CDN/cloud). Plan: `docs/superpowers/plans/2026-06-20-sam-style-ui.md`. **All work committed; tree clean;
app runs at `http://127.0.0.1:8000/app`.**

**Next = OWNER DIRECTION** (relay auto-starts nothing). Candidate directions:
- **Complete CE_PLAN Milestone 4** — the UI is the demo *surface*; M4 also needs a **user-guide draft +
  demo script** (synthetic), then the **attorney UAT** (owner-gated). This is the natural next step.
- **More UI polish** — additional SAM-style refinements / a Matters dashboard / Search view.
- **Close the lone yellow** — `<3s` first-token latency (G-LAT; validate on D-22 hardware vs. pilot).
- **Housekeeping** — remove the two synthetic test matters from the live catalog; capture an `/app`
  screenshot for the demo deck.
_Still owner-gated: M4-5 hardware (no purchase on spec, D-21/D-22), M6 real data (written approval). The
M2/M3 gap-closure (D-47) is done; latency is the one open §2/M3 yellow._

**(Prior boundary) M2/M3 gap-closure DONE; latency the lone yellow (D-47).** The 7-task gap-closure batch landed + was independently Tester-confirmed and
Planner-verified (commits `89c7c66`→`c2cc89f`; baseline `.lancedb`/M2-8 byte-identical; new stores
`.lancedb_full`/`.lancedb_hyb` git-ignored). **SC scorecard:** SC-1 🟢, SC-2 🟢 (capability; real-scan
validation = M6), §8 quarantine 🟢, hybrid 🟢 (off by default — negative lift at this scale), SC-7 🟢,
SC-3/4/5/6 🟢. **Lone yellow: `<3s` first-token NOT met** (~3.6s median; instrumented honestly) — a
§2/M3 quantitative target; the "production hardware fixes it" read is a **hypothesis** for D-22, not
proven. **Precise gate:** the CE_PLAN §2 "GO for attorney demo" gate is worded on SC-1…SC-7 → those are
all 🟢, so the demo-GO gate is met; but the `<3s` target is open, so **do not relabel M2/M3 "complete."**
**Owner's call next** (relay auto-starts nothing): proceed to CE_PLAN **M4 attorney-demo prep** /
chase latency first / something else. **Two loose ends to clear regardless:** (1) commit the uncommitted
prior-milestone code (M2-7/M2-9/UI); (2) latency is hardware-hypothesis, validate on D-22. Still
owner-gated: M4-5 hardware (no purchase on spec, D-21/D-22), M6 real data (written approval).

**(Superseded framing) M2-9 + D-44 milestone wrap.** M2-9 is
done (D-43, Tester-confirmed + Planner-verified against `Dockerfile`/`docker-compose.yml`): single-service
Compose, Ollama on host via `host.docker.internal` (bind unchanged, `OLLAMA_HOST` unset), published
**`127.0.0.1:8000:8000` only**, LanceDB volume-mounted read-only, `/answer` parity with `answer()`, 0
non-loopback egress, clean teardown. **⚠ Binding deploy constraint (D-43a): COMPOSE-ONLY** — a bare
`docker run -p 8000:8000` would expose `0.0.0.0` off-host (hard rule #4); deploy via `docker compose`
only.

The remaining milestones are **owner decisions, none auto-started**:
- **M4-5 — production hardware:** only after the attorney sees a demo; **no purchase on spec**
  (D-21/D-22).
- **M6 — real attorney data:** onsite, on attorney hardware, after **written** approval (hard rules
  #1–#2).
- **Optional pre-M4 / pre-M6 prep** (still synthetic, no new milestone gate): latency/thinking-mode
  tuning pass; M6 real-PDF section-heading robustness validation on heading-less PDFs.

**Open carry-forwards (none blockers; full list in `TASKS_M2.md` Risks):** F-026 recall gap;
`answering._norm` escape-alignment (fails safe); optional API hardening (`openapi_url=None`); compose-only
deploy guard/README; image leanness; Linux/CUDA portability of the host-Ollama path (D-43b).
- **Pre-M4 latency/thinking-mode tuning pass:** size a tuning pass on qwen3 "thinking" before any demo
  (M2 pipeline already much faster than M1 — mean ~6.9s/Q — but first-token vs the <3s CE_PLAN §2
  target is not yet instrumented).
- **M4-5 hardware:** owner decision only, after the attorney sees a demo; **no purchase on spec**
  (D-21/D-22).
- **M6 real-PDF readiness:** validate section-heading detection on heading-less real-style PDFs before
  any real-data work (onsite, written approval).
**Carry-forward risks (none blockers):** (a) real-PDF section detection before M6; (b) F-026 recall
gap; (c) `answering._norm` not yet on the verifier's escape-normalization contract (precision-only,
fails safe); (d) optional `openapi_url=None` API hardening — all tracked in `TASKS_M2.md` Risks.
_(M2 pipeline latency is much better than M1's AnythingLLM path — mean ~6.9s/median 7.0s/max 17.5s in
the M2-8 run; the ~19s figure below is the M1-10/turnkey number.)_

**Perf carry-forward (M2-3 / pre-M4 demo):** per-question latency was high (mean ~19s, max ~78s,
qwen3 "thinking"); first-token (<3s CE_PLAN §2 target) not separately instrumented. Size a
thinking-mode/latency tuning pass on the custom pipeline + production hardware. **Pinned digests
(D-11):** `qwen3:14b=bdbd181c33f2`, `bge-m3=790764642607`.

**⚠ Key go/no-go risk (M1-5 Tester flag — read before M1-10).** On the EMPTY `m1-golden` workspace a
non-legal trivia prompt returned "Blue." **with a fabricated citation** ("Weather Conditions, p.3")
instead of the §10 refusal. The turnkey stack has **no mechanical span verification** (that is M2-3 /
D-19) — the §10 prompt is the ONLY guardrail, and it already let a hallucinated citation through. This
is the exact **M1-12 (0%-hallucination refusal)** risk and likely the binding gate.
- **✅ RESOLVED in M1-7b:** root cause was **chat mode** (answers from world knowledge). `m1-golden`
  is now persisted to **query mode** and the M1-7b probe showed NF-001/002/003 all **refuse + cite
  nothing** with the exact D-30 sentence — the "Blue." leak no longer reproduces. M1-10 confirms at
  full scale. (Caveat carried to M1-10: score "cites nothing" on the answer's asserted citations, not
  AnythingLLM's always-present `sources` array.)
- **✅ Context window:** raised from **8192** to **32768** and verified effective via `/api/ps`
  (`context_length=32768`, no OOM) in M1-7b.
- **Run path / safety:** M1-10 poses questions via the **v1 query chat** (`/api/v1/workspace/
  m1-golden/chat`), single-turn, **never agent mode** (this build's `stream-chat` swaps to agent mode,
  which can use tools/web → would violate no-action/no-egress, CE_PLAN §3 #12). Strip `<think>…</think>`
  before scoring. Fabricated citations are **hard fails** (TEST_PLAN §3.1/§4).
- **Go/no-go framing:** if M1-12 cannot reach 100% after reasonable prompt/config tuning, that is
  itself the key datapoint — it would indicate the turnkey stack is insufficient WITHOUT the M2-3
  span-check, a legitimate input to the M1-13 decision (owner call), not a silent failure.

**M1-EH RESOLVED (owner decision).** App-level telemetry is disabled + log-confirmed. For zero-egress
(SC-6), the **M1-10 measurement run executes with networking OFF (air-gap)** — the loopback-only
pipeline works offline, which also moots the Chromium DoH/encrypted-DNS residual. **No host firewall
this cycle;** `pf`/Little Snitch are deferred to M5/M6 persistent-online hardening. The networking-off
step + an egress confirmation are folded into the M1-10 procedure (`eval/TEST_PLAN.md` §2).

_PDF rendering of the corpus (for true page-level citation testing) remains a follow-up that must use
a confirmed no-install path or its own approval._

**Air-gap posture (post-decision):** AnythingLLM anonymous telemetry is **disabled + log-confirmed**.
The remaining launch egress (Chromium DoH/encrypted DNS to the ISP) is handled by running M1-10 with
**networking off**, not a firewall. **Historical note (cannot be recalled):** a pre-disable
`workspace_created` event already shipped config metadata (model names / vector-db type / anon id) —
**no document content**; reinforces full air-gap from the start for M5/M6 real-data work.

## Blockers

- **None technical.** Install + wiring chain M1-1..M1-5 complete and verified loopback-only;
  **M1-EH resolved** (telemetry off; M1-10 runs air-gapped, no firewall this cycle). Next is M1-7
  (load the synthetic corpus into `m1-golden`) — synthetic docs only, no fresh install required. Per
  `CLAUDE.md`, nothing further is installed/configured without confirming the task calls for it.

## Standing reminders

- Fake/sanitized/public documents only. No real attorney/client data on this machine.
- Local-only; loopback binding; no public ports; no cloud dependencies without written approval.
- Do not scaffold the custom production pipeline (Milestones 2+) until the M1 gate passes.
