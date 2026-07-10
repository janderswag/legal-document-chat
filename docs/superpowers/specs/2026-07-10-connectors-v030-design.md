# v0.3.0 design — Live connectors, one-click update, memory & speed research

Owner-approved 2026-07-10 (this session). Supersedes nothing; extends D-78/D-80.
New decision to record at ship time: **D-81** (see Catalog rules below).

## Goal

Every connector in the catalog must be one a user can actually connect: paste a
key/token they can self-serve, click Test, and documents flow into the Document
Hub with provenance. Anything that cannot do that is deleted from the catalog.
Plus: true in-place updates, Hub folder upload, a new landing demo, and
research-first designs for memory and speed-to-insights.

## Track 1 — Connector platform

### Catalog rules (D-81)

- **LIVE**: vendor lets an ordinary user self-serve a key/token (API key,
  personal access token, self-created app/integration token) AND the API can
  list + download documents/transcripts/notes. Gets an `Available` chip and a
  Connect drawer.
- **PLANNED**: pull path exists but requires an owner-registered OAuth app
  (Google, Microsoft, Zoom, Webex, Clio Manage). Stays in catalog, honestly
  labeled, synced-folder workaround noted. Owner gets registration steps for
  next cycle.
- **DELETE**: no user-reachable pull path (partner-gated, enterprise-sales-only,
  webhook-only). Removed entirely. The verdict comes from deep research against
  the vendor's real, current API docs — never from assumption. We would rather
  delete a connector than list one a user discovers they cannot connect.
- Paid-plan APIs stay LIVE with an honest "requires <plan>" note in the drawer.

### Framework

- `connections` table in the encrypted catalog: id, service (adapter slug),
  label, credential_encrypted (keyvault master key, AES-GCM), config_json
  (matter target, filters, sync on/off), status, last_sync, last_error, created.
  Disconnect deletes the credential row (D-80 contract).
- Adapter interface (`pipeline/connectors/` package), one module per vendor:
  - `SERVICE` metadata: slug, display name, key instructions (numbered steps a
    user follows in the vendor UI), credential fields (usually one key; some
    need key+secret or email+token), docs URL, plan requirements.
  - `test(creds) -> account label` (raises ConnectorAuthError on bad key)
  - `list_items(creds, since=None) -> [{id, name, kind, modified, meta}]`
  - `fetch_item(creds, id) -> (filename, bytes, provenance)` where provenance
    carries source service, source id, author, dates, meeting title,
    speakers/timestamps when applicable.
- Error taxonomy shared by all adapters: ConnectorAuthError, ConnectorAccessError
  (valid key, missing scope/plan), ConnectorRateLimited, ConnectorUnavailable.
  UI surfaces each with a plain-language message.
- Import engine: fetched bytes go through the EXISTING upload/ingest path into
  the Document Hub (Unfiled by default or the chosen matter), deduped by
  (service, source id) and checksum, marked imported-from-cloud; every item
  keeps provenance. Originals stored like any upload (DEK-encrypted at rest).
- Sync: one-time import default; optional scheduled sync rides the watcher poll
  loop with a per-connection interval (>= 15 min). Sync errors land in
  last_error, never crash the loop.
- Routes (GET/POST only, structural lock intact): GET /connections,
  POST /connections (create+test), POST /connections/test, POST
  /connections/import, POST /connections/sync, POST /connections/remove.
- Network posture: egress ONLY when the user connects/imports/syncs a
  connection they created, plus the existing fenced version check, plus the
  user-clicked update download. Site security copy extended to say exactly
  this. Loopback binding unchanged; the answer path still makes zero calls.
- UI: live catalog rows get `Available` + Connect. Drawer: credential fields,
  numbered "where to get your key" steps, Test connection, matter picker,
  sync toggle, Import now, Disconnect & delete key. No fake UI: a row is
  Available only when its adapter + tests exist and pass.

### Adapters (fan-out, all at once — owner call)

One agent per vendor batch reads the live API docs and produces the adapter +
key instructions + tests (mocked responses matching documented shapes) + error
mapping. Runtime gate for real users is Test connection. Suite must stay green.

### Logos

Every kept entry (LIVE and PLANNED) gets a real brand logo committed into
`pipeline/static/logos/` (SVG preferred, PNG fallback), sourced from official
brand assets / press kits / favicons at build time. No runtime fetch (air-gap).
Zero letter tiles remain in the catalog.

## Track 2 — True in-place updater

Click "Update available" → backend downloads the release DMG to a temp path →
verifies the code signature (codesign/spctl against the Developer ID) →
mounts, rename-aside swaps the app bundle, relaunches → cleans up. Any failure
leaves the running version untouched and falls back to opening the download
page. Progress shown in the nav item. Tests cover verify-fail, partial
download, swap rollback.

## Track 3 — Hub folder upload

Verify UX-9 recursive folder drop works in the Document Hub pane; add an
explicit "Add folder" button (webkitdirectory picker) so clicking a desktop
folder ingests all supported documents (strays skipped, not errored).

## Track 4 — Memory (research → design doc → owner gate)

Deep research (how a Karpathy-grade engineer would build local memory):
layered memory — existing profile/teachable notes; matter-level distilled
memory (entities, dates, timelines, key facts extracted at ingest so chat
starts knowing the case); answer-memory reuse. All local, inspectable,
fenced per product rules. NO engine change ships without the 63/63 golden gate
(D-79 never-a-blind-swap). Deliverable this cycle: design doc for owner review.

## Track 5 — Speed to insights (research + profiling)

Profile real pipeline latency (embed, retrieve, rerank, generate; p50/p90) +
deep research → ranked interventions (streaming, warm models, caches,
precomputed summaries, etc.). Quick wins that don't touch answer quality may
ship this cycle; anything touching the engine is golden-gated. Deliverable:
ranked doc + implemented safe wins.

## Track 6 — Landing demo

Replace the current hero demo asset on docuchat.app with a new short demo of
the updated app (same slot, size, style). Record from the live local app.
Owner pre-approved production push tonight (explicit, this session).

## Ship

Full suite green → DECISIONS.md D-81 + RUN_STATE update → push main → deploy
site (new demo + extended security caveat) → cut v0.3.0 signed/notarized
release per the recipe in ~/projects/legal-doc-intelligence.
