"""M2-7 — Thin FastAPI loopback HTTP surface over answer() (D-41, D-13).

A single-user, loopback-only read-only service: it retrieves + answers + verifies and
returns the result. It has NO action tools and adds NO network egress (D-2) — the only
outbound call is the loopback Ollama call already inside answer(). The bind is
127.0.0.1 only (D-4/D-25); the loopback boundary is the auth boundary for the
solo-attorney v1 (D-23, D-41 — no API auth by decision). The HTTP layer is a pass-through
of answer()'s result, so displayed citations stay chunk-derived (D-38) and mechanically
verified (D-19/M2-6); it never re-introduces a model-asserted page.
"""

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

from answering import answer
from retrieval import known_matters

HOST = "127.0.0.1"  # loopback only — never 0.0.0.0 (D-4/D-25)
PORT = 8000

PIPELINE_DIR = Path(__file__).resolve().parent
REPO_ROOT = PIPELINE_DIR.parent
# /source serves ONLY synthetic-corpus PDFs (SC-5 "open the original at the cited
# page"). Synthetic docs only; the dir is git-ignored (D-28) and absent in the M2-9
# image, so /source 404s there by design — the demo UI is a local-run surface.
CORPUS_PDF_DIR = (REPO_ROOT / "documents" / "synthetic_corpus" / "pdf").resolve()
UI_PAGE = PIPELINE_DIR / "static" / "index.html"
STATIC_DIR = (PIPELINE_DIR / "static").resolve()
APP_PAGE = STATIC_DIR / "app.html"

# Local-only asset media types (no CDN; assets are served from pipeline/static only).
_STATIC_MEDIA = {".js": "application/javascript", ".css": "text/css", ".html": "text/html",
                 ".png": "image/png", ".svg": "image/svg+xml", ".ico": "image/x-icon",
                 ".woff2": "font/woff2", ".json": "application/json"}

# Defense-in-depth (B2): no interactive docs AND no schema endpoint (openapi_url=None) —
# the loopback single-tenant API exposes no introspection surface.
app = FastAPI(title="Legal Document Intelligence (M2-7)", docs_url=None, redoc_url=None,
              openapi_url=None)

# App routers (the SAM-style UI surfaces). Loopback-only, cited-retrieval only.
import routes_chat  # noqa: E402
import routes_clauses  # noqa: E402
import routes_grid  # noqa: E402
import routes_kb  # noqa: E402
import routes_matters  # noqa: E402
import routes_settings  # noqa: E402
import routes_setup  # noqa: E402

app.include_router(routes_matters.router)
app.include_router(routes_kb.router)
app.include_router(routes_chat.router)
app.include_router(routes_clauses.router)
app.include_router(routes_grid.router)
app.include_router(routes_settings.router)
app.include_router(routes_setup.router)


@app.get("/", response_class=HTMLResponse)
def index():
    """Thin read-only demo page (SC-5). Static HTML; all data flows via /answer +
    /source. No document data is embedded in the page itself."""
    return HTMLResponse(UI_PAGE.read_text(encoding="utf-8"))


@app.get("/app", response_class=HTMLResponse)
def app_shell():
    """The SAM-style local app shell (left nav + views). Local assets only."""
    return HTMLResponse(APP_PAGE.read_text(encoding="utf-8"))


def _safe_static(asset: str):
    """Resolve ``asset`` to a real file INSIDE pipeline/static/, or None. Rejects any
    traversal/separator escape so /static never serves outside the static dir."""
    if asset.startswith("/") or "\\" in asset or ".." in asset.split("/"):
        return None
    target = (STATIC_DIR / asset).resolve()
    try:
        target.relative_to(STATIC_DIR)
    except ValueError:
        return None
    return target if target.is_file() else None


@app.get("/static/{asset:path}")
def static_asset(asset: str):
    """Serve a LOCAL static asset (CSS/JS/img), path-locked to pipeline/static/."""
    target = _safe_static(asset)
    if target is None:
        raise HTTPException(status_code=404, detail="not found")
    return FileResponse(target, media_type=_STATIC_MEDIA.get(target.suffix, "application/octet-stream"))


@app.get("/eval/matters")
def eval_matters():
    """The EVAL store's matter allowlist (read-only) — used by the SC-5 demo page (/).
    The app's own matters catalog is served at /matters by routes_matters."""
    return {"matters": known_matters()}


def _safe_corpus_pdf(filename: str):
    """Resolve ``filename`` to a real PDF INSIDE the synthetic-corpus dir, or None.
    PATH-LOCKED: reject any separator / traversal, require a .pdf, and require the
    resolved path to be a direct child file of CORPUS_PDF_DIR (no symlink escape)."""
    if "/" in filename or "\\" in filename or ".." in filename:
        return None
    if not filename.endswith(".pdf"):
        return None
    target = (CORPUS_PDF_DIR / filename).resolve()
    if target.parent != CORPUS_PDF_DIR or not target.is_file():
        return None
    return target


@app.get("/source/{filename:path}")
def source(filename: str):
    """Serve a synthetic-corpus PDF so a citation can open the original at the cited
    page (`/source/<file>#page=N`, SC-5). Path-locked to documents/synthetic_corpus/pdf
    (synthetic only, loopback only); anything outside that dir → 404. Read-only."""
    target = _safe_corpus_pdf(filename)
    if target is None:
        raise HTTPException(status_code=404, detail="not found")
    return FileResponse(target, media_type="application/pdf")


class AnswerRequest(BaseModel):
    question: str
    matter: str | None = None  # None = explicit search-all (D-35)


@app.get("/health")
def health():
    """Liveness only — no document data."""
    return {"status": "ok"}


@app.post("/answer")
def post_answer(req: AnswerRequest):
    """Retrieve + answer + verify, returning answer()'s result verbatim. matter is
    validated against the store allowlist inside retrieve() (D-35); an unknown matter
    is a 400 (never interpolated raw into a filter)."""
    try:
        return answer(req.question, matter=req.matter)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


def run():
    """Serve on loopback only (D-4). Used by the M2-7 smoke run; not auto-invoked."""
    import uvicorn
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")


if __name__ == "__main__":
    run()
