"""T-GRID — tabular review grid (D-49). A (document x question) matrix evaluated over the
EXISTING retrieve+answer+verify path, reusing the T-CLAUSE cell classifier.

Each cell = one question asked of one document's matter context. Classification reuses
``clauses._classify`` (NOT a forked verifier): a cell is "found" only with a span-verified,
chunk-derived citation (D-19/D-38); the D-30 refusal -> "potentially_missing"; prose whose
spans the verifier rejected -> "not_confirmed". The doc_id post-filter (target_filename)
scopes each cell's citations to its own document, so a clause present elsewhere in the
matter never leaks onto the wrong row.

Concurrency is BOUNDED (a thread pool of <= 4 workers, never unbounded ``Promise.all``):
cells are streamed as they complete (the SSE route consumes this generator). Read-only;
runs against whichever store ``db_path`` selects; never re-embeds.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed

import catalog
from answering import REFUSAL, answer  # answer() is monkeypatched in unit tests
from clauses import _classify as classify_cell, load_taxonomy

_MAX_WORKERS = 4  # hard ceiling on concurrent answer() calls (never unbounded)


def _clamp_workers(n):
    try:
        n = int(n)
    except (TypeError, ValueError):
        n = 3
    return max(1, min(n, _MAX_WORKERS))


def resolve_columns(questions=None, clause_ids=None, taxonomy=None, taxonomy_path=None):
    """The grid columns. Default = the full clause taxonomy (A2). ``clause_ids`` selects a
    subset (in the given order); ``questions`` (list of strings or {id,question} dicts)
    overrides with custom questions."""
    tax = taxonomy if taxonomy is not None else load_taxonomy(taxonomy_path)
    if questions:
        cols = []
        for i, q in enumerate(questions):
            if isinstance(q, str):
                cols.append({"id": f"q{i + 1}", "name": q[:48], "category": "Custom",
                             "question": q})
            else:
                cols.append({"id": q.get("id", f"q{i + 1}"),
                             "name": q.get("name", q["question"][:48]),
                             "category": q.get("category", "Custom"),
                             "question": q["question"]})
        return cols
    if clause_ids:
        by_id = {c["id"]: c for c in tax}
        return [by_id[cid] for cid in clause_ids if cid in by_id]
    return list(tax)


def resolve_docs(matter, doc_ids=None, catalog_db=None):
    """The grid rows: ``[{doc_id, filename}]`` for ``matter``. ``doc_ids`` (optional)
    restricts to those documents (and only ones that belong to the matter — no cross-matter
    rows). Default = every document in the matter."""
    docs = catalog.list_documents(matter, db_path=catalog_db)
    if doc_ids is not None:
        wanted = set(doc_ids)
        docs = [d for d in docs if d["id"] in wanted]
    return [{"doc_id": d["id"], "filename": d["filename"]} for d in docs]


def evaluate_column(matter, docs, column, db_path=None, top_k=5):
    """Evaluate one question for EVERY document row from a SINGLE answer() call.

    The per-cell answer() call was identical across a column by construction — the
    question and matter are the cell's only retrieval inputs; the document only
    scopes the CLASSIFICATION (target_filename post-filter). Memoizing it is the
    council 2026-07-11 Move 2i fix: 5 docs x 20 clauses cost 100 calls, now 20.
    Citations are copied per row before doc_id enrichment so rows never share dicts;
    the cross-document leak filter is unchanged (a citation only survives onto the
    row whose filename it carries)."""
    try:
        res = answer(column["question"], matter=matter, top_k=top_k, db_path=db_path)
    except ValueError:
        # matter has no indexed chunks -> clean refusal (never a fabricated citation)
        res = {"answer_text": REFUSAL, "citations": [], "rejected_claims": [],
               "grounding_chunks": []}
    cells = []
    for doc in docs:
        scoped = dict(res)
        scoped["citations"] = [dict(c) for c in (res.get("citations") or [])]
        row = classify_cell(column, scoped, target_filename=doc["filename"])
        for c in row["citations"]:
            c["doc_id"] = doc["doc_id"]  # every kept citation is on this row's document
        cells.append({
            "doc_id": doc["doc_id"], "filename": doc["filename"],
            "column_id": column["id"], "column_name": column.get("name"),
            "question": column["question"],
            "status": row["status"], "value": row["value"],
            "citations": row["citations"], "rejected_claims": row["rejected_claims"],
        })
    return cells


def run_grid(matter, docs, columns, db_path=None, top_k=5, max_workers=3):
    """Yield each cell as its column completes, with BOUNDED concurrency (<= 4
    workers over answer() calls). Column completion order (the SSE route streams
    them live); a column's cells arrive together — one answer() per question."""
    workers = _clamp_workers(max_workers)
    if not docs or not columns:
        return
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(evaluate_column, matter, docs, c, db_path, top_k)
                for c in columns]
        for fut in as_completed(futs):
            for cell in fut.result():
                yield cell
