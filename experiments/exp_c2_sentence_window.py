"""C2 — sentence-window retrieval prototype + measurement (kotaemon pattern).

Idea: retrieve tight chunks for precision, but feed the LLM a narrower sentence WINDOW
around the matched region (smaller context -> better precision + lower latency), while
still containing the answer span. This measures, READ-ONLY against the baseline (.lancedb),
how much smaller a sentence-window is than the full retrieved chunk while still containing
the golden span. No mutation, no re-embed, no re-index ([GATE]).

Run: pipeline/.venv/bin/python experiments/exp_c2_sentence_window.py
"""

import json
import re
import sys
from pathlib import Path

PIPELINE_DIR = Path(__file__).resolve().parent.parent / "pipeline"
REPO_ROOT = PIPELINE_DIR.parent
sys.path.insert(0, str(PIPELINE_DIR))

from retrieval import retrieve  # noqa: E402

MANIFEST = REPO_ROOT / "eval" / "golden_manifest.jsonl"
QUESTIONS = REPO_ROOT / "eval" / "golden_questions.jsonl"
_SENT = re.compile(r"(?<=[.!?])\s+")


def sentence_window(text, needle, radius=1):
    """Return the sentence containing ``needle`` plus ``radius`` neighbors each side. If the
    needle isn't found, return the full text (fail-open — never drops the answer)."""
    sentences = _SENT.split(text)
    nd = "".join(needle.lower().split())
    hit = None
    for i, s in enumerate(sentences):
        if nd in "".join(s.lower().split()):
            hit = i
            break
    if hit is None:
        return text
    lo, hi = max(0, hit - radius), min(len(sentences), hit + radius + 1)
    return " ".join(sentences[lo:hi])


def _load(path):
    return [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]


def measure_one(question, matter, span, radius=1):
    rows = retrieve(question, matter=matter, top_k=5)
    nd = "".join(span.lower().split())
    chunk = next((r for r in rows
                  if nd[:24] in "".join((r.get("text") or "").lower().split())), None)
    if chunk is None:
        return None
    window = sentence_window(chunk["text"], span, radius=radius)
    return {
        "chunk_chars": len(chunk["text"]),
        "window_chars": len(window),
        "window_has_span": nd in "".join(window.lower().split()),
        "reduction_pct": round(100 * (1 - len(window) / max(1, len(chunk["text"]))), 1),
    }


def run(radius=1):
    manifest = {m["fact_id"]: m for m in _load(MANIFEST)}
    questions = {q["fact_id"]: q["question"] for q in _load(QUESTIONS)}
    subset = ["F-001", "F-004", "F-005", "F-007", "F-009", "F-010", "F-046"]
    out = []
    for fid in subset:
        if fid not in manifest:
            continue
        m = manifest[fid]
        r = measure_one(questions[fid], m["matter_or_client"], m["verbatim_span"], radius)
        if r:
            out.append({"fact_id": fid, **r})
    return out


if __name__ == "__main__":
    rows = run()
    print("=== sentence-window vs full chunk (radius=1) ===")
    keep = 0
    for r in rows:
        print(f"  {r['fact_id']}: chunk={r['chunk_chars']}c  window={r['window_chars']}c  "
              f"-{r['reduction_pct']}%  has_span={r['window_has_span']}")
        keep += 1 if r["window_has_span"] else 0
    if rows:
        avg = sum(r["reduction_pct"] for r in rows) / len(rows)
        print(f"\navg context reduction: {avg:.1f}%  | span retained: {keep}/{len(rows)}")
