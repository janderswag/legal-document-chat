"""D-90 — the background job runner (council 2026-07-11, Priya's R2 rule).

Anything that takes longer than ~10 seconds becomes a QUEUED BACKGROUND JOB, never a
long-lived HTTP request. This module is the generalized runner; the clause review is
its first tenant (registered in review_job.py). Design:

- **Persisted**: every job is a row in the encrypted catalog (catalog.jobs_*). The
  full event history is stored, so a reloaded UI replays progress, and the final
  result is stored, so a finished review costs zero seconds to reopen.
- **Serial**: ONE worker thread runs jobs FIFO. The local Ollama is the scarce
  resource — two concurrent reviews would halve each other, and the runner must never
  become a second source of model contention (R3).
- **Cancellable**: cancel() flips a per-job event; tenants poll ctx.cancelled()
  between units of work and raise JobCancelled.
- **Honest across restarts**: jobs.mark_interrupted() (called at app startup) flips
  any queued/running row to an error — a job can never look alive after the process
  that ran it has died.

Tenant contract: register(kind, fn) where fn(ctx) -> result dict. ctx.params are the
submitted params; ctx.emit(name, data) streams a progress event (persisted + live);
ctx.cancelled() polls the cancel flag. No document data lives here — tenants own
their payloads. Runner state is process-local; persistence goes through catalog.
"""

import json
import queue
import threading

import catalog

_REGISTRY = {}                 # kind -> fn(ctx) -> result dict
_MAX_EVENTS = 500              # persisted-event cap per job (runaway-tenant guard)

_lock = threading.Lock()       # guards everything below
_queue = []                    # FIFO of (job_id, db_path)
_wake = threading.Condition(_lock)
_worker = None                 # the single worker thread, started lazily
_generation = 0                # bumped by _reset_for_tests; stale workers exit
_cancels = {}                  # job_id -> threading.Event
_subscribers = {}              # job_id -> [queue.Queue]
_events_mem = {}               # job_id -> [event dict] (live copy of events_json)
_done = {}                     # job_id -> threading.Event (wait() support)


class JobCancelled(Exception):
    """Raised by tenants when ctx.cancelled() is observed."""


class JobContext:
    def __init__(self, job_id, params, db_path):
        self.job_id = job_id
        self.params = params
        self.db_path = db_path
        self._cancel = _cancels[job_id]

    def cancelled(self):
        return self._cancel.is_set()

    def emit(self, name, data):
        _emit(self.job_id, self.db_path, name, data)


def register(kind, fn):
    _REGISTRY[kind] = fn


def submit(kind, params, matter_slug=None, dedupe_key=None, db_path=None):
    """Queue a job. If dedupe_key is given and a queued/running job with the same
    kind+dedupe_key exists, return that job instead (``existing=True``) — the
    in-flight guard that stops a double-click from burning the model twice."""
    if kind not in _REGISTRY:
        raise ValueError(f"unknown job kind: {kind!r}")
    with _lock:
        if dedupe_key is not None:
            active = catalog.job_find_active(kind, dedupe_key, db_path=db_path)
            if active:
                active["existing"] = True
                return active
        job = catalog.job_create(kind, params, matter_slug=matter_slug,
                                 dedupe_key=dedupe_key, db_path=db_path)
        jid = job["id"]
        _cancels[jid] = threading.Event()
        _events_mem[jid] = []
        _done[jid] = threading.Event()
        _queue.append((jid, db_path))
        _ensure_worker()
        _wake.notify_all()
    job["existing"] = False
    return job


def cancel(job_id, db_path=None):
    """Cancel a job. Queued -> cancelled immediately; running -> flag set, the tenant
    stops at its next ctx.cancelled() poll. Terminal jobs are untouched."""
    with _lock:
        ev = _cancels.get(job_id)
        if ev:
            ev.set()
        for i, (jid, dbp) in enumerate(_queue):
            if jid == job_id:
                del _queue[i]
                _finish(job_id, dbp, "cancelled", event=("cancelled", {}))
                return True
    job = catalog.job_get(job_id, db_path=db_path)
    return bool(job and job["status"] in ("running", "cancelled"))


def subscribe(job_id, db_path=None):
    """(replay, live_queue_or_None). Replay = every event so far. live None = the job
    is already terminal, replay is the whole story. Atomic with emit — no gaps."""
    with _lock:
        if job_id in _events_mem:
            replay = list(_events_mem[job_id])
            done_ev = _done.get(job_id)
            if done_ev and done_ev.is_set():
                return replay, None
            q = queue.Queue()
            _subscribers.setdefault(job_id, []).append(q)
            return replay, q
    # Not in memory: an older (pre-restart or long-finished) job — replay from disk.
    job = catalog.job_get(job_id, db_path=db_path)
    if not job:
        return None, None
    return list(job.get("events") or []), None


