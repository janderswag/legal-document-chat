"""Document Hub router — upload, list, view, delete managed KB documents.

Upload is a RAW body POST (no python-multipart dependency): the file bytes are the
request body; ``matter`` (slug) and ``filename`` are query params. Files are saved under
documents/kb/<slug>/ and ingested into .lancedb_kb by a background task. DELETE is
structurally locked to documents/kb/ — it can never unlink a path outside that tree
(hard rule #5: the attorney's originals are never read or deleted).
"""

import hashlib
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

import catalog
import ingest_worker
import keyvault
import pdf_view
from embed_store import delete_doc

router = APIRouter()

import apppaths
KB_DB = apppaths.data_root() / ".lancedb_kb"   # dedicated KB store (git-ignored)
KB_DOCS = apppaths.docs_root()                 # managed copies (git-ignored)

_ALLOWED = {".pdf", ".docx", ".txt", ".md", ".eml"}
_MAX_BYTES = 25 * 1024 * 1024  # 25 MB upload cap
_MEDIA = {".pdf": "application/pdf", ".txt": "text/plain", ".md": "text/markdown",
          ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
          ".eml": "message/rfc822"}


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
async def upload(request: Request, matter: str, filename: str, doc_type: str = "document"):
    if doc_type not in ("document", "transcript"):
        raise HTTPException(status_code=400, detail=f"unknown doc_type: {doc_type!r}")
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
    # dedup compares PLAINTEXT (read_matter_file decrypts D-73 natives transparently)
    while dest.exists() and keyvault.read_matter_file(dest, matter) != body:
        dest = dest_dir / f"{stem}-{i}{suf}"
        i += 1
    # D-73: written DEK-encrypted when the encryption cycle is active on this
    # install, plain otherwise; catalog rows always carry the PLAINTEXT hash/size.
    keyvault.write_matter_file(dest, body, matter)

    # Move 0b (D-68): enqueue to the single serialized ingest worker — uploads return
    # instantly and NEVER occupy the request thread pool (a bulk upload previously ran
    # up to 40 concurrent sync ingests there, starving /chat for hours).
    doc = catalog.add_document(matter, dest, filename=dest.name, status="queued",
                               doc_type=doc_type,
                               checksum=hashlib.sha256(body).hexdigest(),
                               size_bytes=len(body))
    ingest_worker.enqueue(doc["id"], str(dest), matter, str(KB_DB), catalog.DEFAULT_DB)
    return doc


class MoveRequest(BaseModel):
    doc_id: int
    matter: str


@router.post("/kb/documents/move")
def move_document(body: MoveRequest):
    """UX-7 Document Hub filing: re-file a document into another matter. The managed
    copy is decrypted with the source matter's key and re-encrypted under the
    destination's (D-73 per-matter DEKs); old chunks are removed and the document is
    re-ingested under the new scope. Blocked while the SOURCE matter is under an
    active legal hold (moving out of a held matter would defeat preservation).
    POST, not PUT/PATCH (structural lock)."""
    row = catalog.get_document(body.doc_id)
    if not row:
        raise HTTPException(status_code=404, detail="not found")
    if not catalog.get_matter(body.matter):
        raise HTTPException(status_code=400, detail=f"unknown matter: {body.matter!r}")
    old_matter = row["matter_slug"]
    if body.matter == old_matter:
        return {"moved": body.doc_id, "matter": old_matter, "unchanged": True}
    hold = catalog.active_hold(old_matter)
    if hold:
        raise HTTPException(status_code=409,
                            detail=f"legal hold active on {old_matter!r} since "
                                   f"{hold['created']}: {hold['reason']}")

    stored = Path(row["stored_path"])
    if not _within_kb(stored) or not stored.is_file():
        raise HTTPException(status_code=409, detail="managed copy missing")
    plain = keyvault.read_matter_file(stored, old_matter)

    dest_dir = KB_DOCS / body.matter
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / row["filename"]
    stem, suf, i = dest.stem, dest.suffix, 1
    while dest.exists() and keyvault.read_matter_file(dest, body.matter) != plain:
        dest = dest_dir / f"{stem}-{i}{suf}"
        i += 1
    keyvault.write_matter_file(dest, plain, body.matter)

    delete_doc(KB_DB, row["filename"], old_matter)      # old-scope chunks out
    catalog.move_document_row(body.doc_id, body.matter, dest.name, dest)
    stored.unlink(missing_ok=True)                       # managed copy only, in-KB
    catalog.audit_append("document_moved", matter_slug=body.matter,
                         detail=f"doc {body.doc_id} ({dest.name}) from {old_matter}")
    ingest_worker.enqueue(body.doc_id, str(dest), body.matter, str(KB_DB),
                          catalog.DEFAULT_DB)
    return {"moved": body.doc_id, "matter": body.matter, "filename": dest.name}


@router.get("/kb/ingest/status")
def ingest_status():
    """Ingest progress for the Hub (Move 0c): queue depth, in-flight doc + stage,
    lifetime processed count. Read-only; no document content."""
    return ingest_worker.status()


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
    media = _MEDIA.get(stored.suffix.lower(), "application/octet-stream")
    if keyvault.is_encrypted_file(stored):  # D-73: serve the decrypted native
        return Response(keyvault.read_matter_file(stored, row["matter_slug"]),
                        media_type=media)
    return FileResponse(stored, media_type=media)


def _managed_pdf(doc_id):
    """A fitz-ready managed PDF inside documents/kb/, or None. Path-locked + must be
    a .pdf. Returns the path — or, for a DEK-encrypted native (D-73), the decrypted
    BYTES (pdf_view renders either; plaintext stays in memory)."""
    row = catalog.get_document(doc_id)
    if not row:
        return None
    stored = Path(row["stored_path"])
    if not _within_kb(stored) or stored.suffix.lower() != ".pdf" or not stored.is_file():
        return None
    if keyvault.is_encrypted_file(stored):
        return keyvault.read_matter_file(stored, row["matter_slug"])
    return stored


@router.get("/kb/thumb/{doc_id}")
def thumb(doc_id: int, page: int = 1):
    """A retrieved page rendered to a PNG thumbnail (path-locked to documents/kb/)."""
    target = _managed_pdf(doc_id)
    if target is None:
        raise HTTPException(status_code=404, detail="not found")
    return Response(pdf_view.render_page_png(target, page), media_type="image/png")


@router.get("/kb/highlight/{doc_id}")
def highlight(doc_id: int, page: int = 1, span: str = ""):
    """The retrieved page with the cited span highlighted. ``span`` is text passed to
    search_for (never interpolated into a path); the file is rendered read-only."""
    target = _managed_pdf(doc_id)
    if target is None:
        raise HTTPException(status_code=404, detail="not found")
    return Response(pdf_view.highlight_span_png(target, page, span), media_type="image/png")


@router.delete("/kb/documents/{doc_id}")
def delete(doc_id: int):
    row = catalog.get_document(doc_id)
    if not row:
        raise HTTPException(status_code=404, detail="not found")
    # Move 4 (D-72): a legal hold freezes ALL disposal in the matter, including
    # single-document deletes (FRCP 37(e) preservation).
    hold = catalog.active_hold(row["matter_slug"])
    if hold:
        raise HTTPException(status_code=409,
                            detail=f"legal hold active since {hold['created']}: "
                                   f"{hold['reason']}")
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
