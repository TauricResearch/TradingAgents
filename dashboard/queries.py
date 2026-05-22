"""
dashboard/queries.py — All SQLite queries for the trading dashboard.

DB path is read from the HERMES_DB_PATH environment variable.
Default: /opt/data/hermes.db
"""

import logging
import os
import sqlite3
import warnings
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

_DB_PATH = os.environ.get("HERMES_DB_PATH", "/opt/data/hermes.db")


def get_db_connection() -> Optional[sqlite3.Connection]:
    """Return a sqlite3 connection, or None if the DB file cannot be opened."""
    db_path = os.environ.get("HERMES_DB_PATH", _DB_PATH)
    if not os.path.exists(db_path):
        warnings.warn(
            f"Database not found at {db_path!r}. "
            "Set HERMES_DB_PATH to the correct path.",
            RuntimeWarning,
            stacklevel=2,
        )
        return None
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.OperationalError as exc:
        warnings.warn(
            f"Cannot open database at {db_path!r}: {exc}",
            RuntimeWarning,
            stacklevel=2,
        )
        return None


def get_equity_curve() -> pd.DataFrame:
    """Return daily_snapshots ordered by date.

    Columns: date, account_equity, realized_pnl, unrealized_pnl
    Returns an empty DataFrame on failure.
    """
    conn = get_db_connection()
    if conn is None:
        return pd.DataFrame(
            columns=["date", "account_equity", "realized_pnl", "unrealized_pnl"]
        )
    try:
        df = pd.read_sql_query(
            """
            SELECT date, account_equity, realized_pnl, unrealized_pnl
            FROM daily_snapshots
            ORDER BY date ASC
            """,
            conn,
        )
        return df
    except Exception as exc:
        logger.warning("get_equity_curve failed: %s", exc)
        return pd.DataFrame(
            columns=["date", "account_equity", "realized_pnl", "unrealized_pnl"]
        )
    finally:
        conn.close()