def unsubscribe(job_id, q):
    with _lock:
        subs = _subscribers.get(job_id)
        if subs and q in subs:
            subs.remove(q)


def wait(job_id, timeout=None):
    """Block until the job is terminal (tests + smoke). False on timeout."""
    with _lock:
        ev = _done.get(job_id)
    if ev is None:
        return True  # unknown to this process -> nothing to wait on
    return ev.wait(timeout)


def mark_interrupted(db_path=None):
    """Startup: flip stale queued/running rows to error (see module docstring)."""
    return catalog.jobs_mark_interrupted(db_path=db_path)


def _ensure_worker():
    global _worker
    if _worker is None or not _worker.is_alive():
        _worker = threading.Thread(target=_worker_loop, args=(_generation,),
                                   name="job-runner", daemon=True)
        _worker.start()


def _worker_loop(my_gen):
    while True:
        with _lock:
            while not _queue and my_gen == _generation:
                _wake.wait()
            if my_gen != _generation:   # superseded by _reset_for_tests
                return
            job_id, db_path = _queue.pop(0)
            if _cancels[job_id].is_set():   # cancelled while queued (race)
                _finish(job_id, db_path, "cancelled", event=("cancelled", {}))
                continue
        try:
            _run_one(job_id, db_path)
        except Exception as e:  # a catalog hiccup in the prologue must not kill
            try:                # the worker loop (review finding #14)
                with _lock:
                    _finish(job_id, db_path, "error",
                            error=f"{type(e).__name__}: {e}",
                            event=("error", {"detail": type(e).__name__}))
            except Exception:
                pass


def _run_one(job_id, db_path):
    job = catalog.job_get(job_id, db_path=db_path)
    if not job:
        return
    catalog.job_update(job_id, db_path=db_path, status="running",
                       started=catalog._now())
    _emit(job_id, db_path, "started", {"kind": job["kind"]})
    ctx = JobContext(job_id, job.get("params") or {}, db_path)
    fn = _REGISTRY[job["kind"]]
    try:
        result = fn(ctx)
    except JobCancelled:
        with _lock:
            _finish(job_id, db_path, "cancelled", event=("cancelled", {}))
        return
    except Exception as e:  # a tenant bug must never kill the worker loop
        with _lock:
            _finish(job_id, db_path, "error", error=f"{type(e).__name__}: {e}",
                    event=("error", {"detail": f"{type(e).__name__}"}))
        return
    with _lock:
        _finish(job_id, db_path, "done", result=result, event=("done", result))


def _emit(job_id, db_path, name, data):
    # NOTE: the persisted-history write happens under the global lock, so a
    # busy_timeout stall on the catalog (up to 5s under heavy ingest) briefly
    # blocks submit/cancel/subscribe too. Fine at review scale (~22 small
    # events); revisit before a chattier tenant lands.
    event = {"event": name, "data": data}
    with _lock:
        mem = _events_mem.setdefault(job_id, [])
        if len(mem) >= _MAX_EVENTS:
            return
        mem.append(event)
        catalog.job_update(job_id, db_path=db_path, events=mem)
        for q in _subscribers.get(job_id, []):
            q.put(event)


def _finish(job_id, db_path, status, result=None, error=None, event=None):
    """Terminal transition. Caller holds _lock (or is the sole owner pre-start)."""
    fields = {"status": status, "finished": catalog._now()}
    if result is not None:
        fields["result"] = result
    if error is not None:
        fields["error"] = error
    mem = _events_mem.setdefault(job_id, [])
    if event is not None and len(mem) < _MAX_EVENTS:
        mem.append({"event": event[0], "data": event[1]})
        fields["events"] = mem
    catalog.job_update(job_id, db_path=db_path, **fields)
    if event is not None:
        for q in _subscribers.get(job_id, []):
            q.put({"event": event[0], "data": event[1]})
    for q in _subscribers.pop(job_id, []):
        q.put(None)  # end-of-stream sentinel
    done_ev = _done.get(job_id)
    if done_ev:
        done_ev.set()
    _cancels.pop(job_id, None)
    # Prune process-local copies (review finding #7): the catalog row now holds
    # the full history, and subscribe() falls back to it for terminal jobs — a
    # weeks-long process must not accumulate every finished run in RAM. Waiters
    # keep their Event reference; set-then-pop is safe.
    _events_mem.pop(job_id, None)
    _done.pop(job_id, None)


def _reset_for_tests():
    """Blow away process-local state (NOT the catalog). Unit-test hook only."""
    global _worker, _generation
    with _lock:
        _generation += 1        # any live worker exits at its next wake
        _queue.clear()
        _cancels.clear()
        _subscribers.clear()
        _events_mem.clear()
        _done.clear()
        _worker = None
        _wake.notify_all()
