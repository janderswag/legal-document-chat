# docuchat.app — What You Must PROVE, Not Claim (security/retention/output-quality proof bar)

_Agent report, 2026-07-07, verbatim (formatting lightly adjusted). Graded as a big-firm security
reviewer + malpractice insurer would. Repo ground-truthed; three research-stage errors corrected
in verify pass (Harvey ISO 42001 = Jun 2026; Virginia LEO 1901 court-approved Nov 24, 2025;
CVE-2026-27940 is an OOB write)._

**Bottom line up front.** The architecture (local-only, loopback, no telemetry, mechanically
verified citations) is a genuinely strong starting posture — but three load-bearing claims are
currently unproven or weaker than the marketing implies:

1. **"Privilege-safe by architecture"** is undercut by an unauthenticated, auto-started Ollama
   with the worst CVE record in the stack and a FastAPI layer with no Host/CSRF defense — both
   reachable from a website the attorney visits. Loopback is not a security boundary.
2. **"Your documents never leave the machine"** is true for the query path, but client text sits
   in plaintext at rest (LanceDB OSS + SQLite, neither encrypted) and can be silently copied
   off-device by Time Machine/iCloud/Spotlight — no exclusions set.
3. **"Mechanically verified citations"** is defensible ONLY in its narrow honest sense (the quote
   string-matches the source). If marketing lets a reader hear "verified = legally correct," you
   are standing where LexisNexis's "hallucination-free" claim got dismantled and where the FTC
   treats it as a substantiation violation.

## 1. The Proof Bar (what firms, regulators, insurers require in 2026)

- **ABA Formal Op. 512 (Jul 29, 2024):** informed consent required before inputting client info
  into a self-learning GAI tool; boilerplate insufficient. **A local, non-self-learning tool
  sidesteps the consent trigger entirely — docuchat's single best compliance argument** — but you
  must be able to prove the model does not learn/persist across matters. Op. 512 also imposes a
  vendor-terms diligence duty: your Terms and a plain-language data-flow statement are compliance
  artifacts buyers are ethically required to read.
- **25+ jurisdictions** have issued opinions (Bloomberg Law comparison table; Justia 50-state
  survey). Recurring commands: (a) don't put confidential data in a tool without adequate
  protection/consent; (b) independently verify every citation. Key cites: CA COPRAC Nov 2023;
  FL 24-1; NYC 2024-5; NJ Jan 2024; PA/Phila 2024-200; KY E-457; TX 705 (Feb 2025 — Rule 1.05
  triggered by privileged mental impressions in prompts); **VA LEO 1901 approved by SCV Nov 24,
  2025**; DC 388; NC 2024 FEO 1; OR 2025-205 (firm AI policies mandatory for managers); MN Sept
  2024. Build a "How docuchat maps to your state's rules" page.
- **Rule 1.1 Comment 8** (tech competence): 40 states + DC + PR (Ambrogi tracker; PR standalone
  Rule 1.19 effective Jan 1, 2026).
- **OCGs:** ACC/Everlaw 2025 (657 in-house pros): only 24% satisfied with outside-counsel GenAI
  adoption; 59% don't know whether firms use GenAI on their matters. The OCG "return or destroy
  at end of matter, with written certification" clause is boilerplate (Fox Rothschild; Law
  Insider) — **the market pull for retention tooling.** No credible public stat exists for "% of
  OCGs with an AI clause" — don't cite one.
- **Cyber insurance:** MFA everywhere, EDR, encrypted immutable tested backups, <30-day critical
  patching, documented IR plan (Uptime Legal; Dataprise 2026). Coalition's Affirmative AI
  Endorsement (2024-25); market splitting into affirmative-AI vs AI exclusions (Fenwick). **No
  major US LPL carrier has attached an AI-specific exclusion to its lawyers' PL form** (Legal AI
  Governance tracker, May 2026), but coverage for AI mistakes is "uncertain" (ABA Journal 2025).
  Lawyers Mutual NC's AI policy template recommends AI use logs + human-review checklists — ship
  the audit log the carrier's template wants.
