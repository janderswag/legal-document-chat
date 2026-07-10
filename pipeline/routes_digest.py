"""Matter overview API (M-2). Serves ONLY mechanically verified fact rows plus the
attorney's review state — zero LLM calls at read time. Deadline dates are the
attorney's: docuchat surfaces source language; the human supplies/confirms the date."""

import json
import re

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import catalog
import digest

router = APIRouter()

_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class ReviewBody(BaseModel):
    status: str | None = None
    confirmed_date: str | None = None


def _require_matter(matter):
    if catalog.get_matter(matter) is None:
        raise HTTPException(status_code=404, detail="unknown matter")


@router.get("/matters/{matter}/overview")
def overview(matter: str):
    _require_matter(matter)
    reviews = catalog.reviews_for_matter(matter)
    out = {"building": catalog.digest_progress(matter, digest.EXTRACTOR_VERSION),
           "deadlines": [], "timeline": [], "parties": [], "amounts": [],
           "terms": [], "refs": [], "dismissed_count": 0}
    buckets = {"party": "parties", "amount": "amounts",
               "defined_term": "terms", "key_ref": "refs"}
    for row in catalog.facts_for_matter(matter):
        review = reviews.get(row["fact_key"])
        if review and review["status"] == "dismissed":
            out["dismissed_count"] += 1
            continue
        item = {"fact_key": row["fact_key"], "fact_type": row["fact_type"],
                "value": json.loads(row["value_json"]), "page": row["page"],
                "span": row["span"], "doc_id": row["doc_id"],
                "filename": row["filename"], "review": review}
        if row["fact_type"] == "date_event":
            out["timeline"].append(item)
            if item["value"].get("kind") in ("deadline", "obligation"):
                out["deadlines"].append(item)
        else:
            out[buckets[row["fact_type"]]].append(item)

    def _due(i):   # unconfirmed first, then by best-known date; dateless last
        eff = (i["review"] or {}).get("confirmed_date") or i["value"].get("date_iso")
        return (0 if not (i["review"] and i["review"]["status"] == "confirmed") else 1,
                eff or "9999-99-99")
    out["deadlines"].sort(key=_due)
    out["timeline"].sort(key=lambda i: i["value"].get("date_iso") or "9999-99-99")
    return out


@router.post("/matters/{matter}/facts/{fact_key}/review")
def review_fact(matter: str, fact_key: str, body: ReviewBody):
    _require_matter(matter)
    if body.status not in ("confirmed", "dismissed", None):
        raise HTTPException(status_code=422, detail="status must be confirmed, dismissed, or null")
    if body.confirmed_date is not None and not _ISO.match(body.confirmed_date):
        raise HTTPException(status_code=422, detail="confirmed_date must be YYYY-MM-DD")
    catalog.set_fact_review(matter, fact_key, body.status, body.confirmed_date)
    catalog.audit_append("fact_review", matter,
                         json.dumps({"fact_key": fact_key, "status": body.status,
                                     "confirmed_date": body.confirmed_date}))
    return {"ok": True}
