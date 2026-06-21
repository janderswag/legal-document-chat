"""Chat router — matter-scoped cited answering over .lancedb_kb, with persisted threads.

POST /chat answers ONLY from the chosen matter's KB chunks (D-18 hard pre-filter inside
answer()/retrieve()); citations are chunk-derived (D-38) + span-verified (D-19). An
empty matter (no indexed chunks) returns the exact D-30 refusal — never a tool/web call
(D-2). Threads + messages persist for Chat History.
"""

import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

import catalog
import routes_kb  # for the shared KB_DB path (monkeypatchable in tests)
from answering import answer, answer_stream, REFUSAL

router = APIRouter()


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

    try:
        res = answer(body.question, matter=body.matter, db_path=str(routes_kb.KB_DB),
                     with_confidence=True)  # B4: non-gating display signal
    except ValueError:
        # matter has no indexed chunks yet (empty KB) -> D-30 refusal, no tool/web call
        res = _refusal_result()

    # Enrich each chunk-derived citation with its catalog doc_id so the UI can request
    # the page thumbnail + cited-span highlight. doc_id is looked up by (matter, filename)
    # — the displayed page/span stay chunk-derived (D-38); we add no model-asserted data.
    by_name = {d["filename"]: d["id"] for d in catalog.list_documents(body.matter)}
    for c in res["citations"]:
        c["doc_id"] = by_name.get(c["filename"])

    catalog.add_message(thread_id, "assistant", res["answer_text"],
                        json.dumps(res["citations"]))
    catalog.touch_thread(thread_id)
    return {"thread_id": thread_id, **res}


def _enrich_doc_ids(matter, citations):
    by_name = {d["filename"]: d["id"] for d in catalog.list_documents(matter)}
    for c in citations:
        c["doc_id"] = by_name.get(c["filename"])


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

    def gen():
        result = None
        try:
            for ev in answer_stream(body.question, matter=body.matter,
                                    db_path=str(routes_kb.KB_DB)):
                if ev["type"] == "token":
                    yield event("token", {"text": ev["text"]})
                else:
                    result = ev
        except ValueError:
            result = {"answer_text": REFUSAL, "citations": [], "rejected_claims": []}
        _enrich_doc_ids(body.matter, result["citations"])
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
