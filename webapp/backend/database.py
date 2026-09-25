"""SQLite storage for accounts, API keys, and analysis jobs.

Kept intentionally simple (stdlib sqlite3, no ORM) since the webapp is a thin
monetization layer on top of the existing ``tradingagents`` package, not a
service meant to scale past a single small deployment out of the box.
"""

from __future__ import annotations

import os
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path


def db_path() -> Path:
    """Resolve the sqlite file path from the environment on every call.

    Read lazily (rather than cached at import time) so tests can point each
    run at an isolated file via ``monkeypatch.setenv`` without needing to
    reimport this module.
    """
    return Path(
        os.environ.get(
            "TRADINGAGENTS_WEBAPP_DB",
            str(Path.home() / ".tradingagents" / "webapp.sqlite3"),
        )
    )


def free_tier_monthly_limit() -> int:
    """Free-tier monthly quota; overridable so an operator can tune it
    without a code change. Paid plans bypass this check entirely (see
    billing.py). Read lazily for the same reason as ``db_path``."""
    return int(os.environ.get("TRADINGAGENTS_FREE_TIER_LIMIT", "5"))


def cache_ttl_hours() -> float:
    """How long a completed (ticker, trade_date) result is reused across
    *all* users instead of re-running the LLM pipeline. The result for a
    given historical trade_date is effectively static, so this mainly bounds
    how long a stale/incorrect run stays cached rather than modeling data
    freshness. 0 disables the cache. Read lazily for the same reason as
    ``db_path``."""
    return float(os.environ.get("TRADINGAGENTS_CACHE_TTL_HOURS", "24"))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def get_conn():
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                api_key TEXT UNIQUE NOT NULL,
                display_name TEXT,
                currency TEXT NOT NULL DEFAULT 'USD',
                plan TEXT NOT NULL DEFAULT 'free',
                stripe_customer_id TEXT,
                stripe_subscription_id TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS watchlist (
                user_id INTEGER NOT NULL REFERENCES users(id),
                ticker TEXT NOT NULL,
                added_at TEXT NOT NULL,
                PRIMARY KEY (user_id, ticker)
            );

            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                ticker TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'queued',
                decision TEXT,
                report TEXT,
                error TEXT,
                cached INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                finished_at TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_jobs_user ON jobs(user_id);
            CREATE INDEX IF NOT EXISTS idx_jobs_ticker_date ON jobs(ticker, trade_date, status);
            """
        )


def _new_api_key() -> str:
    return "ta_" + secrets.token_urlsafe(32)


def create_user(email: str) -> sqlite3.Row:
    api_key = _new_api_key()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO users (email, api_key, plan, created_at) VALUES (?, ?, 'free', ?)",
            (email, api_key, _now()),
        )
        return conn.execute(
            "SELECT * FROM users WHERE email = ?", (email,)
        ).fetchone()


def get_user_by_api_key(api_key: str) -> sqlite3.Row | None:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM users WHERE api_key = ?", (api_key,)
        ).fetchone()


def get_user_by_email(email: str) -> sqlite3.Row | None:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM users WHERE email = ?", (email,)
        ).fetchone()


def set_user_plan(user_id: int, plan: str, stripe_customer_id: str | None = None,
                   stripe_subscription_id: str | None = None) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET plan = ?, stripe_customer_id = COALESCE(?, stripe_customer_id), "
            "stripe_subscription_id = COALESCE(?, stripe_subscription_id) WHERE id = ?",
            (plan, stripe_customer_id, stripe_subscription_id, user_id),
        )


def update_display_name(user_id: int, display_name: str | None) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET display_name = ? WHERE id = ?",
            (display_name or None, user_id),
        )


def update_currency(user_id: int, currency: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET currency = ? WHERE id = ?",
            (currency.upper(), user_id),
        )


def regenerate_api_key(user_id: int) -> str:
    """Rotate a user's API key. The old key stops working immediately —
    intentional: this is the "I think my key leaked" escape hatch, so a
    grace period would defeat the point."""
    new_key = _new_api_key()
    with get_conn() as conn:
        conn.execute("UPDATE users SET api_key = ? WHERE id = ?", (new_key, user_id))
    return new_key


def jobs_this_month(user_id: int) -> int:
    """Count of this user's runs this month that count against their quota.
    Cache hits (``cached = 1``) are excluded: they cost nothing to serve, so
    they shouldn't count against a free-tier user's limit."""
    month_prefix = datetime.now(timezone.utc).strftime("%Y-%m")
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM jobs WHERE user_id = ? AND created_at LIKE ? "
            "AND cached = 0",
            (user_id, f"{month_prefix}%"),
        ).fetchone()
        return row["n"]


def user_stats(user_id: int) -> dict:
    """Lifetime counters for the Dashboard's stat cards — real aggregates
    over this user's own job history, not derived/estimated numbers."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT "
            "  COUNT(*) AS total, "
            "  SUM(CASE WHEN status = 'done' THEN 1 ELSE 0 END) AS done, "
            "  SUM(CASE WHEN cached = 1 THEN 1 ELSE 0 END) AS cached, "
            "  COUNT(DISTINCT ticker) AS distinct_tickers "
            "FROM jobs WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        watchlist_count = conn.execute(
            "SELECT COUNT(*) AS n FROM watchlist WHERE user_id = ?", (user_id,)
        ).fetchone()["n"]
    return {
        "total_jobs": row["total"] or 0,
        "done_jobs": row["done"] or 0,
        "cached_jobs": row["cached"] or 0,
        "distinct_tickers": row["distinct_tickers"] or 0,
        "watchlist_count": watchlist_count,
    }


