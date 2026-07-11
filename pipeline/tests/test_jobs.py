"""D-90 job runner — lifecycle, cancel, dedupe, restart honesty, event replay.

All against a temp sqlite catalog (db_path override) with tiny synthetic tenants;
no Ollama, no network. The runner's contract: persisted rows, serial FIFO worker,
per-clause-grade cancellation, in-flight dedupe, and events that replay identically
for a late subscriber (the reloaded-UI case)."""

import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

PIPELINE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPELINE_DIR))

import catalog  # noqa: E402
import jobs  # noqa: E402


class JobsBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db = str(Path(self._tmp.name) / "catalog.db")
        jobs._reset_for_tests()

    def tearDown(self):
        jobs._reset_for_tests()
        self._tmp.cleanup()

    def submit(self, kind, params=None, **kw):
        return jobs.submit(kind, params or {}, db_path=self.db, **kw)


class TestLifecycle(JobsBase):
    def test_submit_run_done_persists_result_and_events(self):
        def tenant(ctx):
            ctx.emit("step", {"n": 1})
            ctx.emit("step", {"n": 2})
            return {"answer": 42}
        jobs.register("t-ok", tenant)

        job = self.submit("t-ok", {"x": "y"})
        self.assertFalse(job["existing"])
        self.assertTrue(jobs.wait(job["id"], timeout=10))

        row = catalog.job_get(job["id"], db_path=self.db)
        self.assertEqual(row["status"], "done")
        self.assertEqual(row["result"], {"answer": 42})
        self.assertEqual(row["params"], {"x": "y"})
        names = [e["event"] for e in row["events"]]
        self.assertEqual(names, ["started", "step", "step", "done"])
        self.assertIsNotNone(row["started"])
        self.assertIsNotNone(row["finished"])

    def test_tenant_exception_is_error_not_worker_death(self):
        jobs.register("t-boom", lambda ctx: 1 / 0)
        jobs.register("t-next", lambda ctx: {"ok": True})

        boom = self.submit("t-boom")
        after = self.submit("t-next")
        self.assertTrue(jobs.wait(after["id"], timeout=10))

        self.assertEqual(catalog.job_get(boom["id"], db_path=self.db)["status"], "error")
        self.assertIn("ZeroDivisionError", catalog.job_get(boom["id"], db_path=self.db)["error"])
        # the worker survived the tenant bug and ran the next job
        self.assertEqual(catalog.job_get(after["id"], db_path=self.db)["status"], "done")

    def test_unknown_kind_rejected(self):
        with self.assertRaises(ValueError):
            self.submit("no-such-kind")

    def test_serial_fifo(self):
        order = []
        gate = threading.Event()

        def slow(ctx):
            gate.wait(5)
            order.append(("slow", time.monotonic()))
            return {}

        def fast(ctx):
            order.append(("fast", time.monotonic()))
            return {}

        jobs.register("t-slow", slow)
        jobs.register("t-fast", fast)
        a = self.submit("t-slow")
        b = self.submit("t-fast")
        gate.set()
        self.assertTrue(jobs.wait(b["id"], timeout=10))
        self.assertEqual([n for n, _ in order], ["slow", "fast"])  # FIFO, one at a time
        self.assertTrue(jobs.wait(a["id"], timeout=10))


class TestCancel(JobsBase):
    def test_cancel_running_job_between_units(self):
        started = threading.Event()

        def tenant(ctx):
            for i in range(50):
                if ctx.cancelled():
                    raise jobs.JobCancelled()
                ctx.emit("unit", {"i": i})
                started.set()
                time.sleep(0.05)
            return {}
        jobs.register("t-cancellable", tenant)

        job = self.submit("t-cancellable")
        self.assertTrue(started.wait(5))
        jobs.cancel(job["id"], db_path=self.db)
        self.assertTrue(jobs.wait(job["id"], timeout=10))

        row = catalog.job_get(job["id"], db_path=self.db)
        self.assertEqual(row["status"], "cancelled")
        self.assertEqual(row["events"][-1]["event"], "cancelled")
        self.assertLess(len(row["events"]), 52)  # it actually stopped early

    def test_cancel_queued_job_never_runs(self):
        gate = threading.Event()
        ran = []
        jobs.register("t-gate", lambda ctx: (gate.wait(5), {})[-1])
        jobs.register("t-victim", lambda ctx: ran.append(1) or {})

        blocker = self.submit("t-gate")
        victim = self.submit("t-victim")
        self.assertTrue(jobs.cancel(victim["id"], db_path=self.db))
        gate.set()
        self.assertTrue(jobs.wait(blocker["id"], timeout=10))
        self.assertTrue(jobs.wait(victim["id"], timeout=10))

        self.assertEqual(catalog.job_get(victim["id"], db_path=self.db)["status"],
                         "cancelled")
        self.assertEqual(ran, [])


