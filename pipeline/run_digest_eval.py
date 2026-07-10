"""G-DIG (M-2 gate): extraction recall against a hand-labeled fact inventory.
Runs the REAL extractor over the eval store, gates mechanically, and scores
recall per fact type. Precision is enforced by construction (the write gate);
value correctness is spot-graded per extractor_version, per the design spec.
Usage:
  python3 run_digest_eval.py --inventory ../eval/digest_inventory.json \
      --db ../eval/.lancedb_eval
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import digest  # noqa: E402
import verifier  # noqa: E402


def _norm(s):
    return verifier._norm_map(s)[0]


def score(inventory, extracted):
    """extracted: {(doc, fact_type): [span, ...]}. An inventory entry is a hit when
    its normalized span_contains is a substring of any extracted span's norm."""
    recall = defaultdict(lambda: {"hit": 0, "total": 0})
    for entry in inventory:
        t = entry["fact_type"]
        recall[t]["total"] += 1
        needle = _norm(entry["span_contains"])
        spans = extracted.get((entry["doc"], t), [])
        if any(needle in _norm(s) for s in spans):
            recall[t]["hit"] += 1
    return dict(recall)


def meets_targets(recall, targets):
    for t, floor in targets.items():
        r = recall.get(t, {"hit": 0, "total": 0})
        if r["total"] and r["hit"] / r["total"] < floor:
            return False
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inventory", required=True)
    ap.add_argument("--db", required=True)
    args = ap.parse_args()

    manifest = json.loads(Path(args.inventory).read_text())
    inventory, targets = manifest["facts"], manifest.get("targets", {})
    extracted, drops = defaultdict(list), 0
    for key in sorted({(e["doc"], e["matter"]) for e in inventory}):
        doc, matter = key
        pages = digest.pages_from_store(args.db, doc, matter)
        for i, group in enumerate(digest._groups(pages)):
            text = "\n\n".join(f"=== page {p['page_number']} ===\n{p['page_text']}"
                               for p in group)
            raw = digest._extract_call(text)
            if raw is None:
                raw = digest._extract_call(text)   # one retry
            if raw is None:
                print(f"G-DIG ABORT: extraction call failed twice for {doc} group {i} "
                      "— recall would be understated")
                sys.exit(2)
            ok, bad = digest.gate_facts(raw, group, doc_id=0)
            drops += bad
            for f in ok:
                extracted[(doc, f["fact_type"])].append(f["span"])

    recall = score(inventory, extracted)
    print(f"G-DIG — extractor {digest.EXTRACTOR_VERSION} — dropped {drops} spans at the gate")
    for t in sorted(recall):
        r = recall[t]
        pct = (r["hit"] / r["total"] * 100) if r["total"] else 0
        print(f"  {t:14s} {r['hit']}/{r['total']}  ({pct:.0f}%)  target "
              f"{targets.get(t, 0) * 100:.0f}%")
    for t in targets:
        if not recall.get(t, {"total": 0})["total"]:
            print(f"WARNING: no inventory entries for {t} — target not enforced")
    ok = meets_targets(recall, targets)
    print("G-DIG:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
