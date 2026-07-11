## Sprint 2 (2026-07-11) — E2E flow verification + honest catalog pass

The packaging bug that shipped an empty connector registry (Sprint 1,
`desktop/build_macos.spec` / `build_windows.spec`) is fixed; this pass proves
the flow works end to end for real adapters and re-checks the two adapters
the audit flagged as needing verification (Zoom, Zoho — both use a
self-serve, no-vendor-review OAuth pattern rather than a paste-a-key one, so
they were worth confirming aren't accidentally OAuth-only).

**E2E verified (real adapter code, vendor transport mocked, no network) —
`pipeline/tests/test_e2e_connector_flow.py`:** connect → import → land in
Unfiled with `source_json` provenance → `POST /kb/documents/move` re-files
into a real matter, proven for the top 3 of the audit's value ranking:

- **Gmail** (#1) — real IMAP protocol against a scripted server (FakeIMAP).
- **Zoom** (#4) — real Server-to-Server OAuth token mint + 30-day recording
  window walk + VTT download.
- **Fireflies.ai** (#7, tied with Fathom) — real GraphQL query/response shape.

All three pass. `pipeline/routes_kb.py` move route is
`POST /kb/documents/move` (`{"doc_id": int, "matter": str}`).

**Honest catalog pass: zero demotions.** All 28 `live: true` rows in
`pipeline/static/app.js` `CONNECTOR_CATALOG` have a complete adapter module
(`pipeline/connectors/*.py`) and a passing adapter-specific test
(`pipeline/tests/test_adapters_*.py`) — confirmed by re-running the full
adapter suite and by re-checking Zoom's and Zoho's vendor docs directly
(2026-07-11): Zoom Server-to-Server OAuth apps are still self-created at
marketplace.zoom.us with no Marketplace review (they're explicitly excluded
from the review requirement because they're never published); Zoho's Self
Client is still self-created at api-console.zoho.com with a user-generated
client ID/secret and short-lived grant code. Neither is disguised
interactive OAuth — both match the audit's "self-serve OAuth, feasible from
a loopback desktop app" classification, and neither needed a demotion to
Planned. (Also fixed while auditing: a stale docstring in
`pipeline/tests/test_adapters_email_files.py` claimed ShareFile was
"intentionally NOT built" — it is built, with its own passing test file;
the comment was left over from before `connectors.request` grew its
`form_body` parameter.)

**What the owner must paste — top 3 connectors:**

- **Gmail:** turn on 2-Step Verification (myaccount.google.com > Security)
  if it isn't already on, then go to myaccount.google.com/apppasswords,
  create one named "docuchat", and copy the 16-character password (shown
  once). In Gmail, create a label (e.g. "docuchat") and apply it to the
  matter emails to import. Paste: Gmail address, the app password, and that
  label name.
- **Zoom:** sign in at marketplace.zoom.us as the account owner/admin >
  Develop > Build App > Server-to-Server OAuth > Create. Add the scopes
  `cloud_recording:read:list_user_recordings:admin`,
  `cloud_recording:read:list_recording_files:admin`,
  `cloud_recording:read:meeting_transcript:admin`, `user:read:user:admin`,
  then Activate (internal app, no Zoom review). In Zoom Settings > Recording,
  turn on "Audio transcript" so future cloud recordings produce transcripts.
  Paste: Account ID, Client ID, Client Secret. Requires a paid Zoom plan
  (Pro or higher).
- **Fireflies.ai:** log in at app.fireflies.ai > Integrations > Fireflies API
  > copy the API key shown. Paste: that key. Works on every plan including
  Free (50 API requests/day — a large backfill may take a few days there).

---

# Owner action list — developer-app registrations for the Planned connectors

Every LIVE connector shipped in v0.3.0 uses a credential the user creates
themselves. The Planned tier needs a docuchat-registered developer app first.
This is the verified registration path for each (2026-07-10 research pass),
ordered by value-for-effort. None block v0.3.0.

## Fast and free (do these first)

1. **Clio Manage** — the flagship legal connector. Submit the developer-account
   intake form at developers.clio.com (reviewed), then create an app. OAuth 2.0
   only, desktop-friendly `oauth/approval` redirect, complete document
   endpoints (`/api/v4/documents.json` + `/download`). 50 req/min/token.
2. **NetDocuments** — free support ticket ("API Support" → "Request Dev Portal
   account"), then self-register an app in their Developer Portal (client
   id/secret auto-issued; pick read+lookup scopes only). Provisioning takes a
   few business days. Region-specific hosts.
3. **Microsoft (one Entra app covers Outlook, OneDrive, Word, OneNote; Teams
   transcripts and SharePoint need admin consent)** — free Entra ID app
   registration, public client + PKCE, delegated `Mail.Read` / `Files.Read` /
   `Notes.Read` are user-consentable. Do publisher verification (needs an MPN
   account) or default tenant policies will block work accounts.
4. **Read AI** — OAuth 2.1 with dynamic client registration (their API is in
   open beta; no static keys). Worth an email to their API team about a
   desktop-app flow: 10-minute access tokens with single-use rotating refresh
   tokens are hostile to a local app.
5. **Lawmatics** — email support to enable Developer Settings on our account,
   then create the OAuth app at app.lawmatics.com/settings/developers.
   Verified files endpoints.

## Costs money or heavier process

6. **Google (Drive, Docs, Gmail-API upgrade, Meet)** — free GCP project +
   OAuth client, but `drive.readonly`/`gmail.readonly` are RESTRICTED scopes:
   brand + app verification (weeks) plus an ANNUAL CASA security assessment by
   an approved lab (local-only apps are not exempt). Consider `drive.file` +
   Google Picker instead: non-restricted, no CASA, user picks the files.
   Gmail is already LIVE via IMAP app passwords without any of this.
7. **Actionstep** — credentials issued by their Global Support with a US$500
   setup fee (includes sandbox) + an API review before production.
8. **MyCase** — contact MyCase support for API access; firm must be on the
   Advanced tier; document byte-download still unverified (their docs are
   JS-gated) — confirm before building.
9. **LEAP** — open self-registration at console.leap.build, but a staged
   sandbox → pre-approval → app review pipeline with unpublished timelines.
10. **Salesforce / Litify** — our own registered app (auth code + PKCE) works
    with a customer login, but customers need API-enabled editions
    (Enterprise+, or Professional with a paid add-on) and Litify firms on
    Docrio keep file bytes outside the API. Build only with a committed
    customer.

## Explicitly parked (re-check triggers)

- **Filevine** — self-serve PATs exist, but document downloads were
  rate-limited to ZERO on 2026-01-30 "for security reasons". Flips to LIVE
  the day they restore it; re-check quarterly.
- **CARET Legal** — API launched Jan 2025 but access is contact-sales and
  phase 1 has no verified document download. Re-check in 6-12 months.
- **Evernote** — API key issuance suspended since Jan 2026 (their request
  form errors on submission). Re-check if they reopen.
- **Circleback** — no REST API, but their hosted MCP server with OAuth
  dynamic client registration has list-meetings/get-transcript tools. Becomes
  connectable if docuchat ever ships a generic remote-MCP connector.
