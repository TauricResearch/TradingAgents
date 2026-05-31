"""Briefs panel — recent briefs table + thread view."""

from __future__ import annotations

import sqlite3
from typing import Optional


def fetch_recent_briefs(conn: sqlite3.Connection, *, limit: int = 50) -> list[dict]:
    rows = conn.execute(
        """
        SELECT b.brief_id, b.mode, b.scope, b.generated_ts,
               b.parent_brief_id, b.refine_depth,
               d.status AS delivery_status, d.channel AS delivery_channel
        FROM briefs b
        LEFT JOIN deliveries d ON d.brief_id = b.brief_id
        ORDER BY b.generated_ts DESC, b.brief_id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def fetch_brief_thread(conn: sqlite3.Connection, *, brief_id: str) -> list[dict]:
    """Walk parent_brief_id upward, then reverse so the original is first."""
    chain: list[dict] = []
    current: Optional[str] = brief_id
    while current is not None:
        row = conn.execute(
            "SELECT * FROM briefs WHERE brief_id = ?", (current,)
        ).fetchone()
        if row is None:
            break
        chain.append(dict(row))
        current = row["parent_brief_id"]
    return list(reversed(chain))
