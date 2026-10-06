"""The user database: everything that is yours rather than the market's.

Saved screens, custom ratios, watchlists, alerts and the alert inbox live in one
SQLite file, ``screener_db_path`` (``TRADINGAGENTS_SCREENER_DB``, default
``~/.tradingagents/screener/screens.db``), apart from the India database, so
rebuilding or re-syncing the market data never touches them. Phase 3 already
kept screens and ratios here, and nothing of the user's was ever written to the
India database, so no data has to move.

The schema is versioned with ``PRAGMA user_version``:

    0  Phase 3's file: screens, custom_ratios
    1  adds watchlists, watchlist_items, alerts and alert_events

``connect`` brings an older file up to date in place. Each step only creates
what is missing, inside one transaction that also sets the new version, so a
step that fails leaves the file as it was, a second run (or a second process
racing the first) changes nothing, and existing rows are never rewritten.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from tradingagents.dataflows.config import get_config

SCREENS = (
    """CREATE TABLE IF NOT EXISTS screens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', query TEXT NOT NULL,
    columns TEXT NOT NULL DEFAULT '[]',   -- JSON list of column ids
    sort TEXT,                            -- JSON {"key": column id, "dir": "asc" | "desc"}
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
)""",
    """CREATE TABLE IF NOT EXISTS custom_ratios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL, key TEXT NOT NULL UNIQUE,   -- key: the name normalised (lower case, single spaces)
    expression TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
)""",
)

WATCHLISTS_AND_ALERTS = (
    """CREATE TABLE IF NOT EXISTS watchlists (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    position INTEGER NOT NULL DEFAULT 0,      -- order among the watchlists
    columns TEXT NOT NULL DEFAULT '[]',       -- JSON list of column ids, as a screen's
    sort TEXT,                                -- JSON {"key": column id, "dir": "asc" | "desc"}
    holdings INTEGER NOT NULL DEFAULT 0,      -- 1: rows carry a quantity and an average price
    cash REAL,                                -- free cash, for the portfolio built from the holdings
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
)""",
    """CREATE TABLE IF NOT EXISTS watchlist_items (
    watchlist_id INTEGER NOT NULL REFERENCES watchlists (id) ON DELETE CASCADE,
    isin TEXT NOT NULL,
    symbol TEXT NOT NULL,                     -- RELIANCE.NS, or 500325.BO for a BSE-only stock
    name TEXT,
    note TEXT NOT NULL DEFAULT '',
    quantity REAL, avg_price REAL,            -- holdings mode only
    added_at TEXT NOT NULL,
    PRIMARY KEY (watchlist_id, isin)
)""",
    """CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,                       -- price | metric | screen | filing | shareholding
    name TEXT NOT NULL,
    isin TEXT, symbol TEXT,                   -- the stock it watches
    watchlist_id INTEGER,                     -- or a watchlist's stocks (filing, shareholding)
    params TEXT NOT NULL DEFAULT '{}',        -- JSON: the kind's settings (a screen alert's screen id too)
    enabled INTEGER NOT NULL DEFAULT 1,
    cooldown_minutes INTEGER NOT NULL DEFAULT 0,
    expires_on TEXT,                          -- YYYY-MM-DD: the last day it is evaluated
    state TEXT,                               -- JSON: what the last evaluation saw (the edge trigger's memory)
    status TEXT,                              -- JSON: the last evaluation's outcome, for the page
    last_evaluated_at TEXT, last_fired_at TEXT,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
)""",
    """CREATE TABLE IF NOT EXISTS alert_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alert_id INTEGER REFERENCES alerts (id) ON DELETE SET NULL,
    alert_name TEXT NOT NULL, kind TEXT NOT NULL,
    dedupe TEXT NOT NULL,                     -- what fired; evaluating the same data again finds it already here
    fired_at TEXT NOT NULL,
    data_date TEXT,                           -- the data it fired on: a trading day, or a snapshot's
    title TEXT NOT NULL, body TEXT NOT NULL DEFAULT '',
    detail TEXT NOT NULL DEFAULT '{}',        -- JSON: the values that tripped it
    symbol TEXT,
    read_at TEXT,
    delivery TEXT NOT NULL DEFAULT '{}'       -- JSON: channel -> {"ok", "error", "at"}
)""",
    "CREATE UNIQUE INDEX IF NOT EXISTS alert_events_once ON alert_events (alert_id, dedupe)",
    "CREATE INDEX IF NOT EXISTS alert_events_fired ON alert_events (fired_at)",
)

# (version reached, statements). Every statement creates only what is missing.
MIGRATIONS = ((1, SCREENS + WATCHLISTS_AND_ALERTS),)
VERSION = MIGRATIONS[-1][0]


def db_path() -> Path:
    return Path(get_config()["screener_db_path"]).expanduser()


def version(conn) -> int:
    return conn.execute("PRAGMA user_version").fetchone()[0]


def upgrade(conn) -> list[int]:
    """Bring the file's schema up to ``VERSION``; the versions it stepped through."""
    done = []
    for target, statements in MIGRATIONS:
        if version(conn) >= target:
            continue
        conn.execute("BEGIN IMMEDIATE")  # the write lock first, so two processes cannot both step
        try:
            if version(conn) < target:
                for statement in statements:
                    conn.execute(statement)
                conn.execute(f"PRAGMA user_version = {int(target)}")
                done.append(target)
            conn.execute("COMMIT")
        except BaseException:
            conn.rollback()
            raise
    return done


def connect(path: str | Path | None = None) -> sqlite3.Connection:
    path = Path(path) if path else db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    upgrade(conn)
    return conn
