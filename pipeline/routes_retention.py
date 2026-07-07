"""Move 4 (D-72) — retention routes: legal hold, export-everything, disposition with an
honest certificate, and audit-chain verification. Matter-scoped, loopback-only.

Flow contract: dispose requires ``confirm=true`` AND is refused (409) under an active
hold. Export is offered independently and the UI runs it before dispose; the
certificate records what was actually done, never more."""

import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

import catalog
import retention
import routes_kb

router = APIRouter()


class HoldRequest(BaseModel):
    reason: str


def _require_matter(slug):
    if not catalog.get_matter(slug):
        raise HTTPException(status_code=404, detail=f"unknown matter: {slug!r}")


@router.get("/retention/{matter}/status")
def status(matter: str):
    _require_matter(matter)
    hold = catalog.active_hold(matter)
    return {"hold": hold, "audit": catalog.audit_entries(matter)[-20:]}


@router.post("/retention/{matter}/hold")
def hold(matter: str, body: HoldRequest):
    _require_matter(matter)
    if not body.reason.strip():
        raise HTTPException(status_code=400, detail="a hold reason is required")
    catalog.place_hold(matter, body.reason.strip())
    return {"hold": catalog.active_hold(matter)}


@router.post("/retention/{matter}/release")
def release(matter: str, body: HoldRequest):
    _require_matter(matter)
    if not catalog.active_hold(matter):
        raise HTTPException(status_code=400, detail="no active hold")
    catalog.release_hold(matter, body.reason.strip() or "released")
    return {"hold": None}


@router.get("/retention/{matter}/export")
def export(matter: str):
    _require_matter(matter)
    data = retention.export_matter(matter, routes_kb.KB_DOCS)
    return Response(data, media_type="application/zip",
                    headers={"Content-Disposition":
                             f'attachment; filename="matter-{matter}-export.zip"'})


@router.post("/retention/{matter}/dispose")
def dispose(matter: str, confirm: bool = False):
    _require_matter(matter)
    if not confirm:
        raise HTTPException(status_code=400,
                            detail="disposition requires confirm=true (export first)")
    try:
        cert = retention.dispose_matter(matter, routes_kb.KB_DB, routes_kb.KB_DOCS)
    except PermissionError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return cert


@router.get("/retention/audit/verify")
def verify():
    ok, first_bad = catalog.verify_audit_chain()
    return {"ok": ok, "first_bad_id": first_bad,
            "entries": len(catalog.audit_entries())}
