"""Move 1d (D-69) — rebuild the KB store on the new schema (one-time migration).

The 1d schema adds document_type/provenance/doc_date and the section-aware SAC
embedding format; existing .lancedb_kb tables predate it. This script renames the old
store aside (never deletes client-visible data), then re-enqueues every cataloged
document through the normal serialized ingest worker so chunks are rebuilt with the
production chunker + new schema. Loopback embedding only; originals untouched.

    ./.venv/bin/python reingest_kb.py
"""

import time
from datetime import datetime
from pathlib import Path

import catalog
import ingest_worker
import routes_kb


def main():
    kb_db = Path(routes_kb.KB_DB)
    if kb_db.exists():
        aside = kb_db.with_name(kb_db.name + ".pre-1d-" + datetime.now().strftime("%Y%m%d%H%M%S"))
        kb_db.rename(aside)
        print(f"old store moved aside -> {aside.name} (delete manually once verified)")

    docs = catalog.list_documents()
    todo = [d for d in docs if Path(d["stored_path"]).is_file()]
    missing = [d for d in docs if not Path(d["stored_path"]).is_file()]
    for d in missing:
        print(f"SKIP (file missing): {d['filename']} [{d['matter_slug']}]")
    for d in todo:
        catalog.update_document(d["id"], "queued")
        ingest_worker.enqueue(d["id"], d["stored_path"], d["matter_slug"],
                              str(routes_kb.KB_DB), catalog.DEFAULT_DB)
    print(f"enqueued {len(todo)} documents; waiting for the worker...")

    deadline = time.time() + 3600 * 20  # scanned corpora can take many hours
    while time.time() < deadline:
        s = ingest_worker.status()
        if s["queue_depth"] == 0 and s["current"] is None:
            break
        print(f"  queue={s['queue_depth']} current={s['current']}", flush=True)
        time.sleep(5)

    final = catalog.list_documents()
    ready = sum(1 for d in final if d["status"] == "ready")
    other = [(d["filename"], d["status"]) for d in final
             if d["status"] not in ("ready",) and Path(d["stored_path"]).is_file()]
    print(f"done: {ready}/{len(todo)} ready; non-ready: {other or 'none'}")


if __name__ == "__main__":
    main()
