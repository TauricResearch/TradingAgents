"""Costs panel — daily cost / token trend chart."""

from __future__ import annotations

import sqlite3


def fetch_daily_cost_trend(conn: sqlite3.Connection, *, days: int = 30) -> list[dict]:
    rows = conn.execute(
        """
        SELECT substr(r.started_ts, 1, 10) AS day,
               c.model AS model,
               SUM(c.usd_estimate) AS total_usd,
               SUM(c.in_tokens) AS in_tokens,
               SUM(c.out_tokens) AS out_tokens,
               SUM(COALESCE(c.cache_hit_tokens, 0)) AS cache_hit_tokens,
               SUM(COALESCE(c.cache_miss_tokens, 0)) AS cache_miss_tokens
        FROM costs c
        JOIN runs r ON r.run_id = c.run_id
        -- datetime(r.started_ts): ISO 'T'+offset must be normalized before
        -- comparing to datetime('now', ?), else same-day rows are mis-filtered.
        WHERE datetime(r.started_ts) > datetime('now', ?)
        GROUP BY day, c.model
        ORDER BY day ASC, c.model ASC
        """,
        (f"-{int(days)} days",),
    ).fetchall()
    out = []
    for row in rows:
        item = dict(row)
        hit = int(item.get("cache_hit_tokens") or 0)
        miss = int(item.get("cache_miss_tokens") or 0)
        total = hit + miss
        item["cache_hit_ratio"] = (hit / total) if total > 0 else None
        out.append(item)
    return out
