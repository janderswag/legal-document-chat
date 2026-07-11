"""Chat router — matter-scoped cited answering over .lancedb_kb, with persisted threads.

POST /chat answers ONLY from the chosen matter's KB chunks (D-18 hard pre-filter inside
answer()/retrieve()); citations are chunk-derived (D-38) + span-verified (D-19). An
empty matter (no indexed chunks) returns the exact D-30 refusal — never a tool/web call
(D-2). Threads + messages persist for Chat History.
"""

import json
import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

import activity
import catalog
import routes_kb  # for the shared KB_DB path (monkeypatchable in tests)
from answering import answer, answer_stream, small_talk_reply, REFUSAL

router = APIRouter()
log = logging.getLogger("docuchat.chat")


class ChatRequest(BaseModel):
    question: str
    matter: str
    thread_id: int | None = None


def _refusal_result():
    return {"answer_text": REFUSAL, "citations": [], "rejected_claims": [],
            "grounding_chunks": [], "confidence": None}


@router.post("/chat")
def chat(body: ChatRequest):
    if not catalog.get_matter(body.matter):
        raise HTTPException(status_code=400, detail=f"unknown matter: {body.matter!r}")
    if not body.question.strip():
        raise HTTPException(status_code=400, detail="empty question")

    thread_id = body.thread_id
    if not thread_id:
        thread_id = catalog.create_thread(body.matter, body.question.strip())["id"]
    catalog.add_message(thread_id, "user", body.question)

    # UX-1: a pure greeting/courtesy message gets a canned reply with NO retrieval —
    # no embedding, no vector search, no passages shown for a question never asked.
    canned = small_talk_reply(body.question)
    if canned is not None:
        catalog.add_message(thread_id, "assistant", canned, json.dumps([]))
        catalog.touch_thread(thread_id)
        return {"thread_id": thread_id, "answer_text": canned, "citations": [],
                "rejected_claims": [], "grounding_chunks": [], "confidence": None,
                "small_talk": True}

    activity.mark_chat()    # interactive priority: pause background ingest (Move 0b)
    try:
        res = answer(body.question, matter=body.matter, db_path=str(routes_kb.KB_DB),
                     with_confidence=True)  # B4: non-gating display signal
    except ValueError:
        # matter has no indexed chunks yet (empty KB) -> D-30 refusal, no tool/web call
        res = _refusal_result()

    # Enrich each chunk-derived citation with its catalog doc_id so the UI can request
    # the page thumbnail + cited-span highlight. doc_id is looked up by (matter, filename)
    # — the displayed page/span stay chunk-derived (D-38); we add no model-asserted data.
    _enrich_citations(body.matter, res["citations"], res.get("grounding_chunks"))

    catalog.add_message(thread_id, "assistant", res["answer_text"],
                        json.dumps(res["citations"]))
    catalog.touch_thread(thread_id)
    return {"thread_id": thread_id, **res}


def _enrich_citations(matter, citations, grounding):
    """Runs both display-only enrichments and never lets a failure in either one lose an
    already-generated, already-verified answer. Root cause of the "one session splits into
    row-per-message" Chat History bug: this used to run unguarded after the SSE stream's
    token loop, so a lookup failure here (e.g. a transient catalog read) raised past the
    generator's only `except ValueError`, which aborted the stream before the 'done' event
    (and its thread_id) ever reached the client. The next send then had no thread_id to
    carry, so it created a brand-new thread instead of appending to the existing one. The
    citations themselves stay verifier-produced either way (D-19/D-38); only the doc_id/
    line-number DECORATION is best-effort."""
    try:
        _enrich_doc_ids(matter, citations)
        _enrich_transcript_lines(matter, citations, grounding)
    except Exception:
        log.exception("citation enrichment failed; answer still delivered without it")


def _enrich_doc_ids(matter, citations):
    by_name = {d["filename"]: d["id"] for d in catalog.list_documents(matter)}
    for c in citations:
        c["doc_id"] = by_name.get(c["filename"])


