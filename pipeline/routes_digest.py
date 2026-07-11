"""Matter overview API (M-2). Serves ONLY mechanically verified fact rows plus the
attorney's review state — zero LLM calls at read time. Deadline dates are the
attorney's: docuchat surfaces source language; the human supplies/confirms the date."""

import json
import re
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

import catalog
import digest

router = APIRouter()

_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ICS_CRLF = "\r\n"


class ReviewBody(BaseModel):
    status: str | None = None
    confirmed_date: str | None = None


def _require_matter(matter):
    if catalog.get_matter(matter) is None:
        raise HTTPException(status_code=404, detail="unknown matter")


def _ics_escape(text):
    """RFC 5545 TEXT escaping: backslash, then semicolon/comma, then newlines as \\n."""
    text = (text or "").replace("\\", "\\\\")
    text = text.replace(";", "\\;").replace(",", "\\,")
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\\n")
    return text


def _ics_fold_line(line):
    """Fold one content line so no physical (CRLF-terminated) line exceeds 75 octets,
    per RFC 5545 3.1. Continuation lines are prefixed with a single space, which counts
    against their 75-octet budget. Never splits a UTF-8 multi-byte sequence."""
    data = line.encode("utf-8")
    if len(data) <= 75:
        return line
    chunks = []
    start, limit = 0, 75
    while start < len(data):
        end = min(start + limit, len(data))
        while end < len(data) and (data[end] & 0xC0) == 0x80:  # UTF-8 continuation byte
            end -= 1
        chunks.append(data[start:end])
        start = end
        limit = 74  # subsequent physical lines reserve 1 octet for the leading space
    return _ICS_CRLF.join(
        chunk.decode("utf-8") if i == 0 else " " + chunk.decode("utf-8")
        for i, chunk in enumerate(chunks))


def _build_ics(fact_key, matter_display, label, confirmed_date, span, filename, page):
    dtstamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dtstart = confirmed_date.replace("-", "")
    summary = f"{label} ({matter_display})"
    description = (f'Source: "{span}" {filename} p.{page}\n'
                    "Extracted by docuchat. Verify against the source document.")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//docuchat//EN",
        "BEGIN:VEVENT",
        "UID:" + _ics_escape(f"{fact_key}@docuchat.local"),
        "DTSTAMP:" + dtstamp,
        "DTSTART;VALUE=DATE:" + dtstart,
        "SUMMARY:" + _ics_escape(summary),
        "DESCRIPTION:" + _ics_escape(description),
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    return _ICS_CRLF.join(_ics_fold_line(l) for l in lines) + _ICS_CRLF


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


@router.get("/matters/{matter}/facts/{fact_key}/calendar.ics")
def fact_calendar(matter: str, fact_key: str):
    """A single all-day VEVENT for one attorney-confirmed deadline. The date is the
    attorney's confirmed_date verbatim — docuchat never computes or offsets it, and
    the event carries no alarms/reminders. Export exists only for attorney-entered dates;
    a confirmation without a date must never fall back to the document's as-written date."""
    matter_row = catalog.get_matter(matter)
    if matter_row is None:
        raise HTTPException(status_code=404, detail="unknown matter")
    fact = next((r for r in catalog.facts_for_matter(matter) if r["fact_key"] == fact_key), None)
    if fact is None:
        raise HTTPException(status_code=404, detail="unknown fact")
    value = json.loads(fact["value_json"])
    if fact["fact_type"] != "date_event" or value.get("kind") not in ("deadline", "obligation"):
        raise HTTPException(status_code=409, detail="fact is not a deadline")
    review = catalog.reviews_for_matter(matter).get(fact_key)
    if not review or review["status"] != "confirmed" or not review.get("confirmed_date"):
        raise HTTPException(status_code=409, detail="deadline is not confirmed")
    confirmed_date = review["confirmed_date"]

    ics = _build_ics(fact_key, matter_row["display_name"], value.get("label") or "",
                      confirmed_date, fact["span"], fact["filename"], fact["page"])
    catalog.audit_append("deadline_calendar_export", matter, json.dumps({"fact_key": fact_key}))
    return Response(content=ics, media_type="text/calendar; charset=utf-8",
                    headers={"Content-Disposition":
                             f'attachment; filename="deadline-{confirmed_date}.ics"'})
