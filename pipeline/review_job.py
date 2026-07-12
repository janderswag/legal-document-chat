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

    # --- G-SCOPE (D5): absence verification -------------------------------------
    # Root cause of false "not located": matter-wide top-5 saturates with other
    # documents' chunks. Every potentially_missing row is re-asked scoped to
    # each candidate document until found or exhausted. A row upgrades to found
    # (span-verified citation) or earns the honest per-document claim. Single-
    # document reviews are already retrieval-scoped (D3) — no second pass.
    verify_stopped = None
    if doc_id is None:
        missing = [(i, r) for i, r in enumerate(results)
                   if r["status"] == "potentially_missing"]
        docs = catalog.list_documents(matter)
        for n, (idx, row) in enumerate(missing, 1):
            # the base review is COMPLETE at this point — a cancel or transient
            # failure during the (long) verify tail must never discard it; the
            # run persists with whatever rows were upgraded so far, honestly
            # marked (un-upgraded rows keep their weaker matter-wide language)
            if ctx.cancelled():
                verify_stopped = "cancelled"
                break
            # progress first: a row's fan-out is up to N serial model calls,
            # and the UI must not keep claiming "Checking clause M of M"
            ctx.emit("verify", {"n": n, "of": len(missing)})
            try:
                upgrade = _verify_absence(ctx, matter, row, docs)
            except jobs.JobCancelled:
                verify_stopped = "cancelled"
                break
            except Exception as e:                      # noqa: BLE001
                verify_stopped = f"{type(e).__name__}: {e}"
                break
            # NEVER mutate the emitted row dict: jobs._emit holds event dicts
            # by reference, so in-place upgrades would retroactively rewrite
            # the persisted "clause" event history (replay consistency) and
            # race a reconnecting client's mid-replay serialization
            upgraded = dict(row)
            upgraded.update(upgrade)
            results[idx] = upgraded
            ctx.emit("verify", {"row": upgraded, "n": n, "of": len(missing)})

    summary = clauses.summarize(results)
    summary["verified_absences"] = sum(
        1 for r in results if r.get("verified_scope") == "matter_documents")

    result = {
        "matter": matter, "doc_id": doc_id, "doc_types": doc_types,
        "results": results, "summary": summary,
        "docs_key": started_docs_key,
        "taxonomy_version": clauses.taxonomy_version(),
        "reviewed": catalog._now(),
    }
    if verify_stopped:
        result["verify_stopped"] = verify_stopped
    return result


def _verify_absence(ctx, matter, row, docs, top_k=5):
    """Scoped re-asks for one potentially_missing row, one document at a time.

    Returns the dict of row upgrades: found (with doc_id-enriched citations,
    verified_scope="document"), a verified absence (verified_scope=
    "matter_documents" with an honest count), or {} when nothing was checkable.
    A document whose scoped ask raises ValueError (no indexed chunks) is never
    counted as checked — the claim only covers checks that actually ran."""
    checked = 0
    for d in docs:
        if ctx.cancelled():
            raise jobs.JobCancelled()
        activity.mark_chat()   # still user-initiated foreground work (D-68)
        try:
            res = clauses.answer(row["question"], matter=matter, top_k=top_k,
                                 db_path=_kb_path(),
                                 source_filename=d["filename"])
        except ValueError:
            continue
        checked += 1
        cand = clauses._classify(row, res, target_filename=d["filename"])
        if cand["status"] == "found":
            for c in cand["citations"]:
                c["doc_id"] = d["id"]
            return {"status": "found", "value": cand["value"],
                    "citations": cand["citations"],
                    "rejected_claims": cand["rejected_claims"],
                    "verified_scope": "document"}
    total = len(docs)
    if not checked:
        return {}
    noun = "document" if checked == 1 else "documents"
    if checked == total:
        value = (f"Not located in {checked} {noun} "
                 "(every document checked individually).")
    else:
        value = (f"Not located in the {checked} {noun} that could be checked "
                 f"individually ({total - checked} could not be checked).")
    return {"status": "potentially_missing", "value": value, "citations": [],
            "rejected_claims": [], "verified_scope": "matter_documents",
            "docs_checked": checked}


jobs.register(KIND, run_review)
