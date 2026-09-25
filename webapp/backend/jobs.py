"""Background execution of TradingAgentsGraph analysis runs.

A run makes several LLM calls and can take minutes, so it's dispatched to a
thread pool and polled by job id rather than executed inline in a request.
"""

from __future__ import annotations

import logging
import uuid
from concurrent.futures import ThreadPoolExecutor

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph

from . import database

logger = logging.getLogger(__name__)

# Small pool: each worker holds an LLM-bound graph run. Raise via env if the
# deployment has the API rate limits / hardware to support more concurrency.
_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="ta-analysis")


def submit_job(user_id: int, ticker: str, trade_date: str) -> str:
    job_id = uuid.uuid4().hex
    database.create_job(job_id, user_id, ticker, trade_date)
    _EXECUTOR.submit(_run_job, job_id, ticker, trade_date)
    return job_id


def _run_job(job_id: str, ticker: str, trade_date: str) -> None:
    database.update_job(job_id, status="running")
    try:
        config = DEFAULT_CONFIG.copy()
        graph = TradingAgentsGraph(debug=False, config=config)
        final_state, decision = graph.propagate(ticker, trade_date)
        report = final_state.get("final_trade_decision") or str(decision)
        database.update_job(
            job_id,
            status="done",
            decision=str(decision),
            report=report,
            finished_at=_iso_now(),
        )
    except Exception as exc:  # noqa: BLE001 - surface any failure to the caller
        logger.exception("Analysis job %s failed", job_id)
        database.update_job(
            job_id, status="failed", error=str(exc), finished_at=_iso_now()
        )


def _iso_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()
