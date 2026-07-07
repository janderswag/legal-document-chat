# Council: Scale, Transcripts, and the Trust Product — 2026-07-07

Six independent agents reported: three adversarial engineering audits grounded in this repo
(scale-to-thousands with measured timings; transcript readiness; retrieval quality), and three
market research sweeps (competitor landscape; attorney jobs-to-be-done; security/retention proof
bar). Every engineering claim below carries file:line evidence in the underlying reports; every
market claim carries a source URL. This document is the synthesis: council verdicts, the
convergent findings, and a prioritized roadmap. Roadmap adoption is an owner decision.

Owner brief this council answers: a platform holding THOUSANDS of documents and transcripts,
searched fast; the gaps where an application like this brings attorneys more value; critical
review; sustained focus on data retention, security, and output quality.

---

## 1. Where we stand (context)

Shipped and pushed this morning (D-63/D-64/D-65): streaming default answer path (sources render
first, verifier untouched, gate re-run 62/63 = 98.4%, 0 fabrications), warm inference (cold-start
cliff closed), sample-matter onboarding with zero-setup cited answer, in-app model download with
progress, frozen-launcher fix + macOS build kit (certs are the only missing input), honest site
platform claims + privilege-safe wedge above the fold.

## 2. Council verdicts (each seat is deliberately critical)

**Head of Engineering — verdict: the architecture is sound; three small bombs make "thousands of
documents" false advertising today.**
The measured truth is better AND worse than assumed. Better: brute-force vector search is a
non-problem (96ms p50 at 500k chunks on the M4 Pro; no ANN index needed at target scale; the
matter pre-filter *helps* latency). Worse: `retrieval.py:36` materializes the ENTIRE store into
Python on every matter-scoped query to validate a matter name — measured 15.6s + 4.7GB RSS at
100k chunks, projected swap-death at 500k. The app becomes unusable at roughly NINETY documents.
Second: background ingest shares the request thread pool, so a bulk upload starves /chat for
hours, with 40-way parser thrash and LanceDB writer conflicts. Third: a 1.5-16h ingest is
completely uninstrumented — invisible to the user and to us. All three fixes are days, not weeks
(catalog-based matter validation [GATE re-run required]; a serialized ingest worker; per-stage
timing + progress). Also real: OCR reality check — a fully scanned corpus ingests at ~1.16s/page
(~16h per thousand 50-page docs); set expectations honestly ("scans ingest overnight") rather
than pretending otherwise. Generation (~18 tok/s) remains the UX floor; streaming was the right
ship.

**Search/IR lead — verdict: retrieval quality, not speed, is where "thousands of documents"
actually fails; the current eval cannot see it.**
The "hybrid off" decision was measured honestly on a 50-chunk corpus where top-5 is 10% of the
whole store — a regime where every ranker looks fine. Probes on our own store show dense-only
already failing the queries attorneys actually type: a bare bar number ranks 4th; an amount
without its dollar sign misses top-5 entirely; hybrid BM25 puts both at rank 1. False refusals
grow mechanically with corpus size (refusal ≈ 1 − recall@5 by construction); 10-25% on real query
mixes at scale is the honest estimate, concentrated on the highest-value identifier queries.
There is also NO search feature at all — every surface is QA-shaped; "find every mention of X,"
the most-used tool in document review, is unanswerable; doc-type filtering is impossible because
the store schema drops `document_type`. And production /chat runs on a POORER chunking pipeline
(empty section breadcrumbs) than the one the eval numbers were earned on. Nothing here requires
touching the verifier or matter isolation — every fix is upstream (candidates) or additive
(a /search endpoint). The gate for all of it: a 1k-5k-doc synthetic scale eval with per-query-
class metrics. We must not claim "thousands of documents" before that eval exists and passes.

