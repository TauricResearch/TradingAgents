"""Actions panel — pending + recently actioned brief_actions."""

from __future__ import annotations

import sqlite3


def fetch_pending_actions(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM brief_actions WHERE state = 'pending' "
        "ORDER BY expires_at ASC"
    ).fetchall()
    return [dict(r) for r in rows]


def fetch_recent_actioned(conn: sqlite3.Connection, *, limit: int = 20) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM brief_actions WHERE state != 'pending' "
        "ORDER BY action_id DESC LIMIT ?", (limit,)
    ).fetchall()
    return [dict(r) for r in rows]
