"""T-CLAUSE — Contract Review clause checklist over the existing answer() + verifier.

Pure data + orchestration (no new install, D-49/D-51): for each clause in a curated,
CUAD-informed taxonomy (`data/clause_taxonomy.json`), pose our authored natural-language
question to the existing grounded-answer path `answer(question, matter)` and classify the
result against the SAME mechanical span-verification (D-19) + chunk-derived (D-38) rules
the rest of the pipeline uses. This adds NO new retrieval, answering, or verification
behavior — it is a thin loop that consumes answer()'s already-verified output.

Classification (the never-false-accept invariant is non-negotiable):

- ``found`` — answer() returned **>=1 span-verified, chunk-derived citation**
  (``result["citations"]`` is non-empty; those are the verifier's output, page+span
  mechanically checked). Only then is a value + citation(s) reported.
- ``potentially_missing`` — answer() returned the exact D-30 refusal. Advisory, **never
  citable**: this is the "Missing Terms" signal. We never fabricate a citation for an
  absence and never phrase it as legal advice — only "not located in the documents".
- ``not_confirmed`` — prose was returned but the verifier rejected every asserted span
  (``citations`` empty, not a refusal). Surfaced honestly, **never** as found, with ZERO
  citations — so an unverified model assertion can never reach the attorney as grounded.

Scope: locate/summarize only (CLAUDE.md product boundary) — no drafting, advice, or
actions. Read-only over whichever store ``db_path`` selects; never re-embeds (D-31).
"""

from pathlib import Path

from answering import REFUSAL, answer  # answer() is monkeypatched in unit tests

import apppaths

DEFAULT_TAXONOMY = apppaths.assets_root() / "data" / "clause_taxonomy.json"

# Advisory text for a not-located clause. NOT a citation, NOT legal advice — a
# plain statement of what retrieval actually did: the clause was not located in
# the passages checked (never an absence claim; council 2026-07-11).
MISSING_ADVISORY = "Not located in the passages checked."

_FIELDS = ("id", "name", "category", "question", "doc_types")


def load_taxonomy(path=None):
    """Return the list of clause entries from the taxonomy JSON (default: the tracked
    `data/clause_taxonomy.json`). Each entry is ``{id, name, category, question,
    doc_types}``; the file's ``_provenance`` header is metadata, not a clause."""
    import json
    doc = json.loads(Path(path or DEFAULT_TAXONOMY).read_text(encoding="utf-8"))
    return list(doc["clauses"])


def taxonomy_version(path=None):
    """The taxonomy's ``_provenance.version`` (persisted-run staleness key)."""
    import json
    doc = json.loads(Path(path or DEFAULT_TAXONOMY).read_text(encoding="utf-8"))
    return str((doc.get("_provenance") or {}).get("version", ""))


def plan_clauses(taxonomy=None, taxonomy_path=None, doc_types=None,
                 extra_questions=None):
    """The clause list a review will actually run, in run order.

    doc_types — attorney-designated document type(s) (council 2026-07-11 Move 2d:
    the catalog never classifies documents into contract/lease/nda/services_agreement,
    so the TYPE IS THE ATTORNEY'S CALL, never guessed). A clause survives the filter
    when any of its ``doc_types`` intersects the designated set; an empty/None filter
    keeps everything.
    extra_questions — the attorney's own questions (owner decision #3, minimal
    add-your-own-question row). Same shape as grid.resolve_columns custom entries;
    always included regardless of the doc_types filter.
    """
    clause_list = list(taxonomy) if taxonomy is not None else load_taxonomy(taxonomy_path)
    if doc_types:
        wanted = set(doc_types)
        clause_list = [c for c in clause_list
                       if wanted & set(c.get("doc_types") or [])]
    for i, q in enumerate(extra_questions or []):
        text = (q or "").strip() if isinstance(q, str) else (q.get("question") or "").strip()
        if not text:
            continue
        clause_list.append({"id": f"custom-{i + 1}", "name": text[:48],
                            "category": "Custom", "question": text,
                            "doc_types": None})
    return clause_list


