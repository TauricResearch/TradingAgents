"""Low-level SQL helpers over the queue_jobs table.

Each function takes an open sqlite3.Connection and commits before returning,
EXCEPT lease_one which relies on the implicit BEGIN IMMEDIATE inside
``with conn:`` for atomicity (and commits at the end of the with-block).
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Iterable, Optional


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def insert_queue_job(
    conn: sqlite3.Connection,
    *,
    job_type: str,
    payload: str,                      # already-serialized JSON string
    trigger_event_id: Optional[str],
) -> int:
    cur = conn.execute(
        "INSERT INTO queue_jobs (job_type, payload, state, enqueued_ts, "
        "trigger_event_id) VALUES (?, ?, 'queued', ?, ?)",
        (job_type, payload, _now_iso(), trigger_event_id),
    )
    conn.commit()
    return cur.lastrowid


def lease_one(conn: sqlite3.Connection) -> Optional[sqlite3.Row]:
    """Atomically claim the oldest queued job. Returns the updated row or None.

    Uses ``UPDATE … RETURNING`` (sqlite >= 3.35). The implicit BEGIN IMMEDIATE
    from ``with conn:`` ensures two concurrent leasers cannot both win the
    same job — the second sees the row already updated and returns nothing.
    """
    with conn:
        row = conn.execute(
            """
            UPDATE queue_jobs
               SET state = 'running',
                   started_ts = ?
             WHERE job_id = (
                 SELECT job_id FROM queue_jobs
                  WHERE state = 'queued'
                  ORDER BY job_id
                  LIMIT 1
             )
         RETURNING job_id, job_type, payload, trigger_event_id, state, started_ts
            """,
            (_now_iso(),),
        ).fetchone()
    return row


def mark_done(
    conn: sqlite3.Connection,
    *,
    job_id: int,
    run_ids: Iterable[str],
    brief_id: Optional[str],
    cost_usd: Optional[float],
) -> None:
    conn.execute(
        "UPDATE queue_jobs SET state = 'done', finished_ts = ?, "
        "run_ids = ?, brief_id = ?, cost_usd = ? WHERE job_id = ?",
        (_now_iso(), json.dumps(list(run_ids)), brief_id, cost_usd, job_id),
    )
    conn.commit()


def mark_error(
    conn: sqlite3.Connection,
    *,
    job_id: int,
    error_msg: str,
) -> None:
    conn.execute(
        "UPDATE queue_jobs SET state = 'error', finished_ts = ?, error = ? "
        "WHERE job_id = ?",
        (_now_iso(), error_msg, job_id),
    )
    conn.commit()


def pending_count(conn: sqlite3.Connection) -> int:
    """Jobs currently queued OR running (anything not yet terminal)."""
    return conn.execute(
        "SELECT COUNT(*) FROM queue_jobs WHERE state IN ('queued', 'running')"
    ).fetchone()[0]


def daily_enqueue_count(conn: sqlite3.Connection) -> int:
    """Jobs enqueued in the last 24h (regardless of current state)."""
    return conn.execute(
        "SELECT COUNT(*) FROM queue_jobs "
        "WHERE datetime(enqueued_ts) > datetime('now', '-1 day')"
    ).fetchone()[0]


def daily_cost_total(conn: sqlite3.Connection) -> float:
    """Sum of cost_usd for jobs finished today (UTC date)."""
    row = conn.execute(
        "SELECT COALESCE(SUM(cost_usd), 0) FROM queue_jobs "
        "WHERE state = 'done' AND date(finished_ts) = date('now')"
    ).fetchone()
    return float(row[0])


def sweep_stale_leases(
    conn: sqlite3.Connection, *, max_age_seconds: int = 3600,
    reason: str = "stale_lease_swept_on_boot",
) -> int:
    """Mark any 'running' job older than max_age_seconds as 'error'.

    Used by the worker at boot AND periodically in-loop (S-4) to recover jobs
    left 'running' by an unclean shutdown or a blown wall-clock cap. ``reason``
    is recorded in the error column for post-mortems.
    Returns the number of rows swept.

    NOTE: ``started_ts`` is stored as an ISO-8601 string with a 'T' separator
    and a '+00:00' offset, so it MUST be wrapped in ``datetime(...)`` before
    comparison with SQLite's space-separated ``datetime('now', ?)``. A raw
    string compare silently fails for same-calendar-date rows ('T' 0x54 >
    ' ' 0x20), which made this sweep a no-op for any job that went stale today.
    """
    n = conn.execute(
        "UPDATE queue_jobs SET state = 'error', finished_ts = ?, "
        "error = ? "
        "WHERE state = 'running' AND datetime(started_ts) < datetime('now', ?)",
        (_now_iso(), reason, f"-{max_age_seconds} seconds"),
    ).rowcount
    conn.commit()
    return n
