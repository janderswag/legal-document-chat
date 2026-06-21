"""C1 — measure top-k×N-before-rerank vs the current dense top-k=5, on the F-026 recall
miss and a present-fact aggregate. READ-ONLY against the eval baseline (.lancedb) — no
mutation, no re-embed, no M2-8 re-run (those are [GATE]). Reports rank of the correct
chunk; whether F-026's page-1 caption chunk is recovered.

Run: pipeline/.venv/bin/python experiments/exp_c1_topk_rerank.py
"""

import json
import sys
from pathlib import Path

PIPELINE_DIR = Path(__file__).resolve().parent.parent / "pipeline"
REPO_ROOT = PIPELINE_DIR.parent
sys.path.insert(0, str(PIPELINE_DIR))

from retrieval import retrieve  # noqa: E402

MANIFEST = REPO_ROOT / "eval" / "golden_manifest.jsonl"
QUESTIONS = REPO_ROOT / "eval" / "golden_questions.jsonl"


def _load(path):
    return [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]


def rank_of_correct(rows, filename, page, needle):
    """1-based rank of the first row matching (filename, page) whose text contains
    ``needle`` (normalized), or None if absent. Pure — unit-tested separately."""
    nd = "".join(needle.lower().split())
    for i, r in enumerate(rows, 1):
        if r.get("source_filename") == filename and r.get("page_number") == page:
            if nd in "".join((r.get("text") or "").lower().split()):
                return i
    return None


def measure_one(question, matter, filename, page, needle, top_k=5, candidate_k=20):
    """Rank of the correct chunk under (a) current dense top_k and (b) top-k×N + rerank."""
    dense = retrieve(question, matter=matter, top_k=top_k)
    reranked = retrieve(question, matter=matter, top_k=top_k, rerank=True,
                        candidate_k=candidate_k)
    return {
        "question": question,
        "dense_rank": rank_of_correct(dense, filename, page, needle),
        "reranked_rank": rank_of_correct(reranked, filename, page, needle),
        "top_k": top_k, "candidate_k": candidate_k,
    }


def run():
    manifest = {m["fact_id"]: m for m in _load(MANIFEST)}
    questions = {q["fact_id"]: q["question"] for q in _load(QUESTIONS)}

    # 1) the F-026 recall miss specifically
    f = manifest["F-026"]
    f026 = measure_one(questions["F-026"], f["matter_or_client"], f["filename"],
                       f["page_number"], "Sabrina Voss")

    # 2) present-fact aggregate (a representative subset across matters)
    subset = ["F-001", "F-004", "F-007", "F-009", "F-010", "F-026", "F-042", "F-046"]
    agg = []
    for fid in subset:
        if fid not in manifest:
            continue
        m = manifest[fid]
        agg.append(measure_one(questions[fid], m["matter_or_client"], m["filename"],
                               m["page_number"], m["verbatim_span"].split()[0]))
    return {"f026": f026, "aggregate": agg}


if __name__ == "__main__":
    res = run()
    print("=== F-026 (page-1 caption recall miss) ===")
    print(json.dumps(res["f026"], indent=2))
    print("\n=== present-fact aggregate (dense_rank -> reranked_rank) ===")
    dn = rn = 0
    for r in res["aggregate"]:
        print(f"  dense={r['dense_rank']}  reranked={r['reranked_rank']}  | {r['question'][:60]}")
        dn += 1 if r["dense_rank"] == 1 else 0
        rn += 1 if r["reranked_rank"] == 1 else 0
    print(f"\nrank@1: dense {dn}/{len(res['aggregate'])}  reranked {rn}/{len(res['aggregate'])}")
    f = res["f026"]
    verdict = ("RECOVERED" if (f["reranked_rank"] and not f["dense_rank"])
               else "no change" if f["reranked_rank"] == f["dense_rank"]
               else "changed")
    print(f"\nF-026 top-k×N+rerank verdict: {verdict} "
          f"(dense={f['dense_rank']} -> reranked={f['reranked_rank']})")