**Litigation-support PM — verdict: transcripts are effectively unsupported, and the site
currently promises otherwise.**
No page:line concept exists anywhere in the schema. A `.txt` transcript — the standard court-
reporter delivery — ingests as a single "page 1," making every citation into a 300-page
deposition useless; E-Transcript/.ptx is rejected; a condensed 4-up PDF ingests silently with
page cites off by ~4x. The 900-char windowing orphans answers from questions and loses speaker
attribution — misattributing an objecting attorney's words to the witness is a malpractice-grade
error. The worst structural failure: "summarize what the witness said" retrieves 5 of ~500
chunks and produces a confidently partial summary — every quote verified, materially misleading
by omission. The good news is real: the verifier substrate is transcript-ready (page:line can be
DERIVED from verified span offsets without touching the verifier), a deferred transcript design
exists in-repo, and the five-feature build path (page:line ingestion → speaker-aware chunking →
map-reduce digest → exhaustive lookup → contradiction candidates) is concrete. Until F1 ships,
the site's "cited to the exact line" transcript claim is untrue in every input format — fix the
copy now under our own honesty rule.

**Security officer — verdict: "privilege-safe by architecture" is a strong posture with three
unproven load-bearing claims; closing them IS the product.**
(1) Loopback is not a security boundary: we auto-start an UNAUTHENTICATED Ollama (worst CVE
record in our stack — Probllama RCE, DNS rebinding that works despite loopback, May 2026
"Bleeding Llama" CVSS 9.1 memory leak) and our FastAPI has no TrustedHost/CSRF/origin defense —
every state-changing endpoint is reachable from a malicious web page the attorney visits.
(2) "Documents never leave the machine" is true on the query path while client text sits in
PLAINTEXT at rest (LanceDB OSS + SQLite have no encryption) and Time Machine/iCloud/Spotlight
silently copy it off-device — no exclusions set. (3) "Mechanically verified" is defensible ONLY
in its narrow honest sense (quote fidelity + existence); the moment marketing lets a reader hear
"verified = legally correct," we are standing exactly where LexisNexis's "hallucination-free"
claim got publicly dismantled and where the FTC's Workado order (numeric claims need published
methodology) bites. None of this is fatal; the fixes are enumerated, mostly small, and the
at-rest-encryption build pays twice — it closes the backup-leak gap AND enables per-matter
crypto-shred, which is the foundation of the retention product attorneys will pay for.

**Practicing attorney (the buyer) — verdict: I already pay cash for exactly what you want to
build; my trust threshold is brutal and specific.**
I pay $1-2.25/page for deposition summaries ($300-2,000 per transcript; $600-2,400/month for an
active litigation practice), $30-140/month for chronology tools, and 70% of my eDiscovery budget
on review. Only 22.1% of my peers report high trust in AI output; 69.7% of it needs rework; there
are 1,400+ court decisions involving fabricated AI content and sanctions to six figures; my
malpractice carrier tells me to verify everything and my judge now makes me certify it. What
wins me: page:line pin cites I can read into the record, a digest exported as a Word table (not
a chat bubble), a cite-checker that loudly separates "record cites: checked" from "legal
authorities: not checkable offline," and an answer that says "I could not find this" instead of
guessing. What loses me instantly: one wrong pin cite, a paraphrase that turns "did not recall
approving" into "denied approving," or discovering my "local" tool's index synced to iCloud.
Retention tooling (export-everything, provable deletion, certificate of disposition) maps to
duties I already have under Rules 1.15/1.16 and my OCGs — that is a paid feature, not plumbing.

**CEO/market strategist — verdict: the four-quadrant cell is empty and the macro events of 2026
point straight at us — but the window is time-boxed and the bear case is free.**
Nobody combines local + solo-priced + legal-specific + mechanically-verified citations; the
specific claim "every answer is programmatically checked against the exact source span, and
unverifiable output is blocked" is unclaimed by anyone (confirmed by third-party synthesis).
*U.S. v. Heppner* (S.D.N.Y. Feb 2026: consumer-AI chats waived privilege BECAUSE OF the terms of
service, with dicta favoring counsel-directed non-public tools) is the demand event for the
privacy half of the wedge; the 9th Circuit's first precedential hallucination-sanctions opinion
plus NY's certification rule (Part 161, June 2026) are the demand events for the verification
half. The $20-50/month legal-specific slot is empty (nothing between ChatGPT at $20 and Midpage
at $99), and Casetext's shutdown orphaned solos with $40-110/month anchors. The credible threat
is NOT Harvey — it is free OSS (AnythingLLM; Lavern, Apache-2.0 legal AI, June 2026) plus
OS-level local models commoditizing "local." Our moat must be the verification layer, transcript
page:line engine, and zero-config trust pack — never "local" alone. Two housekeeping calls:
docuchat.io is an active cloud SaaS named DocuChat (trademark/SEO/message collision — decide on
the name before serious launch marketing), and depo summaries are commoditizing toward free
(Steno bundles them) — we sell privilege-safe cited cross-transcript search at case scale, not
summaries.

