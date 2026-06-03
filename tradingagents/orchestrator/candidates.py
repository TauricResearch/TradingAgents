"""Promoter candidate query — selects triaged events worth firing as alerts.

Predicate: event.status='triaged' AND event.salience >= S AND
           event_ticker.confidence >= C AND ticker ∈ watchlist AND
           not currently suppressed AND not already enqueued.

Ordered oldest-first so the oldest qualifying event fires first.
"""

from __future__ import annotations

import sqlite3
from typing import List


_QUERY = """
SELECT e.event_id, et.ticker, e.salience, et.confidence, e.ingested_ts
FROM events e
JOIN event_ticker et   ON et.event_id = e.event_id
JOIN watchlist  w      ON w.ticker     = et.ticker
LEFT JOIN suppression s ON s.key = 'event_alert:' || et.ticker
                       AND datetime(s.until_ts) > datetime('now')
LEFT JOIN queue_jobs q ON q.trigger_event_id = e.event_id
WHERE e.status = 'triaged'
  AND e.salience >= ?
  AND et.confidence >= ?
  AND s.key IS NULL
  AND q.job_id IS NULL
ORDER BY e.ingested_ts ASC
LIMIT ?
"""


def fetch_candidates(
    conn: sqlite3.Connection,
    *,
    salience_threshold: float,
    ticker_conf_threshold: float,
    limit: int,
) -> List[sqlite3.Row]:
    return list(
        conn.execute(
            _QUERY,
            (salience_threshold, ticker_conf_threshold, limit),
        )
    )


def fetch_candidates_grouped(
    conn: sqlite3.Connection,
    *,
    salience_threshold: float,
    ticker_conf_threshold: float,
    limit: int,
) -> List[dict]:
    """Like fetch_candidates, but groups the per-(event,ticker) rows into one
    dict per event: {event_id, ingested_ts, salience, tickers: [...]}. Preserves
    event order (oldest-first). ``limit`` bounds the number of underlying rows."""
    rows = fetch_candidates(
        conn,
        salience_threshold=salience_threshold,
        ticker_conf_threshold=ticker_conf_threshold,
        limit=limit,
    )
    grouped: "dict[str, dict]" = {}
    for r in rows:
        g = grouped.get(r["event_id"])
        if g is None:
            g = {
                "event_id": r["event_id"],
                "ingested_ts": r["ingested_ts"],
                "salience": r["salience"],
                "tickers": [],
            }
            grouped[r["event_id"]] = g
        g["tickers"].append(r["ticker"])
    return list(grouped.values())
