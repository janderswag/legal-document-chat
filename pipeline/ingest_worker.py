"""Move 0b/0c (D-68) — serialized, instrumented KB ingest.

One dedicated daemon worker thread + an unbounded queue replaces the previous
BackgroundTasks-on-request-pool pattern, which ran up to 40 concurrent sync ingests on
the SAME anyio thread pool as every request handler — a bulk upload starved /chat for
hours, thrashed 40 parallel Docling/Tesseract parses, and raced LanceDB writers
(D-66 scale audit). Serializing ingest also ends the writer commit conflicts and gives
one natural place for progress state and store maintenance.

Uploads enqueue instantly (catalog status "queued"); the worker walks each job through
the existing kb_ingest lifecycle ("parsing" -> ready/needs_review/failed) with per-stage
timings logged, and runs ``table.optimize()`` every N ingests (the store previously
accumulated versions/fragments forever — measured 2 versions + 1 fragment per doc,
never compacted). Everything is loopback-local; no new dependencies.
"""

import logging
import queue
import threading
import time

import activity
import catalog
import digest
import kb_ingest
from embed_store import open_table

log = logging.getLogger("docuchat.ingest")

OPTIMIZE_EVERY = 50    # ingests between table.optimize() runs (measured ~0.1s each)

_QUEUE = queue.Queue()
_START_LOCK = threading.Lock()
_started = False
# Progress surface for the Hub UI (read-only snapshot via status()).
_state = {"current": None, "processed": 0}


def enqueue(doc_id, file_path, matter_slug, db_path, catalog_db=None):
    """Queue one document for ingest and return the queue depth (including this job).
    The catalog row should already be status='queued' (routes_kb sets it at upload)."""
    _ensure_worker()
    _QUEUE.put((doc_id, str(file_path), matter_slug, str(db_path), catalog_db))
    return _QUEUE.qsize()


def status():
    """Read-only progress snapshot: queue depth, the in-flight doc (id + stage), and a
    lifetime processed count. No document content."""
    cur = _state["current"]
    return {"queue_depth": _QUEUE.qsize(),
            "current": dict(cur) if cur else None,
            "processed": _state["processed"]}


def _ensure_worker():
    global _started
    with _START_LOCK:
        if _started:
            return
        threading.Thread(target=_loop, name="kb-ingest-worker", daemon=True).start()
        _started = True


def _loop():
    while True:
        job = _QUEUE.get()
        try:
            # Interactive priority: an in-flight/recent chat outranks background
            # indexing (embedding batches measurably slow generation on shared local
            # compute). Defer the next job until the chat window goes quiet.
            while activity.chat_recent():
                _state["current"] = {"doc_id": job[0], "stage": "waiting-for-chat"}
                time.sleep(0.5)
            _run(*job)
        except Exception:
            # ingest_document sets catalog status itself on known failures; this guard
            # is for unexpected crashes — fail loud in the log, keep the worker alive.
            log.exception("ingest job crashed: doc_id=%s", job[0])
            try:
                catalog.update_document(job[0], "failed", "ingest worker crash",
                                        db_path=job[4])
            except Exception:
                pass
        finally:
            _QUEUE.task_done()


def _run(doc_id, file_path, matter_slug, db_path, catalog_db):
    if catalog.get_document(doc_id, db_path=catalog_db) is None:
        log.info("ingest skipped, doc deleted while queued: %s", doc_id)
        return
    stage_t = {"start": time.perf_counter()}

    def on_stage(stage):
        _state["current"] = {"doc_id": doc_id, "stage": stage}
        stage_t[stage] = time.perf_counter()

    on_stage("parsing")
    catalog.update_document(doc_id, "parsing", db_path=catalog_db)
    result = kb_ingest.ingest_document(doc_id, file_path, matter_slug, db_path,
                                       catalog_db, on_stage=on_stage)
    total_ms = (time.perf_counter() - stage_t["start"]) * 1000
    marks = sorted((t, s) for s, t in stage_t.items() if s != "start")
    stages = " ".join(
        f"{s}={((marks[i + 1][0] if i + 1 < len(marks) else time.perf_counter()) - t) * 1000:.0f}ms"
        for i, (t, s) in enumerate(marks))
    log.info("ingest doc=%s status=%s total=%.0fms %s", doc_id, result, total_ms, stages)

    # M-2: build the matter digest for a successfully ingested doc. Best-effort —
    # a digest failure must never fail the ingest (the doc is already searchable).
    if result in ("ready", "needs_review"):
        on_stage("digest")
        try:
            digest.extract_for_document(doc_id, db_path, catalog_db=catalog_db)
        except Exception:
            log.exception("digest failed (non-fatal): doc_id=%s", doc_id)

    _state["processed"] += 1
    _state["current"] = None
    if _state["processed"] % OPTIMIZE_EVERY == 0:
        try:
            t0 = time.perf_counter()
            open_table(db_path).optimize()
            log.info("store optimize after %d ingests: %.0fms",
                     _state["processed"], (time.perf_counter() - t0) * 1000)
        except Exception:
            log.exception("table.optimize() failed (non-fatal)")
