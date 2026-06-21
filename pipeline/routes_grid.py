"""Tabular-review grid router — POST /grid streams a (document x question) matrix as SSE.

Read-only: NO action verbs, no document mutation (D-2). The matter is validated against the
catalog allowlist (D-35; unknown -> 400). Each cell is evaluated over the matter's KB store
via the existing answer()+verifier and the T-CLAUSE classifier (span-verified only, D-19/
D-38), with the doc_id post-filter blocking cross-document citation leaks. Concurrency is
bounded inside grid.run_grid (<= 4 workers); cells stream live as they complete.
"""

import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

import catalog
import grid
import routes_kb  # shared KB store path (monkeypatchable in tests)

router = APIRouter()


class GridRequest(BaseModel):
    matter: str
    doc_ids: list[int] | None = None
    questions: list[str] | None = None     # custom-question override (A2)
    clause_ids: list[str] | None = None    # taxonomy subset (A2)
    max_workers: int = 3                    # clamped to <= 4 inside grid


def _event(name, obj):
    return f"event: {name}\ndata: {json.dumps(obj)}\n\n"


@router.post("/grid")
def post_grid(body: GridRequest):
    if not catalog.get_matter(body.matter):
        raise HTTPException(status_code=400, detail=f"unknown matter: {body.matter!r}")

    docs = grid.resolve_docs(body.matter, doc_ids=body.doc_ids)
    columns = grid.resolve_columns(questions=body.questions, clause_ids=body.clause_ids)

    def stream():
        yield _event("meta", {
            "matter": body.matter,
            "docs": docs,
            "columns": [{"id": c["id"], "name": c.get("name"), "question": c["question"]}
                        for c in columns],
        })
        count = 0
        for cell in grid.run_grid(body.matter, docs, columns,
                                  db_path=str(routes_kb.KB_DB),
                                  max_workers=body.max_workers):
            count += 1
            yield _event("cell", cell)
        yield _event("done", {"count": count})

    return StreamingResponse(stream(), media_type="text/event-stream")
