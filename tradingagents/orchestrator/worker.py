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


def _install_signal_handlers():
    def _handler(signum, frame):
        global _shutdown
        _shutdown = True
        log.info("received signal %s; shutting down after current job", signum)
    signal.signal(signal.SIGTERM, _handler)
    signal.signal(signal.SIGINT, _handler)


def main(config: Optional[dict] = None) -> None:
    from tradingagents.default_config import DEFAULT_CONFIG
    cfg = dict(DEFAULT_CONFIG)
    if config:
        cfg.update(config)

    conn = connect(cfg["iic_db_path"])
    swept = boot_sweep(conn, max_age_seconds=3600)
    if swept:
        log.warning("boot sweep marked %d stale lease(s) as error", swept)

    secretary = _build_secretary(cfg, conn)
    budget = DailyBudgetGuard(
        enabled=cfg["daily_budget_enabled"],
        daily_usd=cfg["daily_budget_usd"],
    )
    job_timeout = cfg["worker_job_timeout_min"] * 60

    _install_signal_handlers()
    log.info("worker started: poll=%ss timeout=%dm budget_enabled=%s",
             cfg["worker_poll_interval_s"], cfg["worker_job_timeout_min"],
             budget.enabled)

    while not _shutdown:
        try:
            with ThreadPoolExecutor(max_workers=1) as ex:
                fut = ex.submit(drain_one, conn,
                                 secretary=secretary, budget_guard=budget)
                try:
                    ran = fut.result(timeout=job_timeout)
                except FuturesTimeout:
                    log.exception("job timed out after %ds (cannot abort "
                                  "in-flight LangGraph; relying on "
                                  "stale-lease sweep on next worker boot)",
                                  job_timeout)
                    ran = True   # sleep less aggressively after a timeout
        except KeyboardInterrupt:
            break
        except Exception:
            log.exception("worker loop failure; sleeping 5s and continuing")
            time.sleep(5)
            continue
        if not ran:
            time.sleep(cfg["worker_poll_interval_s"])

    log.info("worker stopped")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    main()