def _enrich_transcript_lines(matter, citations, grounding):
    """Move 2a (D-70): derive page:line for citations into transcript documents by
    mapping the VERIFIER-CONFIRMED span offsets through the stored line map. The model
    never asserts a line number; an ambiguous span (text occurring more than once on
    the page) gets NO line range — precise or absent. Display metadata only: page/span
    provenance stays chunk-derived and mechanically verified."""
    import transcript_extract as te
    docs = {d["filename"]: d for d in catalog.list_documents(matter)}
    page_text = {(g["source_filename"], g["page_number"]): g["text"]
                 for g in grounding or []}
    for c in citations:
        d = docs.get(c["filename"])
        if not d or d.get("doc_type") != "transcript" or c.get("char_start") is None:
            continue
        entries = catalog.line_map_for_page(d["id"], c["page"])
        lines = te.derive_lines(entries, c["char_start"], c["char_end"],
                                page_text.get((c["filename"], c["page"]), ""),
                                c.get("span", ""))
        if lines:
            c["lines"] = lines


@router.post("/chat/stream")
def chat_stream(body: ChatRequest):
    """Streaming variant of /chat (B6): tokens stream live over SSE, then a 'done' event
    carries the verified citations (verifier runs on the COMPLETE text, never a partial).
    Perceived-latency only — citations are identical to /chat."""
    if not catalog.get_matter(body.matter):
        raise HTTPException(status_code=400, detail=f"unknown matter: {body.matter!r}")
    if not body.question.strip():
        raise HTTPException(status_code=400, detail="empty question")

    thread_id = body.thread_id or catalog.create_thread(body.matter, body.question.strip())["id"]
    catalog.add_message(thread_id, "user", body.question)

    def event(name, obj):
        return f"event: {name}\ndata: {json.dumps(obj)}\n\n"

    # UX-1: small talk streams the canned reply immediately — no retrieval, no
    # 'sources' event (nothing is being read), empty citations on 'done'.
    canned = small_talk_reply(body.question)
    if canned is not None:
        def gen_small_talk():
            catalog.add_message(thread_id, "assistant", canned, json.dumps([]))
            catalog.touch_thread(thread_id)
            yield event("token", {"text": canned})
            yield event("done", {"thread_id": thread_id, "answer_text": canned,
                                 "citations": [], "rejected_claims": [],
                                 "small_talk": True})
        return StreamingResponse(gen_small_talk(), media_type="text/event-stream")

    def gen():
        result = None
        activity.mark_chat()    # interactive priority: pause background ingest (Move 0b)
        try:
            for ev in answer_stream(body.question, matter=body.matter,
                                    db_path=str(routes_kb.KB_DB)):
                if ev["type"] == "token":
                    yield event("token", {"text": ev["text"]})
                elif ev["type"] == "second_pass":
                    # 1b: the first pass refused; a wider anchor-fed retrieval retry is
                    # starting. The UI clears the streamed refusal and shows the state.
                    yield event("second_pass", {})
                elif ev["type"] == "sources":
                    # Retrieved (chunk-derived) passages, shown as "reading" while the
                    # answer generates — candidates only, NEVER presented as verified
                    # citations (those come exclusively from the 'done' event below).
                    srcs = [{"filename": g["source_filename"], "page": g["page_number"],
                             "snippet": g["text"][:200]} for g in ev["grounding"]]
                    try:
                        _enrich_doc_ids(body.matter, srcs)
                    except Exception:
                        log.exception("sources doc_id lookup failed; showing without it")
                    yield event("sources", {"sources": srcs})
                else:
                    result = ev
        except ValueError:
            result = {"answer_text": REFUSAL, "citations": [], "rejected_claims": []}
        activity.mark_chat()    # re-mark at completion: quiet window starts now
        # Enrichment failures must never cost the client the 'done' event / thread_id
        # (see _enrich_citations docstring — that gap is how one chat session used to
        # split into a separate Chat History row per message).
        _enrich_citations(body.matter, result["citations"], result.get("grounding_chunks"))
        catalog.add_message(thread_id, "assistant", result["answer_text"],
                            json.dumps(result["citations"]))
        catalog.touch_thread(thread_id)
        yield event("done", {"thread_id": thread_id, "answer_text": result["answer_text"],
                             "citations": result["citations"],
                             "rejected_claims": result.get("rejected_claims", [])})

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.get("/chat/threads")
def list_threads():
    return {"threads": catalog.list_threads()}


@router.get("/chat/threads/{thread_id}")
def thread_messages(thread_id: int):
    return {"messages": catalog.get_thread_messages(thread_id)}
