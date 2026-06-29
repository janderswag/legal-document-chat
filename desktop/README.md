# Desktop launcher (Phase A) — Legal Document Chat in a window

D-58 v1, Phase A: a thin **pywebview** launcher around the existing FastAPI app. It opens
the app in a native macOS window instead of a terminal — no PyInstaller bundle, no signing
(those are Phase B). It **wraps** the pipeline; it changes no pipeline/verifier code.

## What it does
1. Pre-kills anything stuck on port 8000 (so a stale server can't block launch).
2. Starts the FastAPI server as a child process (`uvicorn api:app`, bound `127.0.0.1`).
3. Health-checks `http://127.0.0.1:8000/health`.
4. Opens the first-run wizard (`/setup`) in a window; the wizard drops into `/app` once
   Ollama + the pinned models are present.
5. Kills the child server when you close the window (no orphaned process).

Loopback-only, no telemetry, no auto-update.

## Run it (this Mac)
```bash
cd ~/projects/legal-doc-intelligence
pipeline/.venv/bin/pip install -r desktop/requirements.txt   # one-time (pywebview)
pipeline/.venv/bin/python desktop/launcher.py
```
A window titled "Legal Document Chat" opens. If Ollama or a model is missing, the wizard
guides you (with the exact `ollama pull` commands); otherwise it goes straight to the app.

## Prerequisites (Phase A still needs these — Phase B bundles them)
- **Ollama** running on `127.0.0.1:11434`.
- Models: `ollama pull qwen3:14b` and `ollama pull bge-m3` (the wizard checks + prompts).

## Deferred to Phase B (NOT in v1)
PyInstaller-frozen self-contained bundle; bundled inference engine + in-app model download;
Windows build; code-signing/notarization.
