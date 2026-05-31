"""Job dispatcher — routes leased jobs to the right handler.

Today only ``event_alert`` is supported. The DISPATCH map is the seam
F5 (morning_digest) extends.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from typing import Any, Dict


log = logging.getLogger(__name__)


def dispatch_event_alert(
    conn: sqlite3.Connection,
    job: Dict[str, Any],
    *,
    secretary,                           # tradingagents.secretary.service.Secretary
) -> Dict[str, Any]:
    """Run an event_alert job. Returns the rollup dict the worker writes
    into queue_jobs (brief_id, run_ids JSON, cost_usd)."""
    payload = json.loads(job["payload"])
    event_id = payload["event_id"]
    ticker = payload["ticker"]
    job_id = job["job_id"]

    brief_id = secretary.compose_event_alert(
        event_id=event_id, ticker=ticker, job_id=job_id,
    )

    # Pull run_ids back from the brief row (compose_event_alert wrote them).
    brief = conn.execute(
        "SELECT run_ids FROM briefs WHERE brief_id = ?", (brief_id,)
    ).fetchone()
    run_ids = json.loads(brief["run_ids"]) if brief and brief["run_ids"] else []

    # Cost rollup: sum usd_estimate across all runs in this job.
    if run_ids:
        placeholders = ",".join("?" for _ in run_ids)
        row = conn.execute(
            f"SELECT COALESCE(SUM(usd_estimate), 0) "
            f"FROM costs WHERE run_id IN ({placeholders})",
            tuple(run_ids),
        ).fetchone()
        cost_usd = float(row[0])
    else:
        cost_usd = 0.0

    return {"brief_id": brief_id, "run_ids": run_ids, "cost_usd": cost_usd}


DISPATCH = {
    "event_alert": dispatch_event_alert,
    # F5 will add: "morning_digest": dispatch_morning_digest
}


def dispatch(
    conn: sqlite3.Connection,
    job: Dict[str, Any],
    *,
    secretary,
) -> Dict[str, Any]:
    handler = DISPATCH.get(job["job_type"])
    if handler is None:
        raise ValueError(f"unknown job_type: {job['job_type']!r}")
    return handler(conn, job, secretary=secretary)
