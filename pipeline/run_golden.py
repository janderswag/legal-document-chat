"""Golden-set run harness — pose all 72 golden questions through the pipeline and write
raw results to a REQUIRED, explicit output tag (never a hardcoded date: an earlier
copy-and-sed workflow silently overwrote a historical baseline file).

    ./.venv/bin/python run_golden.py <tag>
    # -> ../eval/results/run-<tag>.jsonl   (refuses to overwrite an existing file)

This is the RUN mechanism (a loop), NOT a scorer; grading is per TEST_PLAN §5/§6.
Supersedes the run_m28.py copy-pattern for new runs.
"""
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from answering import answer  # noqa: E402

REPO = Path(__file__).resolve().parent.parent


def main(tag):
    out_path = REPO / "eval" / "results" / f"run-{tag}.jsonl"
    if out_path.exists():
        raise SystemExit(f"refusing to overwrite existing results: {out_path}")
    manifest = {}
    with open(REPO / "eval" / "golden_manifest.jsonl", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                r = json.loads(line)
                manifest[r["fact_id"]] = r
    with open(REPO / "eval" / "golden_questions.jsonl", encoding="utf-8") as f:
        questions = [json.loads(l) for l in f if l.strip()]

    out_path.parent.mkdir(parents=True, exist_ok=True)
    print("PID", os.getpid(), "writing", out_path, flush=True)
    with open(out_path, "w", encoding="utf-8") as out:
        for q in questions:
            rec = manifest[q["fact_id"]]
            present = not rec["expected_absent_topics"]
            matter = rec["matter_or_client"] if present else None  # NF -> search-all
            t0 = time.time()
            res = answer(q["question"], matter=matter)
            dt = round(time.time() - t0, 2)
            out.write(json.dumps({
                "fact_id": q["fact_id"], "question": q["question"], "matter": matter,
                "answer_text": res["answer_text"], "citations": res["citations"],
                "grounding_chunks": res["grounding_chunks"],
                "rejected_claims": res["rejected_claims"], "latency_s": dt,
            }) + "\n")
            out.flush()
            print(q["fact_id"], dt, "s", flush=True)
    print("DONE", flush=True)


if __name__ == "__main__":
    if len(sys.argv) != 2 or not sys.argv[1].strip():
        raise SystemExit("usage: run_golden.py <output-tag>   (e.g. 2026-07-07-m0a)")
    main(sys.argv[1].strip())
