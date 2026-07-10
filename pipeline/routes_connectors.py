"""Connectors router (UX-6) — watched folders, the local-first import surface.

GET lists watched folders with live status (exists / missing). POSTs add/remove.
All verbs are POST/GET (no PUT/PATCH/DELETE — the structural lock in test_api
stays intact). No network egress: a "connector" here is a directory on disk.
"""

from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import catalog
import watchers

router = APIRouter()


class NewFolder(BaseModel):
    matter: str
    path: str


class RemoveFolder(BaseModel):
    id: int


@router.get("/connectors/folders")
def list_folders():
    out = []
    for wf in catalog.list_watch_folders():
        out.append({**wf, "exists": Path(wf["path"]).is_dir()})
    return {"folders": out, "poll_seconds": watchers.POLL_SECONDS}


@router.post("/connectors/folders")
def add_folder(body: NewFolder):
    if not catalog.get_matter(body.matter):
        raise HTTPException(status_code=400, detail=f"unknown matter: {body.matter!r}")
    try:
        folder = watchers.validate_folder(body.path)
        row = catalog.add_watch_folder(body.matter, folder)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return row


@router.post("/connectors/folders/remove")
def remove_folder(body: RemoveFolder):
    catalog.remove_watch_folder(body.id)
    return {"ok": True}
