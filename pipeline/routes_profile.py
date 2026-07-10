"""Profile router — the attorney's LOCAL identity (UX-5 onboarding).

Stored ONLY in the local catalog (SQLCipher-encrypted in production); it never
leaves the machine. Used to greet the user by name, tailor suggested prompts to
their practice area(s), and (later) stamp exported work product. Deliberately NO
email, phone, firm-size, or account fields — collecting contact data would
contradict the no-account privacy promise, and every field here must have a
visible in-product use (research: unused onboarding fields are pure friction and,
for this audience, a privacy red flag).
"""

from fastapi import APIRouter
from pydantic import BaseModel

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
_MAX_AREAS = 12
_MAX_AREA_LEN = 48


class ProfileUpdate(BaseModel):
    name: str | None = None
    practice_areas: list[str] | None = None
    onboarded: bool | None = None


@router.get("/profile")
def get_profile():
    p = catalog.get_profile()
    p["available_practice_areas"] = PRACTICE_AREAS
    return p


# POST (not PUT): the app keeps its "no PUT/PATCH anywhere" structural lock
# (test_api.TestSafetyStructural) — like /setup/pull, this is one of the few
# deliberate non-read-only actions, and it touches ONLY local app config,
# never a document.
@router.post("/profile")
def put_profile(body: ProfileUpdate):
    vals = {}
    if body.name is not None:
        vals["name"] = body.name.strip()[:_MAX_NAME]
    if body.practice_areas is not None:
        vals["practice_areas"] = [str(a).strip()[:_MAX_AREA_LEN]
                                  for a in body.practice_areas
                                  if str(a).strip()][:_MAX_AREAS]
    if body.onboarded is not None:
        vals["onboarded"] = bool(body.onboarded)
    catalog.set_profile(vals)
    p = catalog.get_profile()
    p["available_practice_areas"] = PRACTICE_AREAS
    return p
