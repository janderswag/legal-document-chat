"""Matters router — list/create matters (the D-18 retrieval scope). Read + create only;
no matter is ever inferred from text (explicit selection only, D-35)."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import catalog

router = APIRouter()


class NewMatter(BaseModel):
    display_name: str


@router.get("/matters")
def get_matters():
    """All matters, with the seeded demo matter flagged (P1.3) so the UI can offer its
    one-click suggested questions. Flag + questions are static metadata — no model or
    retrieval involvement."""
    import sample_matter
    matters = catalog.list_matters()
    for m in matters:
        if m["slug"] in sample_matter.SAMPLE_SLUGS:
            m["sample"] = True
            m["suggested_questions"] = sample_matter.SUGGESTED_QUESTIONS
    return {"matters": matters}


@router.post("/matters")
def post_matter(body: NewMatter):
    try:
        return catalog.create_matter(body.display_name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
