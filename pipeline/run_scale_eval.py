"""Move 1a (D-69) — the SCALE retrieval eval: per-query-class recall on .lancedb_scale.

Phase A (this script, no LLM): for every question, does the GOLD chunk (gold filename +
page) appear in the top-5 / top-50 candidates, per retrieval config:

    dense          retrieve(top_k=5)                  — production today
    dense+rr       retrieve(rerank=True, candidate_k=50)
    hybrid         retrieve(hybrid=True)              — raw-question FTS arm
    hybrid+rr      hybrid candidates=50, then the cross-encoder reranker to 5

Questions: eval/scale_questions.jsonl (50 stratified: identifier / statute-cite /
party-name / defined-term / paraphrase / cross-doc / hard-negative, each in a LARGE
matter with same-genre distractors) + the 63 golden present-fact questions re-asked
against the scale store (their matters stay original-size; they test store-level
behavior and no-regression). Refusal-rate at the ANSWER level is Phase B (run after a
config choice, with the LLM).

Emits a per-class table (stdout + returned dict). Results are recorded honestly in
eval/SCALE_EVAL.md with the store recipe and date. Loopback only.
"""

import json
from collections import defaultdict
from pathlib import Path

from retrieval import retrieve

PIPELINE_DIR = Path(__file__).resolve().parent
REPO_ROOT = PIPELINE_DIR.parent
SCALE_DB = PIPELINE_DIR / ".lancedb_scale"
SCALE_QUESTIONS = REPO_ROOT / "eval" / "scale_questions.jsonl"
GOLDEN_MANIFEST = REPO_ROOT / "eval" / "golden_manifest.jsonl"
GOLDEN_QUESTIONS = REPO_ROOT / "eval" / "golden_questions.jsonl"

CONFIGS = ("dense", "dense+rr", "hybrid", "hybrid+rr")


def _load_questions():
    qs = [json.loads(l) for l in SCALE_QUESTIONS.read_text().splitlines() if l.strip()]
    manifest = {json.loads(l)["fact_id"]: json.loads(l)
                for l in GOLDEN_MANIFEST.read_text().splitlines() if l.strip()}
    for line in GOLDEN_QUESTIONS.read_text().splitlines():
        if not line.strip():
            continue
        g = json.loads(line)
        m = manifest[g["fact_id"]]
        if m["expected_absent_topics"]:
            continue  # NF questions are answer-level (Phase B)
        qs.append({"qid": g["fact_id"], "class": "golden",
                   "question": g["question"], "matter": m["matter_or_client"],
                   "gold_filename": m["filename"], "gold_page": m["page_number"]})
    return qs


def _hit(rows, q, k):
    return any(r["source_filename"] == q["gold_filename"]
               and int(r["page_number"]) == int(q["gold_page"]) for r in rows[:k])


def _candidates(q, config, k):
    kw = dict(matter=q["matter"], db_path=str(SCALE_DB))
    if config == "dense":
        return retrieve(q["question"], top_k=k, **kw)
    if config == "dense+rr":
        return retrieve(q["question"], top_k=k, rerank=True, candidate_k=50, **kw)
    if config == "hybrid":
        return retrieve(q["question"], top_k=k, candidate_k=50, hybrid=True, **kw)
    if config == "hybrid+rr":
        cands = retrieve(q["question"], top_k=50, candidate_k=50, hybrid=True, **kw)
        from reranker import rerank as _rr
        return _rr(q["question"], cands, top_k=k)
    raise ValueError(config)


def main():
    questions = _load_questions()
    print(f"{len(questions)} questions over {SCALE_DB.name}", flush=True)
    hits = {c: defaultdict(lambda: [0, 0, 0]) for c in CONFIGS}  # class -> [n, hit5, hit50]

    for i, q in enumerate(questions, 1):
        for config in CONFIGS:
            rows = _candidates(q, config, 50 if config in ("dense", "hybrid") else 5)
            rec = hits[config][q["class"]]
            rec[0] += 1
            rec[1] += _hit(rows, q, 5)
            # top-50 pool only meaningful pre-rerank; for rr configs reuse their 5
            rec[2] += _hit(rows, q, 50 if config in ("dense", "hybrid") else 5)
        if i % 20 == 0:
            print(f"  {i}/{len(questions)}", flush=True)

    classes = sorted({q["class"] for q in questions})
    print(f"\n{'class':<15}" + "".join(f"{c:>12}" for c in CONFIGS) + "   (recall@5)")
    out = {}
    for cls in classes:
        row = []
        for config in CONFIGS:
            n, h5, _ = hits[config][cls]
            row.append(h5 / n if n else 0.0)
        out[cls] = dict(zip(CONFIGS, row))
        print(f"{cls:<15}" + "".join(f"{r:>11.0%} " for r in row))
    print(f"\n{'class':<15}{'dense@50':>12}{'hybrid@50':>12}   (candidate-pool recall)")
    for cls in classes:
        n, _, d50 = hits["dense"][cls]
        _, _, h50 = hits["hybrid"][cls]
        print(f"{cls:<15}{d50 / n:>11.0%} {h50 / n:>11.0%}")
    return out


if __name__ == "__main__":
    main()