- **SOC 2 for local-first:** the classic auditor position is that installed software has no basis
  for a SOC report — but buyers still ask; scope SOC 2 to the vendor org (build/release pipeline,
  update servers, signing keys). Cooley publishes vendor requirements (SOC 2 Type 2/ISO 27001,
  annual pen tests, 30-day critical remediation, 24-hour breach notice, right to audit) and will
  apply them to software inside its walls. **ISO 42001 is the emerging differentiator** (Harvey
  certified Jun 2026; Thomson Reuters; K&L Gates; Willkie).
- **FTC:** retention/training promises are substantiable advertising (Jan/Feb 2024 posts);
  Operation AI Comply — DoNotPay $193K + prohibition on lawyer-equivalence claims (final order
  Feb 2025). "No telemetry / nothing leaves the machine" must be literally true across the whole
  stack (license check, update ping, model download), reflected in the ToS, never quietly
  changed.

## 2. Local-First Attack Surface — top 5 gaps a hostile reviewer will flag

Genuinely favorable and to be stated plainly: default 127.0.0.1 binding (confirmed in
`launcher.py`/`api.py`), GGUF (not pickle) models, no telemetry.

**GAP 1 — Auto-started Ollama is an unauthenticated always-on local API; FastAPI has no
Host/CSRF defense. Loopback != boundary.** Ollama has no built-in API auth (current FAQ). CVE
record: CVE-2024-37032 "Probllama" path-traversal RCE; CVE-2024-28224 DNS rebinding exfiltrates
data despite loopback binding (NCC Group); **CVE-2026-7482 "Bleeding Llama" — unauthenticated
heap OOB read, CVSS 9.1, leaks env/keys/concurrent conversation data, fixed v0.17.1 (May 2026)**.
The "0.0.0.0-day" class reached localhost services from public websites for 18 years on macOS
(Oligo, Aug 2024). ~175,000 exposed Ollama servers (THN, Jan 2026); LeakIX Feb 2026: "12,000
Ollama Instances Exposed: When 'Local-First' Meets the Real World" — a reviewer will quote that
title. Repo status: loopback-forced Ollama, never touches a user's own — good; **no
`OLLAMA_ORIGINS` override (default CORS allows `0.0.0.0`); no TrustedHostMiddleware, no CORS
allowlist, no CSRF/origin token in `pipeline/api.py`** — every state-changing endpoint is a
DNS-rebinding/CSRF target from any page the attorney browses. Mitigation: pin Ollama >=0.17.1
with a signed update channel; `OLLAMA_ORIGINS` app-only allowlist; TrustedHostMiddleware +
per-session origin/CSRF token; SBOM version tracking.

**GAP 2 — Client documents in plaintext at rest; FileVault's guarantee is narrow.** LanceDB OSS
has no at-rest encryption (Enterprise-only feature); SQLite catalog is plaintext (SQLCipher
exists). FileVault protects the powered-off/stolen-disk case only; once unlocked, data is
readable, and it does not isolate one local admin from another. Mitigation: SQLCipher +
app/FS-layer LanceDB encryption, key in Secure-Enclave-backed Keychain with app+user-scoped ACL.
**This one build also neutralizes Gap 4 and, via crypto-shred, delivers provable deletion (§4).**

**GAP 3 — Model supply chain.** Ollama's registry is content-addressable (integrity, not
authenticity); no publisher signing. GGUF parser is an active RCE surface: CVE-2025-49847;
CVE-2024-34359 (Jinja2 SSTI RCE); **CVE-2026-27940 heap OOB write** (bypass of the incomplete
CVE-2025-53630 fix). Precedent: malicious Hugging Face model hit 244,000 downloads (CSO).
Mitigation: curated pinned model allowlist by SHA256 (the wizard already installs specific models
— pin them); keep llama.cpp/Ollama patched; model provenance in SBOM.

