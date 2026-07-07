"""Task 6 — first-token latency (TTFT) harness (G-LAT).

measure(question, matter, db_path) assembles the SAME grounded prompt answer() uses,
then streams qwen3:14b to record TTFT (request-send -> first content token) and total.
answer() itself is untouched (M2-7 parity); this is a read-only side channel.

The harness runs the 63 present-fact golden questions and writes a git-ignored
eval/results/latency-<date>.jsonl, reporting TTFT mean/median/p95 honestly vs the
CE_PLAN <3s first-token target. Loopback Ollama only.
"""

import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from answering import KEEP_ALIVE, NUM_CTX, SYSTEM_PROMPT, _chat_stream_ttft  # noqa: E402
from retrieval import retrieve  # noqa: E402

PIPELINE_DIR = Path(__file__).resolve().parent
REPO_ROOT = PIPELINE_DIR.parent
MANIFEST = REPO_ROOT / "eval" / "golden_manifest.jsonl"
QUESTIONS = REPO_ROOT / "eval" / "golden_questions.jsonl"

# Latency knobs — PRODUCTION PARITY (P0.2): the same think=False + keep_alive + num_ctx
# the production _post_chat/_stream_tokens send, so the numbers reflect the shipped path.
_KEEP_ALIVE = KEEP_ALIVE
_NUM_CTX = NUM_CTX


def _assemble_messages(question, matter, top_k, db_path):
    """Mirror answer()'s grounded prompt assembly (kept in sync; answer() is unchanged)."""
    chunks = retrieve(question, matter=matter, top_k=top_k, db_path=db_path, rerank=False)
    blocks = [
        f"[chunk: C{i} | document: {c['source_filename']} | page: {c['page_number']} "
        f"| section: {c['section']}]\n{c['text']}"
        for i, c in enumerate(chunks, 1)
    ]
    user = (
        "<context>\n" + "\n\n".join(blocks) + "\n</context>\n\n"
        "Cite each factual claim with the tag [document: <filename>, page: <page_number>, "
        "chunk: <chunk_id>, span: \"<verbatim quote>\"] using the chunk labels shown above.\n\n"
        "User question:\n" + question
    )
    return [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}]


def measure(question, matter=None, top_k=5, db_path=None):
    """Return {"ttft_s", "total_s"} for one grounded question (streaming, no-think, warm)."""
    messages = _assemble_messages(question, matter, top_k, db_path)
    _text, ttft, total = _chat_stream_ttft(messages, think=False, keep_alive=_KEEP_ALIVE,
                                           num_ctx=_NUM_CTX)
    return {"ttft_s": round(ttft, 4), "total_s": round(total, 4)}


def main(date_tag="2026-07-07"):
    manifest = {json.loads(l)["fact_id"]: json.loads(l)
                for l in MANIFEST.read_text().splitlines() if l.strip()}
    questions = {json.loads(l)["fact_id"]: json.loads(l)["question"]
                 for l in QUESTIONS.read_text().splitlines() if l.strip()}
    facts = [m for m in manifest.values() if not m["expected_absent_topics"]]

    out_path = REPO_ROOT / "eval" / "results" / f"latency-{date_tag}.jsonl"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    ttfts = []
    with open(out_path, "w", encoding="utf-8") as f:
        for m in facts:
            r = measure(questions[m["fact_id"]], matter=m["matter_or_client"])
            r["fact_id"] = m["fact_id"]
            ttfts.append(r["ttft_s"])
            f.write(json.dumps(r) + "\n")
            f.flush()
            print(m["fact_id"], "ttft", r["ttft_s"], "total", r["total_s"], flush=True)

    ttfts.sort()
    p95 = ttfts[min(len(ttfts) - 1, int(round(0.95 * (len(ttfts) - 1))))]
    print(f"\nTTFT over {len(ttfts)} questions: mean={statistics.mean(ttfts):.2f}s "
          f"median={statistics.median(ttfts):.2f}s p95={p95:.2f}s "
          f"(<3s target: {'MET' if statistics.median(ttfts) < 3 else 'NOT met'})")
    return ttfts


if __name__ == "__main__":
    main()
