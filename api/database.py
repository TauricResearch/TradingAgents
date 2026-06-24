import json
import logging
import sqlite3
import datetime
from typing import Optional

import yfinance as yf

from api.config import DB_PATH, GLOBAL_TICKERS, TICKER_NAMES
from api.models import SignalPayload

logger = logging.getLogger("pulse-trading-signals-service")


def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_db_connection()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS watchlist_tickers (
                ticker VARCHAR(10) PRIMARY KEY,
                asset_type VARCHAR(10) NOT NULL,
                added_at DATETIME NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS trading_signals (
                id VARCHAR(36) PRIMARY KEY,
                ticker VARCHAR(10) NOT NULL,
                asset_type VARCHAR(10) NOT NULL,
                signal_type VARCHAR(20) NOT NULL,
                confidence FLOAT NOT NULL,
                time_horizon VARCHAR(50),
                price_target FLOAT,
                entry_price FLOAT,
                stop_loss FLOAT,
                position_sizing VARCHAR(50),
                reasoning_summary TEXT NOT NULL,
                generated_at DATETIME NOT NULL,
                source_run_id VARCHAR(100),
                name TEXT,
                grade TEXT,
                rr FLOAT,
                agent_votes TEXT,
                sentiment_score FLOAT,
                sentiment_band TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_quota_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id VARCHAR(100) NOT NULL,
                viewed_at DATETIME NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_watchlist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id VARCHAR(100) NOT NULL,
                ticker VARCHAR(10) NOT NULL,
                asset_type VARCHAR(10) NOT NULL,
                added_at DATETIME NOT NULL,
                UNIQUE(user_id, ticker)
            )
        """)
        # Safe migrations: add columns to existing tables (silently ignored if already present)
        for col, col_type in [
            ("name", "TEXT"),
            ("grade", "TEXT"),
            ("rr", "FLOAT"),
            ("agent_votes", "TEXT"),
            ("sentiment_score", "FLOAT"),
            ("sentiment_band", "TEXT"),
            # Raw agent reports
            ("market_report", "TEXT"),
            ("news_report", "TEXT"),
            ("fundamentals_report", "TEXT"),
            ("sentiment_report", "TEXT"),
            ("pm_report", "TEXT"),
            ("trader_report", "TEXT"),
            ("investment_debate", "TEXT"),
            ("risk_debate", "TEXT"),
        ]:
            try:
                conn.execute(f"ALTER TABLE trading_signals ADD COLUMN {col} {col_type}")
            except Exception:
                pass
        conn.commit()
        logger.info("Database verified at: %s", DB_PATH)
    except Exception as e:
        logger.error("Database init error: %s", e)
    finally:
        conn.close()


def seed_global_watchlist() -> None:
    conn = get_db_connection()
    try:
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for ticker, asset_type in GLOBAL_TICKERS:
            conn.execute(
                "INSERT OR IGNORE INTO watchlist_tickers (ticker, asset_type, added_at) VALUES (?, ?, ?)",
                (ticker, asset_type, now),
            )
        conn.commit()
        logger.info("Global watchlist seeded with %d tickers.", len(GLOBAL_TICKERS))
    finally:
        conn.close()


def _row_to_signal(row) -> SignalPayload:
    gen_at_str = row["generated_at"]
    fmt = "%Y-%m-%d %H:%M:%S" if "." not in gen_at_str else "%Y-%m-%d %H:%M:%S.%f"

    agent_votes = None
    try:
        if row["agent_votes"]:
            agent_votes = json.loads(row["agent_votes"])
    except Exception:
        pass

    name = row["name"] or TICKER_NAMES.get(
        row["ticker"].replace("-USD", ""), row["ticker"]
    )

    return SignalPayload(
        id=row["id"],
        ticker=row["ticker"],
        asset_type=row["asset_type"],
        name=name,
        signal_type=row["signal_type"],
        confidence=row["confidence"],
        time_horizon=row["time_horizon"],
        price_target=row["price_target"],
        entry_price=row["entry_price"],
        stop_loss=row["stop_loss"],
        position_sizing=row["position_sizing"],
        reasoning_summary=row["reasoning_summary"],
        generated_at=datetime.datetime.strptime(gen_at_str, fmt),
        source_run_id=row["source_run_id"],
        grade=row["grade"],
        rr=row["rr"],
        agent_votes=agent_votes,
        sentiment_score=row["sentiment_score"],
        sentiment_band=row["sentiment_band"],
        market_report=row["market_report"],
        news_report=row["news_report"],
        fundamentals_report=row["fundamentals_report"],
        sentiment_report=row["sentiment_report"],
        pm_report=row["pm_report"],
        trader_report=row["trader_report"],
        investment_debate=row["investment_debate"],
        risk_debate=row["risk_debate"],
    )


# ---------------------------------------------------------------------------
# Price helpers
# ---------------------------------------------------------------------------


def _yf_symbol(ticker: str, asset_type: str) -> str:
    if asset_type == "crypto" and not ticker.endswith("-USD"):
        return f"{ticker}-USD"
    return ticker


def get_live_price(ticker: str, asset_type: str) -> Optional[float]:
    try:
        return float(yf.Ticker(_yf_symbol(ticker, asset_type)).fast_info.last_price)
    except Exception:
        return None


def validate_price(
    price: Optional[float], live_price: Optional[float]
) -> Optional[float]:
    if price is None or live_price is None or live_price == 0:
        return price
    ratio = price / live_price
    return price if 0.1 <= ratio <= 10 else None