def get_open_positions() -> list[dict]:
    """Return trades with outcome='open' as a list of dicts.

    Returns an empty list on failure.
    """
    conn = get_db_connection()
    if conn is None:
        return []
    try:
        cursor = conn.execute(
            """
            SELECT id, ticker, date_open, entry_price, stop_price,
                   target_price, shares, signal, regime, notes
            FROM trades
            WHERE outcome = 'open'
            ORDER BY date_open DESC
            """
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    except Exception as exc:
        logger.warning("get_open_positions failed: %s", exc)
        return []
    finally:
        conn.close()


def get_recent_trades(n: int = 10) -> pd.DataFrame:
    """Return the last N closed trades (all columns).

    Closed means outcome IN ('win', 'loss', 'cancelled').
    Returns an empty DataFrame on failure.
    """
    conn = get_db_connection()
    if conn is None:
        return pd.DataFrame()
    try:
        df = pd.read_sql_query(
            """
            SELECT *
            FROM trades
            WHERE outcome IN ('win', 'loss', 'cancelled')
            ORDER BY date_close DESC
            LIMIT ?
            """,
            conn,
            params=(n,),
        )
        return df
    except Exception as exc:
        logger.warning("get_recent_trades failed: %s", exc)
        return pd.DataFrame()
    finally:
        conn.close()


def get_stats_summary() -> dict:
    """Return aggregated account stats.

    Keys:
        total_trades        int   — closed trades (win + loss)
        win_rate            float — percentage 0-100
        total_pnl_dollars   float
        total_pnl_pct       float — sum of individual trade pnl_pct
        current_equity      float — latest account_equity from daily_snapshots
        open_positions_count int
        account_heat        float — sum of open position risk as % of current equity
    """
    defaults = {
        "total_trades": 0,
        "win_rate": 0.0,
        "total_pnl_dollars": 0.0,
        "total_pnl_pct": 0.0,
        "current_equity": 0.0,
        "open_positions_count": 0,
        "account_heat": 0.0,
    }
    conn = get_db_connection()
    if conn is None:
        return defaults

    try:
        # Closed trade stats
        row = conn.execute(
            """
            SELECT
                COUNT(*)                                        AS total_trades,
                COALESCE(SUM(CASE WHEN outcome='win' THEN 1 ELSE 0 END), 0) AS wins,
                COALESCE(SUM(pnl_dollars), 0.0)                AS total_pnl_dollars,
                COALESCE(SUM(pnl_pct), 0.0)                   AS total_pnl_pct
            FROM trades
            WHERE outcome IN ('win', 'loss')
            """
        ).fetchone()
        total = row["total_trades"] or 0
        wins = row["wins"] or 0
        win_rate = (wins / total * 100) if total > 0 else 0.0

        # Latest equity
        equity_row = conn.execute(
            """
            SELECT account_equity
            FROM daily_snapshots
            ORDER BY date DESC
            LIMIT 1
            """
        ).fetchone()
        current_equity = equity_row["account_equity"] if equity_row else 0.0

        # Open positions
        open_count_row = conn.execute(
            "SELECT COUNT(*) AS cnt FROM trades WHERE outcome='open'"
        ).fetchone()
        open_count = open_count_row["cnt"] if open_count_row else 0

        # Account heat: sum of (entry_price - stop_price) * shares / equity
        # for all open trades where entry_price and stop_price are set
        heat = 0.0
        if current_equity and current_equity > 0:
            heat_row = conn.execute(
                """
                SELECT COALESCE(SUM(
                    (entry_price - stop_price) * shares
                ), 0.0) AS raw_risk
                FROM trades
                WHERE outcome = 'open'
                  AND entry_price IS NOT NULL
                  AND stop_price IS NOT NULL
                  AND shares IS NOT NULL
                """
            ).fetchone()
            raw_risk = heat_row["raw_risk"] if heat_row else 0.0
            heat = abs(raw_risk) / current_equity * 100

        return {
            "total_trades": total,
            "win_rate": round(win_rate, 1),
            "total_pnl_dollars": round(row["total_pnl_dollars"], 2),
            "total_pnl_pct": round(row["total_pnl_pct"], 2),
            "current_equity": round(current_equity, 2),
            "open_positions_count": open_count,
            "account_heat": round(heat, 1),
        }
    except Exception as exc:
        logger.warning("get_stats_summary failed: %s", exc)
        return defaults
    finally:
        conn.close()


def get_analyst_performance() -> pd.DataFrame:
    """Return per-analyst win_rate and total_signals.

    Columns: analyst_name, win_rate, total_signals
    Returns an empty DataFrame on failure.
    """
    conn = get_db_connection()
    if conn is None:
        return pd.DataFrame(columns=["analyst_name", "win_rate", "total_signals"])
    try:
        df = pd.read_sql_query(
            """
            SELECT
                analyst_name,
                COUNT(*)                                                  AS total_signals,
                ROUND(
                    100.0 * SUM(CASE WHEN outcome='win' THEN 1 ELSE 0 END)
                    / NULLIF(COUNT(*), 0),
                    1
                )                                                         AS win_rate
            FROM analyst_performance
            WHERE outcome IS NOT NULL
            GROUP BY analyst_name
            ORDER BY win_rate DESC
            """,
            conn,
        )
        return df
    except Exception as exc:
        logger.warning("get_analyst_performance failed: %s", exc)
        return pd.DataFrame(columns=["analyst_name", "win_rate", "total_signals"])
    finally:
        conn.close()


def get_pnl_distribution() -> "pd.Series":
    """Return pnl_pct values for all closed trades as a Series.

    Returns an empty Series on failure.
    """
    conn = get_db_connection()
    if conn is None:
        return pd.Series(dtype=float, name="pnl_pct")
    try:
        df = pd.read_sql_query(
            """
            SELECT pnl_pct
            FROM trades
            WHERE outcome IN ('win', 'loss')
              AND pnl_pct IS NOT NULL
            ORDER BY date_close
            """,
            conn,
        )
        return df["pnl_pct"]
    except Exception as exc:
        logger.warning("get_pnl_distribution failed: %s", exc)
        return pd.Series(dtype=float, name="pnl_pct")
    finally:
        conn.close()
