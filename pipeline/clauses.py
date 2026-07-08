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

# Advisory text for an absent clause. NOT a citation, NOT legal advice — a plain
# statement that the standard clause was not located in the matter's documents.
MISSING_ADVISORY = "Not located in the documents."

_FIELDS = ("id", "name", "category", "question", "doc_types")


def load_taxonomy(path=None):
    """Return the list of clause entries from the taxonomy JSON (default: the tracked
    `data/clause_taxonomy.json`). Each entry is ``{id, name, category, question,
    doc_types}``; the file's ``_provenance`` header is metadata, not a clause."""
    import json
    doc = json.loads(Path(path or DEFAULT_TAXONOMY).read_text(encoding="utf-8"))
    return list(doc["clauses"])


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
    clause_list = taxonomy if taxonomy is not None else load_taxonomy(taxonomy_path)

    target_filename = None
    if doc_id is not None:
        import catalog
        doc = catalog.get_document(doc_id, db_path=catalog_db) if catalog_db \
            else catalog.get_document(doc_id)
        if not doc:
            raise ValueError(f"unknown document id: {doc_id!r}")
        if doc.get("matter_slug") not in (None, matter):
            raise ValueError(f"document {doc_id} is not in matter {matter!r}")
        target_filename = doc["filename"]

    results = []
    for clause in clause_list:
        try:
            res = answer(clause["question"], matter=matter, top_k=top_k, db_path=db_path)
        except ValueError:
            # matter has no indexed chunks (e.g. empty KB) -> treat every clause as a
            # clean refusal: potentially missing, never a fabricated citation.
            res = {"answer_text": REFUSAL, "citations": [], "rejected_claims": [],
                   "grounding_chunks": []}
        results.append(_classify(clause, res, target_filename))

    summary = {"found": 0, "potentially_missing": 0, "not_confirmed": 0,
               "total": len(results)}
    for r in results:
        summary[r["status"]] += 1

    return {"matter": matter, "doc_id": doc_id, "results": results, "summary": summary}
