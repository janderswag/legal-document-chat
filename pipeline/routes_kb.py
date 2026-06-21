"""Document Hub router — upload, list, view, delete managed KB documents.

Upload is a RAW body POST (no python-multipart dependency): the file bytes are the
request body; ``matter`` (slug) and ``filename`` are query params. Files are saved under
documents/kb/<slug>/ and ingested into .lancedb_kb by a background task. DELETE is
structurally locked to documents/kb/ — it can never unlink a path outside that tree
(hard rule #5: the attorney's originals are never read or deleted).
"""

from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import FileResponse

import catalog
import kb_ingest
from embed_store import delete_doc

router = APIRouter()

PIPELINE_DIR = Path(__file__).resolve().parent
REPO_ROOT = PIPELINE_DIR.parent
KB_DB = PIPELINE_DIR / ".lancedb_kb"          # dedicated KB store (git-ignored)
KB_DOCS = REPO_ROOT / "documents" / "kb"       # managed copies (git-ignored)

_ALLOWED = {".pdf", ".docx", ".txt", ".md"}
_MAX_BYTES = 25 * 1024 * 1024  # 25 MB upload cap
_MEDIA = {".pdf": "application/pdf", ".txt": "text/plain", ".md": "text/markdown",
          ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}


def _safe_name(filename):
    """Basename only; reject separators/traversal. Returns a safe filename or None."""
    if not filename:
        return None
    name = Path(filename).name
    if name in ("", ".", "..") or "/" in filename or "\\" in filename or ".." in name:
        return None
    return name


def _within_kb(path):
    """True iff ``path`` resolves to somewhere under KB_DOCS (no escape)."""
    try:
        Path(path).resolve().relative_to(KB_DOCS.resolve())
        return True
    except (ValueError, OSError):
        return False


@router.post("/kb/upload")
async def upload(request: Request, matter: str, filename: str, background: BackgroundTasks):
    if not catalog.get_matter(matter):
        raise HTTPException(status_code=400, detail=f"unknown matter: {matter!r}")
    name = _safe_name(filename)
    if name is None:
        raise HTTPException(status_code=400, detail="invalid filename")
    if Path(name).suffix.lower() not in _ALLOWED:
        raise HTTPException(status_code=400, detail=f"unsupported type: {Path(name).suffix}")

    body = await request.body()
    if len(body) == 0:
        raise HTTPException(status_code=400, detail="empty upload")
    if len(body) > _MAX_BYTES:
        raise HTTPException(status_code=400, detail="file too large")

    dest_dir = (KB_DOCS / matter)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / name
    stem, suf, i = dest.stem, dest.suffix, 1
    while dest.exists() and dest.read_bytes() != body:  # avoid clobbering a different file
        dest = dest_dir / f"{stem}-{i}{suf}"
        i += 1
    dest.write_bytes(body)

    doc = catalog.add_document(matter, dest, filename=dest.name, status="parsing")
    background.add_task(kb_ingest.ingest_document, doc["id"], str(dest), matter,
                        str(KB_DB), catalog.DEFAULT_DB)
    return doc


@router.get("/kb/documents")
def list_docs(matter: str | None = None):
    return {"documents": catalog.list_documents(matter)}


@router.get("/kb/source/{doc_id}")
def source(doc_id: int):
    row = catalog.get_document(doc_id)
    if not row:
        raise HTTPException(status_code=404, detail="not found")
    stored = Path(row["stored_path"])
    if not _within_kb(stored) or not stored.is_file():  # path-locked to documents/kb/
        raise HTTPException(status_code=404, detail="not found")
    return FileResponse(stored, media_type=_MEDIA.get(stored.suffix.lower(), "application/octet-stream"))


@router.delete("/kb/documents/{doc_id}")
def delete(doc_id: int):
    row = catalog.get_document(doc_id)
    if not row:
        raise HTTPException(status_code=404, detail="not found")
    # 1) remove this doc's chunks from the KB store (scoped to filename + matter)
    delete_doc(KB_DB, row["filename"], row["matter_slug"])
    # 2) remove the managed copy — ONLY if it is inside documents/kb/ (structural lock)
    stored = Path(row["stored_path"])
    removed_copy = False
    if _within_kb(stored) and stored.is_file():
        stored.unlink()
        removed_copy = True
    # 3) remove the catalog row
    catalog.delete_document(doc_id)
    return {"deleted": doc_id, "removed_copy": removed_copy}