**GAP 4 — Silent off-device leakage via Time Machine, iCloud, Spotlight.** Defaults copy
~/Documents and much of ~/Library off-device; Spotlight indexes content. Repo status: no
exclusions anywhere. Mitigation: store client data outside iCloud paths; `tmutil addexclusion`,
`NSURLIsExcludedFromBackupKey`, `.noindex` as installer steps. (App-layer encryption renders the
copies useless anyway.)

**GAP 5 — Process memory & multi-user exposure.** Model process holds plaintext in RAM
(CVE-2026-7482 proves heap leaks conversation data); core dumps can capture memory
(CVE-2025-24204 until macOS 15.3). Mitigation: Hardened Runtime + notarization; disable core
dumps for the model process; per-user app-level encryption keys.

**Proof artifacts:** Developer ID signing + notarization + Hardened Runtime (pipeline ready in
`desktop/`, **certs unpurchased**); Keychain/Secure Enclave key custody (not implemented); signed
auto-updates — Sparkle EdDSA (launcher currently says "no auto-update"; **for a stack whose
dependencies get critical CVEs quarterly, no update channel is itself a finding**); SBOM
(CycloneDX — none emitted); reproducible builds (aspirational).

## 3. Output-Quality Assurance as a Trust Feature

- **Stanford RegLab** ("Hallucination-Free?", peer-reviewed JELS 2025): Lexis+ AI >17%, Westlaw
  AIAR >34%. The load-bearing concept: hallucination = (a) incorrect OR **(b) misgrounded**
  (correct statement, cited source doesn't support it) — misgrounded is the most dangerous mode.
- **How "verified" burns vendors:** LexisNexis marketed "100% hallucination-free linked legal
  citations," was publicly rebutted ("a tool that cited only Brown v. Board for every query would
  be hallucination-free" under that definition) and **walked it back** (LLRX Apr 2026). Casetext
  claimed "does not make up facts" with no published evidence.
- **The regulatory trap for a number:** FTC v. Workado (final order Aug 2025) — "98% accurate"
  tested at ~53%; numeric accuracy claims are efficacy claims requiring substantiation at the
  time made + evidence retention. Texas AG v. Pieces (Sept 2024): a hallucination-rate claim
  without published methodology was itself the alleged violation.
- **Sanctions backdrop:** Mata v. Avianca ($5K, 2023) through Lacey v. State Farm (~$31K —
  lawyers used CoCounsel + Westlaw Precision + Gemini) and Johnson v. Dunn (disqualification;
  fines "ineffective"); ~1,725 tracked cases by mid-2026; 17 US decisions noting suspected AI
  hallucinations on a single day (Mar 31, 2026, Volokh).

**The defensible claim ladder** (docuchat sits legitimately at rungs 1-2; market there ONLY):
1. **Quote fidelity** — quoted passage string-matches the source (fully machine-checkable; what
   docuchat does).
2. **Link/existence** — citation resolves to a real document in the corpus.
3. **Support/groundedness** — cited passage supports the proposition — report as a measured rate
   with error bars, never a guarantee.
4. **Legal correctness / good law / completeness** — NOT mechanically verifiable. Never claim.

**Say:** "Verified means the quoted text appears, character-for-character, in the cited document.
It does not mean the proposition is legally correct, current, or complete — verify legal
conclusions yourself." / versioned eval with N, methodology, error taxonomy, and abstention rate
reported separately ("declined on Z% of eval queries").
**Never say:** "hallucination-free," "100% verified," "does not hallucinate," lawyer-equivalence,
a bare accuracy % without published method, "eliminates the need to verify."

**A published eval page must contain:** dataset + provenance, sample size, question-type
taxonomy, explicit error taxonomy (incorrect vs misgrounded vs unsupported), human-review
protocol, abstention rate separately, product version + eval date, retained evidence (a literal
FTC order term). Watch: Vals VLAIR (Lexis and Westlaw declined to participate — a fact worth
knowing).

## 4. Retention as a FEATURE

Duties creating demand: Rule 1.16(d) (surrender client file on termination); Rule 1.15(a) (5-year
records, 6 in MA/SC); entire-file vs end-product doctrine (most states entire-file; ABA Op. 471
minority; Idaho codified entire-file 2025); bar-recommended retention 5-10 years, wills/deeds
indefinitely; **NC Proposed 2026 FEO 3 addresses native-format handover — export-everything must
include natives, not just PDFs**; FRCP 37(e) litigation holds — a hold must suspend all scheduled
deletion per matter and be logged (how legal DMS behave — NetDocuments).

Technically credible "provable deletion": **NIST SP 800-88 Rev. 2 (FINAL Sept 26, 2025)** — plain
deletion/overwriting is explicitly insufficient on SSD/flash; **Cryptographic Erase is a Purge
technique**; Appendix C provides a Certificate of Sanitization (model the "Certificate of
Disposition" on it). macOS local snapshots make plain deletion non-provable (deleted files
persist in snapshots ~24h). **The credible design: per-matter crypto-shredding** — envelope-
encrypt each matter with its own DEK, destroy the DEK at disposition (same at-rest build as Gap
2). Certificates of destruction are established practice (NAID AAA). Audit logs: hash-chained
append-only (RFC 6962 construction) makes tampering cryptographically detectable — a solo can
answer a client security audit with no server.

**Feature set attorneys would pay for (matter is the unit):** matter-scoped retention clocks
(default 6-10y post-close; indefinite flags for wills/minors); legal hold as a first-class object
that freezes disposition and logs itself; per-matter crypto-shred; signed Certificate of
Disposition; export-everything (PDFs + natives) before delete (Rule 1.16(d) surrender);
hash-chained local audit log. Revealed preference: iManage Records Manager and NetDocuments sell
retention/disposition as separately licensed governance modules. **Repo status: per-matter delete
exists (`pipeline/kb_maintenance.py`) but is a plain unlink — no crypto-shred, no hold object, no
certificate, no audit log, no native-inclusive export. The biggest greenfield in the product.**

## 5. Trust-Page Checklist — 10 items, graded against the real repo

| # | Item | Status |
|---|---|---|
| 1 | Architecture white paper + honest data-flow diagram enumerating every residual network call (1Password model) | needs-work (architecture real; document doesn't exist) |
| 2 | Loopback + no-telemetry posture, precisely scoped (query path vs one-time model download) | **already-true — just publish it** |
| 3 | At-rest encryption (SQLCipher + LanceDB app-layer), Keychain/Secure-Enclave key | needs-build (highest-value security build; unlocks #8) |
| 4 | Signed + notarized builds, Hardened Runtime, signed auto-update channel | needs-work (pipeline ready, certs unpurchased) + needs-build (no auto-update) |
| 5 | Ollama hardening: pinned >=0.17.1, OLLAMA_ORIGINS allowlist, FastAPI TrustedHost + CSRF token | needs-build |
| 6 | Curated model allowlist by SHA256 + SBOM (CycloneDX) | needs-work (pin the wizard's models) + needs-build (SBOM) |
| 7 | Published eval/methodology page (defines "verified"; states what it does NOT verify; N, error taxonomy, abstention, version) | needs-work (mechanism exists; disclosure doesn't) |
| 8 | Matter-based retention tooling: clocks, hold object, crypto-shred, Certificate of Disposition, export-everything, hash-chained audit log | needs-build |
| 9 | Third-party pen test + public attestation, VDP + RFC 9116 security.txt | needs-build (cheapest way to convert "trust us" into "verify us") |
| 10 | Ethics/compliance mapping page + org-scoped SOC 2 / ISO 42001 roadmap + pre-answered SIG Lite/CAIQ/HECVAT | needs-work + needs-build |

**Fastest credibility gains, in order:** (2) publish what's already true; (5)+(6-allowlist) small
code changes neutralizing the worst finding; (3)+(8) one shared crypto build closing at-rest,
backup-leak, and provable-deletion while creating a paid feature; (9) security.txt + one
named-firm audit of a source-available client.