def _classify(clause, result, target_filename=None):
    """Classify one answer() ``result`` for one ``clause`` into the checklist row.

    target_filename (set when scoping to a single doc_id): only verified citations on
    that file count toward "found"; citations on other documents in the matter are
    dropped, so a clause present elsewhere in the matter but not in THIS document does
    not falsely read as found here.
    """
    answer_text = (result.get("answer_text") or "")
    citations = list(result.get("citations") or [])
    rejected = list(result.get("rejected_claims") or [])

    if target_filename is not None:
        citations = [c for c in citations if c.get("filename") == target_filename]

    row = {k: clause.get(k) for k in _FIELDS}

    if citations:
        # FOUND — at least one span-verified, chunk-derived citation (D-19/D-38).
        row.update(status="found", value=answer_text, citations=citations,
                   rejected_claims=rejected)
    elif REFUSAL in answer_text:
        # POTENTIALLY MISSING — the exact D-30 refusal. Advisory, non-citable.
        row.update(status="potentially_missing", value=MISSING_ADVISORY, citations=[],
                   rejected_claims=[])
    else:
        # NOT CONFIRMED — prose returned but the verifier rejected every span. Never
        # found; surface no citation (never-false-accept).
        row.update(status="not_confirmed", value=answer_text, citations=[],
                   rejected_claims=rejected)
    return row


def extract_clauses(matter, doc_id=None, taxonomy=None, taxonomy_path=None,
                    db_path=None, top_k=5, catalog_db=None):
    """Run the clause checklist over ``matter`` (read-only) and return a structured result.

    matter      — the matter scope passed straight to answer() (D-35 hard pre-filter;
                  validated against the store allowlist inside retrieve()).
    doc_id      — optional: narrow the checklist to a single document. Resolved to a
                  filename via the catalog; only verified citations on that file count.
    taxonomy    — an explicit list of clause entries (tests pass a small one); else
    taxonomy_path / default `data/clause_taxonomy.json` is loaded.
    db_path     — which LanceDB store answer() reads (e.g. the KB store for the UI, or
                  the eval baseline for the core test). Read-only; never re-embedded.

    Returns ``{matter, doc_id, results:[row...], summary:{...}}`` where each row is
    ``{id,name,category,question,doc_types,status,value,citations,rejected_claims}``.
    """
    results = list(iter_clauses(matter, doc_id=doc_id, taxonomy=taxonomy,
                                taxonomy_path=taxonomy_path, db_path=db_path,
                                top_k=top_k, catalog_db=catalog_db))
    return {"matter": matter, "doc_id": doc_id, "results": results,
            "summary": summarize(results)}


def resolve_target_filename(matter, doc_id, catalog_db=None):
    """doc_id -> filename for single-document scoping (validated to the matter)."""
    import catalog
    doc = catalog.get_document(doc_id, db_path=catalog_db) if catalog_db \
        else catalog.get_document(doc_id)
    if not doc:
        raise ValueError(f"unknown document id: {doc_id!r}")
    if doc.get("matter_slug") not in (None, matter):
        raise ValueError(f"document {doc_id} is not in matter {matter!r}")
    return doc["filename"]


def iter_clauses(matter, doc_id=None, taxonomy=None, taxonomy_path=None,
                 db_path=None, top_k=5, catalog_db=None, doc_types=None,
                 extra_questions=None):
    """Yield each checklist row as it completes, in plan order (the job runner and
    its SSE stream consume this). Same classification as extract_clauses — this is
    the same loop, streamed."""
    clause_list = plan_clauses(taxonomy=taxonomy, taxonomy_path=taxonomy_path,
                               doc_types=doc_types, extra_questions=extra_questions)

    target_filename = None
    if doc_id is not None:
        target_filename = resolve_target_filename(matter, doc_id, catalog_db=catalog_db)

    for clause in clause_list:
        try:
            # G-SCOPE (D3): a single-document review scopes RETRIEVAL to that
            # file; the D-52 citation post-filter below stays as belt-and-braces
            res = answer(clause["question"], matter=matter, top_k=top_k, db_path=db_path,
                         source_filename=target_filename)
        except ValueError:
            # matter has no indexed chunks (e.g. empty KB) -> treat every clause as a
            # clean refusal: potentially missing, never a fabricated citation.
            # A SCOPED review is different: "document not in the index" (still
            # processing / OCR-failed) must fail LOUD — swallowing it would
            # persist a complete all-"Not located" review of a document whose
            # passages were never checked (adversarial review, D3).
            if target_filename is not None:
                raise
            res = {"answer_text": REFUSAL, "citations": [], "rejected_claims": [],
                   "grounding_chunks": []}
        yield _classify(clause, res, target_filename)


def summarize(results):
    summary = {"found": 0, "potentially_missing": 0, "not_confirmed": 0,
               "total": len(results)}
    for r in results:
        summary[r["status"]] += 1
    return summary
