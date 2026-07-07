"""M2-8 run harness — pose all 72 golden questions through the M2 pipeline and
capture raw results. This is the RUN mechanism (a loop), NOT a pass/fail scorer;
grading is manual (TEST_PLAN §5)."""
import sys, json, time, os
sys.path.insert(0, '.')
from answering import answer

REPO = ".."
manifest = {}
with open(f"{REPO}/eval/golden_manifest.jsonl") as f:
    for line in f:
        if line.strip():
            r = json.loads(line); manifest[r["fact_id"]] = r
with open(f"{REPO}/eval/golden_questions.jsonl") as f:
    questions = [json.loads(l) for l in f if l.strip()]

os.makedirs(f"{REPO}/eval/results", exist_ok=True)
out_path = f"{REPO}/eval/results/run-2026-07-07-p02-numctx.jsonl"
print("PID", os.getpid(), "writing", out_path, flush=True)
with open(out_path, "w") as out:
    for q in questions:
        fid = q["fact_id"]; rec = manifest[fid]
        present = not rec["expected_absent_topics"]
        matter = rec["matter_or_client"] if present else None  # NF -> search-all
        t0 = time.time()
        res = answer(q["question"], matter=matter)
        dt = round(time.time() - t0, 2)
        out.write(json.dumps({
            "fact_id": fid, "question": q["question"], "matter": matter,
            "answer_text": res["answer_text"], "citations": res["citations"],
            "grounding_chunks": res["grounding_chunks"],
            "rejected_claims": res["rejected_claims"], "latency_s": dt,
        }) + "\n")
        out.flush()
        print(fid, dt, "s", flush=True)
print("DONE", flush=True)
