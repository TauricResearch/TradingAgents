"""Queue panel — current depth + recent jobs + worker heartbeat."""

from __future__ import annotations

import sqlite3
from typing import Optional


def fetch_queue_depth(conn: sqlite3.Connection) -> dict[str, int]:
    rows = conn.execute(
        "SELECT state, COUNT(*) AS n FROM queue_jobs GROUP BY state"
    ).fetchall()
    return {r["state"]: r["n"] for r in rows}


def fetch_recent_jobs(conn: sqlite3.Connection, *, limit: int = 10) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM queue_jobs ORDER BY job_id DESC LIMIT ?", (limit,)
    ).fetchall()
    return [dict(r) for r in rows]


def fetch_worker_heartbeat(conn: sqlite3.Connection) -> Optional[str]:
    """Last started_ts or finished_ts transition timestamp."""
    row = conn.execute(
        "SELECT MAX(coalesce(started_ts, finished_ts)) AS last_seen FROM queue_jobs"
    ).fetchone()
    return row["last_seen"] if row else None
