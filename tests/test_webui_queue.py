"""The analysis queue behind the Screens page's "Analyze with agents": runs go one
at a time, in order, within a cap, and can be taken off or stopped. No graph and
no LLM: each run waits on a gate the test opens."""

from __future__ import annotations

import threading
import time

import pytest

from cli.webui import jobs

pytestmark = pytest.mark.unit


class GatedJob(jobs.AnalysisJob):
    """A run that holds until its gate opens, recording how many ran at once."""

    running = 0
    peak = 0
    order: list[str] = []
    lock = threading.Lock()

    def __post_init__(self):
        super().__post_init__()
        self.gate = threading.Event()

    def _run(self):
        cls = type(self)
        with cls.lock:
            cls.running += 1
            cls.peak = max(cls.peak, cls.running)
            cls.order.append(self.ticker)
        try:
            while not self.gate.wait(0.01):
                if self._cancel.is_set():
                    self.status = jobs.CANCELLED
                    return
            self.status = jobs.DONE
        finally:
            with cls.lock:
                cls.running -= 1
            self.finished = time.time()


@pytest.fixture(autouse=True)
def reset():
    GatedJob.running = GatedJob.peak = 0
    GatedJob.order = []


def job(ticker):
    return GatedJob(ticker, "2026-09-01", "stock", ["market"], {})


def wait_for(predicate, timeout=5.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("timed out")


def test_queued_runs_go_one_at_a_time_in_order():
    registry = jobs.JobRegistry()
    queue = jobs.AnalysisQueue(registry)
    runs = [job(t) for t in ("AAA.NS", "BBB.NS", "CCC.NS")]
    ids = queue.submit(runs)
    assert ids == [r.id for r in runs] and all(registry.get(i) is r for i, r in zip(ids, runs, strict=True))
    wait_for(lambda: runs[0].status == jobs.RUNNING)
    status = queue.status()
    assert status["current"] == runs[0].id and status["waiting"] == 2
    assert [r["position"] for r in status["runs"]] == [None, 1, 2]
    assert [r.status for r in runs[1:]] == [jobs.PENDING, jobs.PENDING]
    for r in runs:
        wait_for(lambda r=r: r.status == jobs.RUNNING)
        time.sleep(0.05)  # long enough for a second run to start, were the queue to allow it
        r.gate.set()
        wait_for(lambda r=r: r.status == jobs.DONE)
    wait_for(lambda: queue.status()["current"] is None)
    assert GatedJob.peak == 1 and GatedJob.order == ["AAA.NS", "BBB.NS", "CCC.NS"]


def test_the_queue_respects_its_cap():
    queue = jobs.AnalysisQueue(jobs.JobRegistry(), max_waiting=2)
    first = [job("AAA.NS"), job("BBB.NS"), job("CCC.NS")]
    queue.submit(first[:1])
    wait_for(lambda: first[0].status == jobs.RUNNING)
    queue.submit(first[1:])  # two waiting: at the cap
    with pytest.raises(jobs.QueueFull, match="at most 2 waiting runs; 0 more"):
        queue.submit([job("DDD.NS")])
    for r in first:
        r.gate.set()
    wait_for(lambda: all(r.status == jobs.DONE for r in first))


def test_a_waiting_run_can_be_taken_off_and_the_running_one_stopped():
    queue = jobs.AnalysisQueue(jobs.JobRegistry())
    a, b, c = job("AAA.NS"), job("BBB.NS"), job("CCC.NS")
    queue.submit([a, b, c])
    wait_for(lambda: a.status == jobs.RUNNING)
    assert queue.cancel(b.id) is True
    assert b.status == jobs.CANCELLED and not queue.holds(b.id)
    assert queue.cancel(a.id) is True  # the running one: stops after its current step
    wait_for(lambda: a.status == jobs.CANCELLED)
    wait_for(lambda: c.status == jobs.RUNNING)
    c.gate.set()
    wait_for(lambda: c.status == jobs.DONE)
    assert GatedJob.order == ["AAA.NS", "CCC.NS"]  # B never ran
    assert queue.cancel("nope") is False


def test_cancel_all_empties_the_queue():
    queue = jobs.AnalysisQueue(jobs.JobRegistry())
    runs = [job(t) for t in ("AAA.NS", "BBB.NS", "CCC.NS")]
    queue.submit(runs)
    wait_for(lambda: runs[0].status == jobs.RUNNING)
    assert queue.cancel_all() == 3
    wait_for(lambda: all(r.status == jobs.CANCELLED for r in runs))
    wait_for(lambda: queue.status()["current"] is None)
    assert GatedJob.order == ["AAA.NS"]


def test_the_worker_restarts_for_a_later_batch():
    queue = jobs.AnalysisQueue(jobs.JobRegistry())
    first = job("AAA.NS")
    first.gate.set()
    queue.submit([first])
    wait_for(lambda: first.status == jobs.DONE and queue.status()["current"] is None)
    second = job("BBB.NS")
    second.gate.set()
    queue.submit([second])
    wait_for(lambda: second.status == jobs.DONE)
    assert [r["ticker"] for r in queue.status()["runs"]] == ["AAA.NS", "BBB.NS"]
