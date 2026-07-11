"""Job-runner router (D-90) — generic progress/cancel surface for queued background
work. GET /jobs/{id}/events streams the job's event history + live tail as SSE (a
reloaded UI replays identically); POST /jobs/{id}/cancel stops it at the tenant's
next poll; GET /jobs/{id} is the persisted row (status + result). Read-only over
job state — tenants own their payloads; no document data lives here."""

import json
import queue as queue_mod

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

import catalog
import jobs

router = APIRouter()

_TERMINAL_EVENTS = ("done", "error", "cancelled")


def _event(name, obj):
    return f"event: {name}\ndata: {json.dumps(obj)}\n\n"


@router.get("/jobs/{job_id}")
def get_job(job_id: int):
    job = catalog.job_get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"unknown job: {job_id}")
    return job


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: int):
    job = catalog.job_get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"unknown job: {job_id}")
    jobs.cancel(job_id)
    return {"ok": True, "id": job_id}


@router.get("/jobs/{job_id}/events")
def job_events(job_id: int):
    replay, live = jobs.subscribe(job_id)
    if replay is None:
        raise HTTPException(status_code=404, detail=f"unknown job: {job_id}")

    def stream():
        # The finally must cover EVERY yield (including replay): a client that
        # drops mid-replay raises GeneratorExit at that yield, and the queue
        # registered by subscribe() would otherwise leak for the job's lifetime.
        try:
            ended = False
            for ev in replay:
                yield _event(ev["event"], ev["data"])
                ended = ended or ev["event"] in _TERMINAL_EVENTS
            if live is None or ended:
                if not ended:
                    # terminal job whose history lacks a terminal event (e.g.
                    # interrupted by a restart) — close the stream honestly
                    # instead of hanging. A finished job replays its result.
                    job = catalog.job_get(job_id)
                    status = (job or {}).get("status")
                    if status == "done":
                        yield _event("done", (job or {}).get("result") or {})
                    elif status in ("error", "cancelled"):
                        yield _event(status,
                                     {"detail": (job or {}).get("error") or status})
                return
            while True:
                try:
                    ev = live.get(timeout=15)
                except queue_mod.Empty:
                    yield ": keepalive\n\n"   # comment frame; keeps WKWebView reading
                    continue
                if ev is None:
                    return
                yield _event(ev["event"], ev["data"])
                if ev["event"] in _TERMINAL_EVENTS:
                    return
        finally:
            if live is not None:
                jobs.unsubscribe(job_id, live)

    return StreamingResponse(stream(), media_type="text/event-stream")