class TestDedupe(JobsBase):
    def test_active_dedupe_key_returns_existing(self):
        gate = threading.Event()
        jobs.register("t-review", lambda ctx: (gate.wait(5), {})[-1])

        first = self.submit("t-review", {"matter": "m"}, dedupe_key="review:m")
        second = self.submit("t-review", {"matter": "m"}, dedupe_key="review:m")
        self.assertEqual(second["id"], first["id"])
        self.assertTrue(second["existing"])   # the double-click guard
        gate.set()
        self.assertTrue(jobs.wait(first["id"], timeout=10))

        third = self.submit("t-review", {"matter": "m"}, dedupe_key="review:m")
        self.assertNotEqual(third["id"], first["id"])  # terminal -> a new run is fine
        self.assertTrue(jobs.wait(third["id"], timeout=10))


class TestRestartHonesty(JobsBase):
    def test_mark_interrupted_flips_stale_rows(self):
        # simulate rows left behind by a dead process (no in-memory state)
        catalog.job_create("t-x", {}, db_path=self.db)                       # queued
        running = catalog.job_create("t-x", {}, db_path=self.db)
        catalog.job_update(running["id"], db_path=self.db, status="running")
        done = catalog.job_create("t-x", {}, db_path=self.db)
        catalog.job_update(done["id"], db_path=self.db, status="done")

        flipped = jobs.mark_interrupted(db_path=self.db)
        self.assertEqual(flipped, 2)
        for jid, want in ((running["id"], "error"), (done["id"], "done")):
            self.assertEqual(catalog.job_get(jid, db_path=self.db)["status"], want)
        self.assertIn("interrupted",
                      catalog.job_get(running["id"], db_path=self.db)["error"])


class TestColumnAllowlist(JobsBase):
    def test_job_update_rejects_unknown_columns(self):
        job = catalog.job_create("t-x", {}, db_path=self.db)
        with self.assertRaises(ValueError):
            catalog.job_update(job["id"], db_path=self.db,
                               **{"status = 'done' WHERE 1=1; --": "x"})


class TestSubscribe(JobsBase):
    def test_late_subscriber_replays_full_history(self):
        def tenant(ctx):
            ctx.emit("step", {"n": 1})
            return {"ok": True}
        jobs.register("t-replay", tenant)
        job = self.submit("t-replay")
        self.assertTrue(jobs.wait(job["id"], timeout=10))

        replay, live = jobs.subscribe(job["id"], db_path=self.db)
        self.assertIsNone(live)  # terminal -> replay is the whole story
        self.assertEqual([e["event"] for e in replay], ["started", "step", "done"])

    def test_live_subscriber_gets_events_then_sentinel(self):
        gate = threading.Event()

        def tenant(ctx):
            gate.wait(5)
            ctx.emit("step", {"n": 1})
            return {}
        jobs.register("t-live", tenant)
        job = self.submit("t-live")
        replay, live = jobs.subscribe(job["id"], db_path=self.db)
        self.assertIsNotNone(live)
        gate.set()
        seen = list(replay)
        while True:
            ev = live.get(timeout=10)
            if ev is None:
                break
            seen.append(ev)
        self.assertEqual([e["event"] for e in seen], ["started", "step", "done"])

    def test_unknown_job_subscribe(self):
        replay, live = jobs.subscribe(99999, db_path=self.db)
        self.assertIsNone(replay)
        self.assertIsNone(live)


if __name__ == "__main__":
    unittest.main()