## 3. Convergent findings (independent reports, same conclusion)

1. **Transcripts with verified page:line cites are the product.** Engineering says the verifier
   substrate supports it without weakening anything; the buyer pays cash for it today; the
   competitor landscape shows summaries commoditizing while cited cross-transcript search at
   case scale is open. Three reports, zero coordination, one answer.
2. **The verification wedge is real, unclaimed, and legally load-bearing** — but only at the
   defensible rungs: quote fidelity + citation existence, with published methodology, abstention
   rate reported, and explicit "does NOT mean legally correct" language. Overclaiming is the
   single fastest way to die (Lexis walkback, FTC Workado/Pieces, DoNotPay).
3. **"Thousands of documents" is 3 small fixes plus one honest eval away — not a rearchitecture.**
   The allowlist bomb, the ingest worker, instrumentation; then hybrid+rerank+/search gated on a
   1k-5k-doc scale eval. Brute-force vectors are fine. The claim stays off the site until the
   eval passes.
4. **Security proof beats security claims.** Ollama hardening + CSRF middleware + pinned model
   hashes + backup exclusions are small builds that neutralize our worst findings; at-rest
   encryption with per-matter keys unlocks crypto-shred → retention/legal-hold/certificates →
   the paid trust tier. "Confidentiality by architecture, not by contract" — never marketed as a
   legal guarantee.
5. **Honesty discipline has two open violations to fix now:** the site's transcript "exact line"
   claim (untrue in every format today) and any future accuracy number without published
   methodology.

## 4. Prioritized roadmap (proposed — owner sign-off required)

**Move 0 — Scale bombs + honesty patch (days).**
a) Replace the full-store matter-allowlist scan with catalog validation or a cached matter-column
scan (`retrieval.py:36`, `:28`) — [GATE]: full eval re-run (validation-path change).
b) Serialized ingest worker (dedicated thread + queue) replacing BackgroundTasks-on-request-pool.
c) Ingest instrumentation: per-stage timings, progress surfaced in Document Hub (per-doc + queue
counters), `table.optimize()` every N ingests.
d) Site copy: scope the transcript claim to what ships ("transcripts: coming — documents cited to
exact page and span today"); owner preview per deploy rule.
Acceptance: 1,000-doc synthetic ingest completes with visible progress while /chat stays
responsive; matter-scoped query p95 < 300ms at 150k chunks; eval grade unchanged.

**Move 1 — Retrieval at scale, honestly measured (1-2 weeks).**
a) Scale eval FIRST: 1k-5k synthetic docs (generators mostly exist), ~40 new questions stratified
by query class {identifier, statute-cite, party-name, defined-term, paraphrase, cross-doc} +
hard-negative pairs; per-class recall@k + refusal-rate; scratch store only. This eval is the
[GATE] for everything else in Move 1 and for ever claiming "thousands of documents."
b) Hybrid ON with query-side term extraction (numbers, quoted strings, proper nouns → FTS arm);
candidate_k 50 + the already-built reranker; refusal-triggered second pass; near-miss passages
displayed on refusal (explicitly unverified, existing sources machinery).
c) `GET /search`: exact/boolean + "every mention" exhaustive mode (matter-pre-filtered, paginated,
truncation always labeled) — retrieval-only, zero hallucination surface.
d) Fix the production chunking gap: full SAC breadcrumbs + `document_type` (+ date) into the KB
schema; re-ingest KB store.
Verifier and matter pre-filter byte-identical throughout.

