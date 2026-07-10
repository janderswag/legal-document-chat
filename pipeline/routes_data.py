"""Erase-everything router (UX-6) — the honest local version of "delete my account".

There is no account; there is data on this machine. POST /data/erase disposes of
EVERY matter through the existing retention machinery (which crypto-shreds each
matter's DEK where the encryption cycle is active, removes documents, index rows,
and chat threads, and appends audit events), then clears the profile and photo.

Safety properties:
- Requires the literal typed confirmation ``"ERASE EVERYTHING"`` (never a bare
  boolean a stray click could send).
- REFUSED (409) while any matter is under an active legal hold — an erase-all that
  silently bypassed holds would be a spoliation machine. Release holds first,
  deliberately, one by one.
- The hash-chained audit log is retained: it records the disposals themselves and
  contains event metadata, never document content. It is the provenance for the
  disposition certificates the user may need later.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import catalog
import retention
import routes_kb
import routes_profile

router = APIRouter()

CONFIRM_PHRASE = "ERASE EVERYTHING"


class EraseRequest(BaseModel):
    confirm: str = ""


@router.post("/data/erase")
def erase_all(body: EraseRequest):
    if body.confirm != CONFIRM_PHRASE:
        raise HTTPException(status_code=400,
                            detail=f'confirmation must be exactly "{CONFIRM_PHRASE}"')

    matters = catalog.list_matters()
    held = [m["slug"] for m in matters if catalog.active_hold(m["slug"])]
    if held:
        raise HTTPException(status_code=409,
                            detail="active legal hold on: " + ", ".join(held) +
                                   ". Release holds first — erase never bypasses a hold.")

    disposed = []
    for m in matters:
        retention.dispose_matter(m["slug"], routes_kb.KB_DB, routes_kb.KB_DOCS)
        disposed.append(m["slug"])

    # profile + photo go last, so a mid-erase failure leaves the profile intact
    # (the user can see the app still knows them and retry).
    catalog.clear_profile()
    routes_profile._PHOTO_PATH.unlink(missing_ok=True)
    catalog.audit_append("erase_all", detail=f"{len(disposed)} matters disposed")
    return {"ok": True, "matters_disposed": disposed}
