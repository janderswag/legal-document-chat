# Next-session prompt — encryption cycle + loose ends (prepared 2026-07-07)

Paste the block below into a fresh Fable session.

---

You are Fable 5 running a focused session on docuchat (repo legal-document-chat), the
local-first, privilege-safe document chat for attorneys. Canonical working copy:
/Users/janderswag/projects/legal-doc-intelligence. FIRST STEP: `git fetch`, confirm
origin/main HEAD, read RUN_STATE.md and DECISIONS.md D-66 through D-72, then the two
design docs named below. Jake runs parallel agents; inspect any uncommitted work before
touching shared files.

STATE YOU INHERIT (do not re-derive; verify in passing):
- The full council roadmap Moves 0-5 is EXECUTED (D-68..D-72). Standing golden gate:
  63/63, 0 fabrications ("run-2026-07-07-m1-secondpass" is the baseline). Scale eval is
  a standing gate: pipeline/build_scale_store.py + run_scale_eval.py + eval/SCALE_EVAL.md.
  359 tests green via `pipeline/.venv/bin/python -m unittest discover -s tests`.
- Retrieval config is MEASURED, not assumed: dense top-5 default; hybrid and reranker
  OFF (both measured harmful post-1d); refusal-triggered anchor-fed second pass in
  answering.py. Do not change retrieval defaults without re-running BOTH evals.
- Transcript engine (D-70), trust pack (D-71), retention primitives (D-72) are live.
- The `site-preview` BRANCH (pushed) holds ALL pending customer-facing site changes
  (transcript claims, security.html + .well-known/security.txt, verification.html,
  pin-cite lede). If the owner has approved: merge site-preview into main and push
  (that deploys Pages). If not approved yet: serve site/ from a site-preview worktree
  at 127.0.0.1:8090 and ask. NEVER commit site changes on main directly.

PRIMARY OBJECTIVE — the encryption cycle (Move 4's deferred half), per the design doc
docs/2026-07-07-retention-encryption-design.md §3-4, which is authoritative:
1. Prototype FIRST, measured: encrypted APFS sparse-bundle volume hosting the LanceDB
   store; measure mount latency + first-query overhead (budget < 500ms) and Time
   Machine interaction before committing to per-matter vs single-volume granularity.
2. Master key in the macOS Keychain (Secure-Enclave-backed where available); per-matter
   DEKs wrapped by it (AES-256-GCM envelope). Never a key in a file or in git.
3. SQLCipher migration for the catalog, using the reingest_kb.py rename-aside pattern;
   REHEARSE the migration on a copy and write a data-loss drill before touching the
   real store.
4. Crypto-shred: destroying a matter's DEK upgrades retention.py's certificate method
   from "Clear" to "Purge (cryptographic erase, NIST SP 800-88r2)" — change that string
   ONLY when the shred is real and tested.
5. [GATE] full golden + scale evals after the storage swap; update security.html's
   honest-status block (site-preview branch) only after everything ships.
If the prototype misses the latency budget or integrity risk appears, STOP, write up
the measurement, and propose alternatives rather than forcing it.

SECONDARY (only if the owner says the inputs exist):
- Certs purchased -> BUNDLE_OLLAMA=1 ./desktop/build_macos.sh per desktop/SIGNING.md,
  first release, then (owner preview) flip the site download cards.
- Owner approval of site-preview -> merge + push.

NON-NEGOTIABLES (unchanged): verifier.py and matter isolation byte-identical; loopback
only; no telemetry; [GATE] discipline with numbered DECISIONS entries (next: D-73);
"verified" = quote fidelity + existence, never legal correctness; no em-dashes in
user-facing copy; product stays free; name stays docuchat; site work on site-preview
only; smallest correct change; full suite before every commit; honest reporting; queue
owner-only actions instead of attempting them.

DELIVERABLES: working gated code committed per unit; DECISIONS + RUN_STATE updated;
a final report of shipped vs deferred with every acceptance result.