**Move 2 — Transcript engine (2-4 weeks, the product bet).**
a) Transcript-aware ingestion (.txt page/line structure + PDF gutter detection; condensed-PDF
detection with a hard warning; page:line DERIVED from verified span offsets — never model-
asserted). User marks "this is a transcript" at upload; no auto-detect.
b) Speaker-turn / Q-A-pair chunking with speaker metadata in embeddings and context labels;
unparseable regions fall back to speakerless chunks, never guessed speakers.
c) Transcript eval fixtures (synthetic 50-page depo with page:line facts, speaker-attribution
traps, Q/A-boundary questions) added to the golden set BEFORE shipping.
d) Then: deposition digest mode (map-reduce over ALL chunks, verified bullets only, Word-table
export) and cross-transcript "every mention" (rides on Move 1c).
Site transcript claims turn back on only when this ships.

**Move 3 — Trust pack v1 (parallel, small).**
Ollama pinned ≥0.17.1 + `OLLAMA_ORIGINS` allowlist; FastAPI TrustedHostMiddleware + origin/CSRF
token; pinned model SHA256 allowlist in the wizard; Time Machine/iCloud/Spotlight exclusions on
the data dir; RFC 9116 security.txt; an honest architecture/data-flow page enumerating every
residual network call; defensible-language pass on all "verified" copy (quote-fidelity framing +
"does not mean legally correct"). Site changes → owner preview.

**Move 4 — Retention as a product (the paid tier; bigger build).**
At-rest encryption (SQLCipher catalog + app-layer LanceDB) keyed per matter in Keychain/Secure
Enclave → per-matter crypto-shred → retention clocks, legal-hold object, Certificate of
Disposition (NIST 800-88r2 App. C model), export-everything (natives included), hash-chained
local audit log. One build closes the at-rest gap, the backup-leak gap, and creates the
"Provable Privacy + Retention" tier attorneys demonstrably pay for.

**Move 5 — Market motion (with owner).**
Positioning line: "every answer carries a verified pin cite you can read into the record."
Published eval-methodology page (claim ladder rungs 1-2 only). Heppner-anchored content (marketed
as architecture, not legal guarantee). Name decision (docuchat.io collision). Certs purchased →
signed builds → first release → only then platform "available" claims (already enforced by
tests). Consider an independent benchmark submission once the scale eval exists.

## 5. Explicit non-goals (scope lines the council reaffirms)

- Case-law citation checking (requires cloud legal databases; silently passing a fake case would
  be fatal — the UI must loudly partition "record cites: checked / legal authorities: verify on
  Westlaw or Lexis").
- Drafting, legal conclusions, "contradiction" verdicts (candidates only, paired verified quotes,
  advisory framing), autonomous actions of any kind.
- ANN indexing, model swaps, Tauri/Electron migration — not until measurements demand them.
- Any accuracy percentage in public copy without a published, versioned methodology.

## 6. Open decisions for the owner

1. **Adopt this roadmap order?** The council's one genuine tension: Search lead wants Move 1
   before Move 2 (retrieval quality is the foundation transcripts sit on); the buyer seat wants
   transcripts sooner (that's the cash). The sequencing above does Move 0 + Move 1a (the eval)
   first because both paths need them; 1b-1d and Move 2 can interleave.
2. **Name:** keep docuchat (and live with docuchat.io collision) or rename before launch
   marketing spends anything.
3. **Certs:** Apple Developer Program + Windows signing purchases (desktop/SIGNING.md) — the
   calendar-time critical path to a signed release.
4. **Monetization shape:** free/open core + paid trust/retention tier in the empty $20-50 slot —
   endorsed by both market reports; needs owner confirmation before any pricing page.
5. **Scanned-corpus expectations:** adopt "scans ingest overnight" as honest product language.

## 7. Source reports

Full agent reports (verbatim) are preserved in `docs/council/2026-07-07-reports/`:
scale-audit.md, transcript-audit.md, search-quality-audit.md, competitor-landscape.md,
attorney-jtbd.md, security-proof-bar.md.
