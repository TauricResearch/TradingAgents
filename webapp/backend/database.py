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
from datetime import datetime, timezone
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
                plan TEXT NOT NULL DEFAULT 'free',
                stripe_customer_id TEXT,
                stripe_subscription_id TEXT,
                created_at TEXT NOT NULL
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
                created_at TEXT NOT NULL,
                finished_at TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_jobs_user ON jobs(user_id);
            """
        )


def create_user(email: str) -> sqlite3.Row:
    api_key = "ta_" + secrets.token_urlsafe(32)
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


def jobs_this_month(user_id: int) -> int:
    month_prefix = datetime.now(timezone.utc).strftime("%Y-%m")
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM jobs WHERE user_id = ? AND created_at LIKE ?",
            (user_id, f"{month_prefix}%"),
        ).fetchone()
        return row["n"]


def create_job(job_id: str, user_id: int, ticker: str, trade_date: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO jobs (id, user_id, ticker, trade_date, status, created_at) "
            "VALUES (?, ?, ?, ?, 'queued', ?)",
            (job_id, user_id, ticker, trade_date, _now()),
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


def list_jobs(user_id: int, limit: int = 20) -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            "SELECT id, ticker, trade_date, status, decision, created_at, finished_at "
            "FROM jobs WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
