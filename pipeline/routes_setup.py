"""First-run setup wizard router (D-58 v1) — detect the local prerequisites the desktop
app needs (Ollama + the pinned models) and guide the user if anything is missing.

Read-only + loopback-only: it probes the SAME local Ollama the pipeline uses
(127.0.0.1:11434) via /api/tags and reports readiness. No telemetry, no external calls, no
mutation — it never installs or pulls anything itself; it shows the user the exact commands.
The wizard page drops straight into /app when everything is present.
"""

import json
import urllib.request

from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from pathlib import Path

from embed_store import ollama_url

router = APIRouter()

# D-11 pinned models the app requires (frozen).
PINNED_MODELS = {"chat": "qwen3:14b", "embed": "bge-m3"}
_STATIC = Path(__file__).resolve().parent / "static"


def _ollama_tags(host=None, timeout=2.0):
    """Model names installed in the local Ollama (via /api/tags). Raises on unreachable —
    callers treat any error as 'Ollama not running'. Loopback host by default."""
    host = host or ollama_url()
    req = urllib.request.Request(f"{host}/api/tags")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.load(resp)
    return [m.get("name", "") for m in data.get("models", [])]


def _model_present(pinned, tags):
    """True if a pinned model id is satisfied by one of Ollama's tag names. Matches an
    exact id, an explicit ``:latest``, and (for a bare name like ``bge-m3``) the base."""
    base = pinned.split(":")[0]
    for t in tags:
        if t == pinned or t == pinned + ":latest":
            return True
        if ":" not in pinned and (t == base or t.startswith(base + ":")):
            return True
    return False


def setup_status():
    """Readiness of the local prerequisites for the desktop app."""
    host = ollama_url()
    try:
        tags = _ollama_tags(host)
        reachable = True
    except Exception:
        tags, reachable = [], False

    models = {m: (reachable and _model_present(m, tags)) for m in PINNED_MODELS.values()}
    missing = [m for m, ok in models.items() if not ok]
    return {
        "ollama_reachable": reachable,
        "ollama_url": host,
        "models": models,
        "missing": missing,
        "pull_commands": [f"ollama pull {m}" for m in missing],
        "ready": reachable and not missing,
    }


@router.get("/setup/status")
def status():
    return setup_status()


@router.get("/setup", response_class=HTMLResponse)
def setup_page():
    """The first-run wizard page (drops into /app when ready). Local assets only."""
    return HTMLResponse((_STATIC / "setup.html").read_text(encoding="utf-8"))
