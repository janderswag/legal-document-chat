"""Task 5 — hybrid-vs-dense lift, a READING AID (objective rank lookups, NOT a pass/fail
scorer; manual interpretation per D-36 honesty). Measures rank@1 and MRR over the 63
present-fact golden questions for dense-only vs RRF hybrid retrieval.

To avoid writing an FTS index into the LIVE .lancedb (which must stay byte-identical for
M2-8), it builds a throwaway .lancedb_hyb from the same chunks and measures there."""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from embed_store import build_store
from retrieval import retrieve

PIPELINE_DIR = Path(__file__).resolve().parent
REPO_ROOT = PIPELINE_DIR.parent
CHUNKS = REPO_ROOT / "documents" / "synthetic_corpus" / "chunks" / "chunks.jsonl"
MANIFEST = REPO_ROOT / "eval" / "golden_manifest.jsonl"
QUESTIONS = REPO_ROOT / "eval" / "golden_questions.jsonl"
HYB_DB = PIPELINE_DIR / ".lancedb_hyb"


def _norm(t):
    return re.sub(r"\s+", " ", re.sub(r"-\n", "-", t)).strip().lower()


def _rank_of_correct(rows, fact):
    span = _norm(fact["verbatim_span"])
    for i, r in enumerate(rows):
        if (r["source_filename"] == fact["filename"]
                and r["page_number"] == fact["page_number"]
                and span in _norm(r["text"])):
            return i + 1  # 1-based
    return 0  # not found in top_k


def main():
    if not HYB_DB.exists():
        build_store(CHUNKS, db_path=str(HYB_DB))  # loopback bge-m3 embed
    manifest = {json.loads(l)["fact_id"]: json.loads(l)
                for l in MANIFEST.read_text().splitlines() if l.strip()}
    questions = {json.loads(l)["fact_id"]: json.loads(l)["question"]
                 for l in QUESTIONS.read_text().splitlines() if l.strip()}
    facts = [m for m in manifest.values() if not m["expected_absent_topics"]]

    agg = {"dense": {"r1": 0, "mrr": 0.0}, "hybrid": {"r1": 0, "mrr": 0.0}}
    n = 0
    for f in facts:
        q = questions[f["fact_id"]]
        matter = f["matter_or_client"]
        for mode, hyb in (("dense", False), ("hybrid", True)):
            rows = retrieve(q, matter=matter, db_path=str(HYB_DB), top_k=5, hybrid=hyb)
            rank = _rank_of_correct(rows, f)
            agg[mode]["r1"] += 1 if rank == 1 else 0
            agg[mode]["mrr"] += (1.0 / rank) if rank else 0.0
        n += 1

    print(f"present-fact questions measured: {n}")
    for mode in ("dense", "hybrid"):
        print(f"  {mode:6s}  rank@1 = {agg[mode]['r1']}/{n} = {100*agg[mode]['r1']/n:.1f}%"
              f"   MRR = {agg[mode]['mrr']/n:.4f}")
    d1 = agg["hybrid"]["r1"] - agg["dense"]["r1"]
    dm = (agg["hybrid"]["mrr"] - agg["dense"]["mrr"]) / n
    print(f"  delta  rank@1 {d1:+d}   MRR {dm:+.4f}")
    return agg, n


if __name__ == "__main__":
    main()
