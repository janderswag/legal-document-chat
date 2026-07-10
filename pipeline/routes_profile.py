"""Profile router — the attorney's LOCAL identity (UX-5 onboarding, UX-6 profile page).

Stored ONLY in the local catalog (SQLCipher-encrypted in production); it never
leaves the machine. Used to greet the user by name, tailor suggested prompts to
their practice area(s), and (later) stamp exported work product. Deliberately NO
email, phone, firm-size, or account fields — collecting contact data would
contradict the no-account privacy promise, and every field here must have a
visible in-product use (research: unused onboarding fields are pure friction and,
for this audience, a privacy red flag).

Memory (UX-6) is TEACHABLE, not learned: ``memory_notes`` are facts the user
writes and can see/delete. They feed the greeting and suggestion layer ONLY —
they are structurally fenced OUT of the grounded answer path (answering.py has no
access to this module; test_memory_fencing proves it), so a remembered "fact" can
never contaminate a cited answer or leak across matters.

The profile photo is a plain local file under the app data dir (it is the user's
own avatar on their own disk; document data is never stored beside it).
"""

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

import apppaths
import catalog

router = APIRouter()

# Shown as multi-select chips during onboarding and in Settings. Free-text is not
# rejected (the UI offers these; the API just bounds sizes).
PRACTICE_AREAS = [
    "Business & Contracts", "Litigation", "Employment", "Estate & Probate",
    "Real Estate", "Family", "Criminal Defense", "Immigration",
    "Personal Injury", "IP & Technology",
]

_MAX_NAME = 80
_MAX_ROLE = 80
_MAX_FIRM = 120
_MAX_AREAS = 12
_MAX_AREA_LEN = 48
_MAX_NOTES = 50
_MAX_NOTE_LEN = 400

_PHOTO_PATH = apppaths.data_root() / ".profile_photo"
_PHOTO_MAX_BYTES = 5 * 1024 * 1024
# magic-byte sniff — we never trust a client-asserted content type
_PHOTO_MAGIC = {b"\x89PNG\r\n\x1a\n": "image/png", b"\xff\xd8\xff": "image/jpeg"}


class ProfileUpdate(BaseModel):
    name: str | None = None
    role: str | None = None
    firm: str | None = None
    practice_areas: list[str] | None = None
    memory_notes: list[str] | None = None
    onboarded: bool | None = None


def _public_profile():
    p = catalog.get_profile()
    p["available_practice_areas"] = PRACTICE_AREAS
    p["has_photo"] = _PHOTO_PATH.is_file()
    return p


@router.get("/profile")
def get_profile():
    return _public_profile()


# POST (not PUT): the app keeps its "no PUT/PATCH anywhere" structural lock
# (test_api.TestSafetyStructural) — like /setup/pull, this is one of the few
# deliberate non-read-only actions, and it touches ONLY local app config,
# never a document.
@router.post("/profile")
def put_profile(body: ProfileUpdate):
    vals = {}
    if body.name is not None:
        vals["name"] = body.name.strip()[:_MAX_NAME]
    if body.role is not None:
        vals["role"] = body.role.strip()[:_MAX_ROLE]
    if body.firm is not None:
        vals["firm"] = body.firm.strip()[:_MAX_FIRM]
    if body.practice_areas is not None:
        vals["practice_areas"] = [str(a).strip()[:_MAX_AREA_LEN]
                                  for a in body.practice_areas
                                  if str(a).strip()][:_MAX_AREAS]
    if body.memory_notes is not None:
        vals["memory_notes"] = [str(n).strip()[:_MAX_NOTE_LEN]
                                for n in body.memory_notes
                                if str(n).strip()][:_MAX_NOTES]
    if body.onboarded is not None:
        vals["onboarded"] = bool(body.onboarded)
    catalog.set_profile(vals)
    return _public_profile()


@router.get("/profile/photo")
def get_photo():
    if not _PHOTO_PATH.is_file():
        raise HTTPException(status_code=404, detail="no photo")
    p = catalog.get_profile()
    return FileResponse(_PHOTO_PATH, media_type=p.get("photo_type") or "image/png")


@router.post("/profile/photo")
async def set_photo(request: Request):
    """Raw-body upload (same no-multipart pattern as /kb/upload). PNG or JPEG only,
    verified by magic bytes; 5 MB cap."""
    body = await request.body()
    if not body:
        raise HTTPException(status_code=400, detail="empty upload")
    if len(body) > _PHOTO_MAX_BYTES:
        raise HTTPException(status_code=400, detail="photo too large (5 MB max)")
    media = next((m for magic, m in _PHOTO_MAGIC.items() if body.startswith(magic)), None)
    if media is None:
        raise HTTPException(status_code=400, detail="photo must be PNG or JPEG")
    _PHOTO_PATH.parent.mkdir(parents=True, exist_ok=True)
    _PHOTO_PATH.write_bytes(body)
    catalog.set_profile({"photo_type": media})
    return {"ok": True, "has_photo": True}


@router.post("/profile/photo/delete")
def delete_photo():
    """POST, not DELETE — DELETE stays structurally locked to /kb/documents."""
    _PHOTO_PATH.unlink(missing_ok=True)
    catalog.set_profile({"photo_type": None})
    return {"ok": True, "has_photo": False}
