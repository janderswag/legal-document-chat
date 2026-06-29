# PROGRESS.md — Desktop packaging v1 (D-58, locked scope)

> Packaging effort, not pipeline code: wrap, don't rewrite. The Python pipeline + the
> mechanical citation verifier stay UNTOUCHED (no edits to verifier.py/answering.py/
> retrieval.py/etc.; new files + additive router mounts only). Runtime loopback-only, no
> telemetry, no auto-update. Approved install: **pywebview** (+ minimal launcher deps,
> named). Anything else = [GATE]. Deferred (Phase B, do NOT build): PyInstaller-frozen
> bundle, Windows build, code-signing/notarization. Do NOT commit (Planner commits).

## Setup
- [x] **S0** installed `pywebview==6.2.1` (+ macOS deps pyobjc-*, bottle, proxy_tools — pywebview's own). api imports clean; pipeline untouched.

## Deliverable 2 — In-app first-run wizard
- [x] **W1** `routes_setup.py` `/setup/status` — probes local Ollama `/api/tags`, checks pinned models; `{ollama_reachable, models, missing, pull_commands, ready}`. `_ollama_tags` monkeypatchable. Loopback-only. _routes_setup.py_
- [x] **W2** `/setup` wizard page — ready → auto-redirect to `/app`; else guided steps with exact `ollama pull` cmds + Get-Ollama link + copy buttons + Re-check. esc() XSS, local assets only. _static/setup.{html,js,css}_
- [x] **W3** tests: model-match, ready / model-missing / not-reachable(simulated), page served, no external assets; route allowlist updated. 7 tests + live status (ready=true). _test_setup.py, api.py, test_api.py_

## Deliverable 3 — macOS launcher (pywebview)
- [x] **L1** `desktop/launcher.py` — free_port(8000) pre-kill, start FastAPI child (handle held), wait_healthy, pywebview window at `/setup`, stop_server on quit (TERM→KILL). webview import deferred. _desktop/launcher.py, requirements.txt, README.md_
- [x] **L2** tests: unused-port free; start→health→stop releases port; free_port kills a stale listener. 3 tests green (headless). _test_launcher.py_

## Deliverable 1 — Landing page (frontend-design skill)
- [x] **P1** `site/` static — editorial-legal design (Fraunces/Newsreader/IBM Plex Mono, ivory paper, oxblood wax seal). 3 downloads, "Download for macOS" CTA→Releases + "Windows — coming soon", privacy framing, framed demo placeholder. _site/index.html, styles.css, script.js, favicon.svg_
- [x] **P2** served locally (http://127.0.0.1:4173) — 200, renders (browser-verified hero/steps/download). Pages wired via `workflow_dispatch`-only workflow + `.nojekyll` (never auto-deploys). 7 guard tests. _site/README.md, .github/workflows/deploy-site.yml, test_site.py_

## FINAL — all v1 pieces [x]; pipeline untouched; Phase-B deferred
- [x] **Suite 257/257 OK** (was 240; +17: setup 7, launcher 3, site 7). Pipeline/verifier logic UNCHANGED — diff touches only `api.py` (additive router mount), `test_api.py` (route allowlist), `PROGRESS.md`; everything else is NEW files.
- [x] **Baselines byte-identical** (canon fold from pipeline/): `.lancedb=13b242de`, `.lancedb_full=0df0525c`, `.lancedb_hyb=51e13b31`.
- [x] **Only pywebview installed** (6.2.1 + its macOS deps). No PyInstaller, no signing, no Windows build, no non-loopback bind — all correctly deferred to Phase B.
- [x] Loopback-only preserved (server 127.0.0.1; wizard probes loopback Ollama; landing page is the public marketing page, intentionally separate). No telemetry, no auto-update.
- Not committed (Planner commits at record).

### Local commands to test all three
```bash
# 1. Landing page
cd ~/projects/legal-doc-intelligence/site && python3 -m http.server 4173   # → http://127.0.0.1:4173
# 2. Launcher (opens the app in a native window; wizard first, then /app)
pipeline/.venv/bin/pip install -r desktop/requirements.txt
pipeline/.venv/bin/python desktop/launcher.py
# 3. Wizard alone (server already running): http://127.0.0.1:8000/setup
```
