"""Clause-review tenant of the job runner (council 2026-07-11 Move 2).

The Review tab's "Run review" submits here instead of blocking a request thread for
minutes. The tenant streams one event per clause (the UI fills skeleton rows live),
marks interactive activity so background ingest/digest yield the shared Ollama, polls
the cancel flag between clauses, and returns the full structured result — which the
runner persists, so a finished review reopens in zero seconds.

Staleness keying (council: persisted runs keyed matter + doc set + taxonomy version):
the result carries ``docs_key`` (hash of the matter's document ids+checksums at run
time) and ``taxonomy_version``; readers compare against the current values to say
"documents have changed since this review" honestly. Read-only over the KB store;
the answer path itself is untouched (engine frozen behind the 63/63 gate).
"""

import hashlib
import json

import activity
import catalog
import clauses
import jobs

KIND = "clause_review"

# The KB store path is owned by routes_kb (monkeypatchable in tests); resolved at
# run time so tests can swap it before the job executes.
KB_DB_PATH = None  # None -> routes_kb.KB_DB


def docs_key(matter, catalog_db=None):
    """Hash of the matter's (doc_id, checksum) set — flips when any document is
    added, replaced, or removed. Pure staleness signal, no document data."""
    docs = catalog.list_documents(matter, db_path=catalog_db) if catalog_db \
        else catalog.list_documents(matter)
    key = sorted((d["id"], d.get("checksum") or "") for d in docs)
    return hashlib.sha256(json.dumps(key).encode()).hexdigest()[:16]


def _kb_path():
    if KB_DB_PATH is not None:
        return str(KB_DB_PATH)
    import routes_kb
    return str(routes_kb.KB_DB)


def run_review(ctx):
    p = ctx.params or {}
    matter = p["matter"]
    doc_id = p.get("doc_id")
    doc_types = p.get("doc_types") or None
    extra_questions = p.get("questions") or None

    # Staleness key hashed BEFORE the run (review finding #3): a document added
    # mid-review was never seen by these clauses, so the finished run must
    # compare against the doc set the review actually started from.
    started_docs_key = docs_key(matter)

    plan = clauses.plan_clauses(doc_types=doc_types, extra_questions=extra_questions)
    ctx.emit("meta", {
        "matter": matter, "doc_id": doc_id, "doc_types": doc_types,
        "clauses": [{"id": c["id"], "name": c["name"], "category": c["category"],
                     "question": c["question"]} for c in plan],
    })

    # doc_id enrichment map for /kb/highlight (same post-step the blocking route
    # did; displayed page/span stay chunk-derived, never model-asserted).
    by_name = {d["filename"]: d["id"] for d in catalog.list_documents(matter)}

    results = []
    it = clauses.iter_clauses(matter, doc_id=doc_id, db_path=_kb_path(),
                              doc_types=doc_types, extra_questions=extra_questions)
    for _ in range(len(plan)):
        if ctx.cancelled():
            raise jobs.JobCancelled()
        activity.mark_chat()   # review is user-initiated foreground work (D-68)
        row = next(it, None)
        if row is None:
            break
        for c in row["citations"]:
            c["doc_id"] = by_name.get(c["filename"])
        results.append(row)
        ctx.emit("clause", row)

    return {
        "matter": matter, "doc_id": doc_id, "doc_types": doc_types,
        "results": results, "summary": clauses.summarize(results),
        "docs_key": started_docs_key,
        "taxonomy_version": clauses.taxonomy_version(),
        "reviewed": catalog._now(),
    }


jobs.register(KIND, run_review)
