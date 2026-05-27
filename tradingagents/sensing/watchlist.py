"""Watchlist write paths — user-curated, auto-promote, sweep.

User-curated entries (ttl_until IS NULL) are permanent. Auto-promoted
entries refresh their TTL on every triggering event. The hourly sweep
prunes rows whose TTL has passed *and* are not user-curated.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone, timedelta
from typing import Iterable


def add_user(
    conn: sqlite3.Connection, *, ticker: str, extra_tags: Iterable[str] = (),
) -> None:
    """User-curated add via CLI. ttl_until=None means never expires."""
    from tradingagents.persistence.store import upsert_watchlist
    tags = ["user", *extra_tags]
    upsert_watchlist(conn, ticker=ticker, ttl_until=None, tags=tags)


def auto_promote(
    conn: sqlite3.Connection,
    *,
    ticker: str,
    event_id: str,
    salience: float,
    confidence: float,
    salience_threshold: float,
    confidence_threshold: float,
    ttl_days: int,
) -> int:
    """Promote a ticker if it clears both thresholds. Returns 1 if upserted, 0 otherwise.

    A pre-existing user-curated entry is NOT overwritten — only its
    ``last_briefed`` timestamp advances (via the upsert helper).
    """
    if salience < salience_threshold or confidence < confidence_threshold:
        return 0

    from tradingagents.persistence.store import upsert_watchlist

    existing = conn.execute(
        "SELECT tags FROM watchlist WHERE ticker = ?", (ticker,)
    ).fetchone()
    user_curated = (
        existing is not None
        and "user" in (json.loads(existing["tags"]) if existing["tags"] else [])
    )
    if user_curated:
        # Refresh last_briefed only; keep ttl_until = NULL.
        upsert_watchlist(conn, ticker=ticker, ttl_until=None,
                         tags=["user", f"event:{event_id}"])
        return 0

    ttl_until = (datetime.now(timezone.utc) + timedelta(days=ttl_days)).isoformat()
    upsert_watchlist(
        conn, ticker=ticker, ttl_until=ttl_until,
        tags=["auto", f"event:{event_id}"],
    )
    return 1


def sweep_expired(conn: sqlite3.Connection) -> int:
    """Delete expired auto-rows. Returns the row count removed.

    User-curated entries (ttl_until IS NULL OR tags ∋ 'user') are preserved.
    """
    # Wrap LHS in datetime() so ISO `T` separator + `+00:00` suffix parse
    # consistently against SQLite's `datetime('now')`. Plain string comparison
    # silently fails when both timestamps land on the same day.
    cur = conn.execute(
        "DELETE FROM watchlist "
        "WHERE ttl_until IS NOT NULL "
        "  AND datetime(ttl_until) < datetime('now') "
        "  AND tags NOT LIKE '%\"user\"%'"
    )
    conn.commit()
    return cur.rowcount