def create_job(job_id: str, user_id: int, ticker: str, trade_date: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO jobs (id, user_id, ticker, trade_date, status, created_at) "
            "VALUES (?, ?, ?, ?, 'queued', ?)",
            (job_id, user_id, ticker, trade_date, _now()),
        )


def find_recent_completed_job(ticker: str, trade_date: str) -> sqlite3.Row | None:
    """Most recent successful run for this (ticker, trade_date) across any
    user, within ``cache_ttl_hours()``. Used to skip a redundant, costly LLM
    pipeline run when someone already paid for this exact result recently."""
    ttl = cache_ttl_hours()
    if ttl <= 0:
        return None
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=ttl)).isoformat()
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM jobs WHERE ticker = ? AND trade_date = ? AND status = 'done' "
            "AND created_at >= ? ORDER BY created_at DESC LIMIT 1",
            (ticker, trade_date, cutoff),
        ).fetchone()


def create_cached_job(job_id: str, user_id: int, source_job: sqlite3.Row) -> None:
    """Record a cache hit as a completed job for ``user_id`` without running
    the pipeline again, so it shows up in their history and counts as done
    immediately — but doesn't consume any compute."""
    now = _now()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO jobs (id, user_id, ticker, trade_date, status, decision, report, "
            "cached, created_at, finished_at) VALUES (?, ?, ?, ?, 'done', ?, ?, 1, ?, ?)",
            (
                job_id,
                user_id,
                source_job["ticker"],
                source_job["trade_date"],
                source_job["decision"],
                source_job["report"],
                now,
                now,
            ),
        )


def update_job(job_id: str, **fields) -> None:
    if not fields:
        return
    columns = ", ".join(f"{k} = ?" for k in fields)
    with get_conn() as conn:
        conn.execute(
            f"UPDATE jobs SET {columns} WHERE id = ?",
            (*fields.values(), job_id),
        )


def get_job(job_id: str, user_id: int) -> sqlite3.Row | None:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM jobs WHERE id = ? AND user_id = ?", (job_id, user_id)
        ).fetchone()


def list_jobs(
    user_id: int,
    limit: int = 20,
    offset: int = 0,
    ticker: str | None = None,
    status: str | None = None,
) -> list[sqlite3.Row]:
    query = (
        "SELECT id, ticker, trade_date, status, decision, cached, created_at, finished_at "
        "FROM jobs WHERE user_id = ?"
    )
    params: list = [user_id]
    if ticker:
        query += " AND ticker = ?"
        params.append(ticker.upper())
    if status:
        query += " AND status = ?"
        params.append(status)
    query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params += [limit, offset]
    with get_conn() as conn:
        return conn.execute(query, params).fetchall()


def add_watchlist_ticker(user_id: int, ticker: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO watchlist (user_id, ticker, added_at) VALUES (?, ?, ?)",
            (user_id, ticker.upper(), _now()),
        )


def remove_watchlist_ticker(user_id: int, ticker: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "DELETE FROM watchlist WHERE user_id = ? AND ticker = ?",
            (user_id, ticker.upper()),
        )


def list_watchlist(user_id: int) -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            "SELECT ticker, added_at FROM watchlist WHERE user_id = ? ORDER BY added_at DESC",
            (user_id,),
        ).fetchall()
