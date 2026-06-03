"""F4 worker — leases queued jobs and dispatches by job_type.

Runs as `iic-worker.service`. Single-process; concurrency capped by
``max_concurrent_jobs`` (default 1). Per-job wall-clock cap enforced
via concurrent.futures timeout in ``main()`` (not in ``drain_one`` to
keep that function trivially unit-testable).
"""

from __future__ import annotations

import logging
import signal
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from typing import Optional

from tradingagents.persistence.db import connect
from tradingagents.orchestrator import queue_store
from tradingagents.orchestrator.dispatch import dispatch
from tradingagents.orchestrator.guards import DailyBudgetGuard


log = logging.getLogger(__name__)


def boot_sweep(conn: sqlite3.Connection, *, max_age_seconds: int) -> int:
    """One-shot sweep on worker startup. See spec R-F4-2."""
    return queue_store.sweep_stale_leases(conn, max_age_seconds=max_age_seconds)


def _build_secretary(config: dict, conn: sqlite3.Connection):
    """Same construction shape as cli/deepdive._build_secretary."""
    from tradingagents.llm_clients.factory import create_llm_client
    from tradingagents.secretary.service import Secretary
    client = create_llm_client(
        provider=config["llm_provider"],
        model=config["deep_think_llm"],
        base_url=config.get("backend_url"),
    )
    llm = client.get_llm()
    return Secretary(conn=conn, data_dir=config["iic_data_dir"], llm=llm)


def drain_one(
    conn: sqlite3.Connection,
    *,
    secretary,
    budget_guard: Optional[DailyBudgetGuard] = None,
) -> bool:
    """Lease + dispatch + mark exactly one job. Returns True if a job ran.

    Per-job wall-clock cap is enforced in ``main()`` (using a ThreadPoolExecutor
    + future.result(timeout)); ``drain_one`` is the synchronous core so unit
    tests can exercise it without process-level timeout machinery.
    """
    if budget_guard is not None and not budget_guard.gate(conn):
        return False

    job = queue_store.lease_one(conn)
    if job is None:
        return False

    try:
        result = dispatch(conn, dict(job), secretary=secretary)
        queue_store.mark_done(
            conn,
            job_id=job["job_id"],
            run_ids=result["run_ids"],
            brief_id=result["brief_id"],
            cost_usd=result["cost_usd"],
        )
        log.info("job %d done (brief=%s cost=$%.4f)",
                 job["job_id"], result["brief_id"], result["cost_usd"])
    except Exception as exc:
        queue_store.mark_error(
            conn, job_id=job["job_id"], error_msg=str(exc),
        )
        log.exception("job %d failed", job["job_id"])
    return True


_shutdown = False

# How often the worker re-checks _shutdown while a job is in flight. Bounds how
# long a stop signal takes to be honored mid-job instead of blocking for the
# whole per-job wall-clock cap (worker_job_timeout_min).
_SHUTDOWN_POLL_S = 2.0


def _install_signal_handlers():
    def _handler(signum, frame):
        global _shutdown
        _shutdown = True
        log.info("received signal %s; stopping (in-flight job, if any, is "
                 "abandoned and reclaimed by the stale-lease sweep)", signum)
    signal.signal(signal.SIGTERM, _handler)
    signal.signal(signal.SIGINT, _handler)


def _await_job(fut, *, job_timeout, poll_interval=_SHUTDOWN_POLL_S):
    """Wait for the in-flight drain future, polling in short slices.

    Returns the future's result (True if a job ran, False if the queue was
    idle) on normal completion. If a stop is requested mid-job (``_shutdown``
    set by the signal handler on SIGTERM/SIGINT), returns ``True`` immediately
    so the caller skips its idle sleep and the loop exits within ~poll_interval
    — the abandoned job's lease is reclaimed by the stale-lease sweep on the
    next boot. Raises ``FuturesTimeout`` once the job exceeds ``job_timeout``,
    preserving the caller's S-4b abandon-and-replace handling.

    Without this, ``fut.result(timeout=job_timeout)`` blocks the loop for the
    full per-job cap (up to 20 min) before re-checking _shutdown, so
    ``systemctl stop`` hangs until the current brief finishes.
    """
    deadline = time.monotonic() + job_timeout
    while True:
        if _shutdown:
            log.info("stop requested mid-job; abandoning the in-flight run "
                     "(cannot abort LangGraph) — lease reclaimed by sweep")
            return True
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise FuturesTimeout
        try:
            return fut.result(timeout=min(poll_interval, remaining))
        except FuturesTimeout:
            if time.monotonic() >= deadline:
                raise
            # Only a poll slice elapsed — loop to re-check _shutdown.
            continue


