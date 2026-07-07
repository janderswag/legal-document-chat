"""First-run setup wizard router (D-58 v1; P1.5 doer) — detect the local prerequisites
the desktop app needs (Ollama + the pinned models, plus Tesseract/disk notices) and DO
the model install in-app: POST /setup/pull streams the local Ollama's /api/pull progress
as SSE so the wizard shows a real progress bar instead of a terminal command.

Loopback-only surface: every call here talks ONLY to the local Ollama
(127.0.0.1:11434). The one download this can trigger is Ollama fetching a PINNED model
from its registry — the same setup-time download the wizard previously told the user to
run by hand; it involves no user or document data and is user-initiated. The query/
document path remains loopback-only. Only the two pinned model ids can be pulled
(allowlist — never a caller-supplied name).
"""

import json
import shutil
import urllib.request

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from pathlib import Path
from pydantic import BaseModel

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


# Approximate download sizes shown next to the in-app Download buttons (P1.5).
MODEL_SIZES_GB = {"qwen3:14b": 9.3, "bge-m3": 1.2}
# Free space to comfortably hold both models + working room.
DISK_NEEDED_GB = 15


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
    try:
        disk_free_gb = round(shutil.disk_usage(Path.home()).free / 2**30, 1)
    except OSError:
        disk_free_gb = None
    return {
        "ollama_reachable": reachable,
        "ollama_url": host,
        "models": models,
        "missing": missing,
        "model_sizes_gb": {m: MODEL_SIZES_GB.get(m) for m in PINNED_MODELS.values()},
        "pull_commands": [f"ollama pull {m}" for m in missing],
        # Advisory notices (P1.5): OCR for scanned PDFs, and room for the model downloads.
        "tesseract": shutil.which("tesseract") is not None,
        "disk_free_gb": disk_free_gb,
        "disk_needed_gb": DISK_NEEDED_GB,
        "ready": reachable and not missing,
    }


@router.get("/setup/status")
def status():
    return setup_status()


class PullRequest(BaseModel):
    model: str


@router.post("/setup/pull")
def pull_model(body: PullRequest):
    """Run the model download IN-APP (P1.5): proxy the local Ollama's /api/pull as SSE
    progress events, so the wizard shows a real progress bar with zero terminal use.
    ALLOWLISTED to the pinned models only — a caller-supplied name is never forwarded."""
    if body.model not in PINNED_MODELS.values():
        raise HTTPException(status_code=400, detail=f"unknown model: {body.model!r}")
    host = ollama_url()

    def event(name, obj):
        return f"event: {name}\ndata: {json.dumps(obj)}\n\n"

    def gen():
        req = urllib.request.Request(
            f"{host}/api/pull",
            data=json.dumps({"model": body.model, "stream": True}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req) as resp:
                for line in resp:
                    if not line.strip():
                        continue
                    obj = json.loads(line)
                    if obj.get("error"):
                        yield event("error", {"detail": obj["error"]})
                        return
                    total, done = obj.get("total"), obj.get("completed")
                    yield event("progress", {
                        "status": obj.get("status", ""),
                        "total": total, "completed": done,
                        "percent": (round(100.0 * done / total, 1)
                                    if total and done is not None else None),
                    })
                    if obj.get("status") == "success":
                        yield event("done", {"model": body.model})
                        return
            yield event("done", {"model": body.model})
        except Exception as e:  # Ollama down / network drop — surface, never crash setup
            yield event("error", {"detail": f"{type(e).__name__}: {e}"})

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.get("/setup", response_class=HTMLResponse)
def setup_page():
    """The first-run wizard page (drops into /app when ready). Local assets only."""
    return HTMLResponse((_STATIC / "setup.html").read_text(encoding="utf-8"))
