# Session close — v0.5.0 built and held (written 2026-07-11, evening)

_For the owner and the NEXT session: RUN_STATE.md's top entry is the full state.
This file is the action list._

## What is waiting on the owner (the release is NOT published)

v0.5.0 is built, signed, notarized, stapled, smoke-gated (all six steps, including
the new review-SSE assertion), golden-gated (63/63 + 9/9 + 0 rejected — identical to
baseline, engine untouched), and attached to a DRAFT GitHub release. Publish is held
per the deploy approval rule. The owner's click-through, from the council doc's
definition of done (docs/council/2026-07-11-council-review-compare-and-ingestion.md §5):

1. Install `~/projects/legal-doc-intelligence/dist/docuchat.dmg` (or the draft
   release asset — same file).
2. Review & Compare → Run review on the sample matter: skeleton instantly, rows fill
   within seconds, cancel one run, re-run, quit the app, reopen — the review is still
   there. Export it (Copy / Markdown / Word) and check the caveat line is on it.
3. Settings → Connectors: click "Choose a folder…" and confirm a REAL macOS folder
   dialog opens (this is the one surface the headless smoke cannot test — the manual
   gate item). Watch the row heartbeat ("watching · checked Ns ago").
4. Gmail on a real label (the standing real-account pass): confirm a >500-message
   label actually finishes across passes and an attachment is searchable.
5. Document Hub: "Every mention" sits at the top; /find in chat jumps to it.
6. If it all holds: publish the draft release (gh release list → edit → publish, or
   the GitHub UI). The site's download link serves releases/latest automatically.

## Standing owner items (unchanged)

- OAuth registrations (Clio, Google, Microsoft, Read AI, NetDocuments) — unlocks the
  Planned tier. docs/2026-07-10-connector-registrations.md.
- Windows build: owner said he starts AFTER this session ships. build_windows.spec
  already collects connectors; the v0.5.0 work carries over.
- Time Machine: still NO backup destination on this machine (no external drive
  found this session; an APFS local snapshot was taken as interim). Plug in a drive.

## Queued next-cycle (council §6 non-goals, reaffirmed)

- The ENGINE-GATED BATCH in one future 63/63 cycle: per-document retrieval scoping
  (the false-"missing" real fix — until then exports carry the scope caveat),
  answering.py Ollama timeouts, M-1 query rewriting, fact-router decision.
- Job runner phase 2: migrate ingest/digest onto the D-90 runner (review is tenant
  #1 and the runner is built for more).
- Matter export/import (must be a background job from day one), editable checklist
  (playbook), suggested-matter ranking chips, e-signature adapter, Slack threads,
  CRM family (cards pulled from the catalog until F6).

## Hard-won lessons this session (do not relearn)

- pywebview exposes PUBLIC attributes of the js_api object RECURSIVELY — a public
  window handle on the bridge = the entire Window API (load_url to a remote origin)
  handed to page JS. Bridge attributes stay underscore-private, and the folders_ui
  test pins it.
- /search and the citation verifier must share ONE character contract (quotes,
  entities, hyphen-breaks) or a verified span can 0-hit the exhaustive counter.
- Most connector adapters implement since= as a client-side modified-time filter;
  passing last_sync fleet-wide silently loses items that enter scope late. Allowlist
  services with verified server-side semantics (fireflies).
- The build script needs the eval repo's venv on PATH (bare `pyinstaller`), and
  `... | tail` masks its exit code — check `$?` unpiped.
- The council's per-move adversarial review went five-for-five finding real
  defects, including one critical. Keep it.