def main(config: Optional[dict] = None) -> None:
    from tradingagents.default_config import DEFAULT_CONFIG
    cfg = dict(DEFAULT_CONFIG)
    if config:
        cfg.update(config)

    # Main-thread connection: used ONLY by this (the main) thread, for the boot
    # and in-loop stale-lease sweeps. Job execution runs on a separate pool
    # thread and uses its OWN connection (see _drain_once) — a sqlite3
    # connection is bound to the thread that created it (check_same_thread), so
    # the worker's connection can never be shared with drain_one's thread (doing
    # so raises ProgrammingError, which the loop's broad except would swallow,
    # silently wedging the worker forever).
    conn = connect(cfg["iic_db_path"])
    swept = boot_sweep(conn, max_age_seconds=3600)
    if swept:
        log.warning("boot sweep marked %d stale lease(s) as error", swept)

    budget = DailyBudgetGuard(
        enabled=cfg["daily_budget_enabled"],
        daily_usd=cfg["daily_budget_usd"],
    )
    job_timeout = cfg["worker_job_timeout_min"] * 60

    # Stale-lease reclamation must run INSIDE the loop, not only at boot
    # (R-F4-2 / S-4). A job whose lease went stale — because the worker died
    # OR because the job blew past its wall-clock cap and its future was
    # abandoned — is recovered to 'error' here without ever needing a restart.
    # max_age must comfortably exceed the per-job timeout so we never reclaim
    # a job that is still legitimately running; we add a margin on top.
    sweep_max_age = max(job_timeout * 2, job_timeout + 300)
    # How often to run the in-loop sweep, in seconds of wall-clock. We track
    # this against time rather than a cycle count so a slow/blocked iteration
    # can't starve the sweep.
    sweep_interval = max(cfg["worker_poll_interval_s"], 30)
    last_sweep = time.monotonic()

    # Per-drain-thread resources. The connection (and the Secretary that holds
    # it) can only be used on the thread that created them, so we build them
    # lazily ON the drain thread and cache them in thread-local storage. Built
    # once and reused across jobs; a fresh drain thread (after a timeout, below)
    # rebuilds its own — no connection is ever shared across threads.
    tls = threading.local()

    def _drain_once() -> bool:
        if getattr(tls, "conn", None) is None:
            tls.conn = connect(cfg["iic_db_path"])
            tls.secretary = _build_secretary(cfg, tls.conn)
        return drain_one(
            tls.conn, secretary=tls.secretary, budget_guard=budget,
        )

    # Single-slot executor (max_concurrent_jobs is 1). On a per-job timeout we
    # cannot kill the runaway LangGraph thread (Python has no thread-kill), so
    # we abandon it AND replace the executor: the next job gets a fresh thread
    # + connection, and abandoned work-items can't pile up in the old
    # executor's unbounded internal queue (which would never be GC'd and would
    # hold connection references).
    ex = ThreadPoolExecutor(max_workers=1, thread_name_prefix="drain")

    _install_signal_handlers()
    log.info("worker started: poll=%ss timeout=%dm budget_enabled=%s "
             "sweep_max_age=%ds sweep_interval=%ds",
             cfg["worker_poll_interval_s"], cfg["worker_job_timeout_min"],
             budget.enabled, sweep_max_age, sweep_interval)

    try:
        while not _shutdown:
            # Periodic in-loop stale-lease sweep (S-4a).
            now = time.monotonic()
            if now - last_sweep >= sweep_interval:
                try:
                    n = queue_store.sweep_stale_leases(
                        conn, max_age_seconds=sweep_max_age,
                        reason="stale_lease_swept_in_loop",
                    )
                    if n:
                        log.warning(
                            "in-loop sweep reclaimed %d stale lease(s) "
                            "to 'error'", n,
                        )
                except Exception:
                    log.exception("in-loop stale-lease sweep failed")
                last_sweep = now

            try:
                fut = ex.submit(_drain_once)
                try:
                    # Poll in short slices so a stop signal (which sets
                    # _shutdown) is honored within ~_SHUTDOWN_POLL_S rather than
                    # blocking here for the whole per-job wall-clock cap.
                    ran = _await_job(fut, job_timeout=job_timeout)
                except FuturesTimeout:
                    # Non-blocking timeout (S-4b): we do NOT join the runaway
                    # thread. Abandon the future, replace the wedged executor
                    # (the runaway thread permanently holds its only slot), and
                    # proceed; the job's lease is reclaimed by the periodic
                    # sweep above — no restart required.
                    log.error("job timed out after %ds; abandoning the "
                              "in-flight run (cannot abort LangGraph) and "
                              "replacing the worker thread — stale-lease sweep "
                              "will mark it 'error' without a restart",
                              job_timeout)
                    ex.shutdown(wait=False, cancel_futures=True)
                    ex = ThreadPoolExecutor(
                        max_workers=1, thread_name_prefix="drain",
                    )
                    ran = True   # sleep less aggressively after a timeout
            except KeyboardInterrupt:
                break
            except Exception:
                log.exception("worker loop failure; sleeping 5s and continuing")
                time.sleep(5)
                continue
            if not ran:
                time.sleep(cfg["worker_poll_interval_s"])
    finally:
        # Do NOT wait on abandoned/runaway drain threads during shutdown —
        # that would reintroduce the blocking behavior S-4 removed. Cancel
        # what we can and return; signal-based shutdown stays responsive.
        ex.shutdown(wait=False, cancel_futures=True)

    log.info("worker stopped")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    main()
