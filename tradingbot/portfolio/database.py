"""SQLite persistence layer for portfolio state."""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from .models import PortfolioSnapshot, TradeRecord

logger = logging.getLogger(__name__)


class PortfolioDatabase:
    """
    Thin SQLite wrapper that handles schema creation and CRUD for
    TradeRecord and PortfolioSnapshot rows.

    Uses standard library sqlite3 (no extra deps).
    """

    _SCHEMA = """
    CREATE TABLE IF NOT EXISTS trades (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        ticker          TEXT    NOT NULL,
        side            TEXT    NOT NULL,
        qty             REAL    NOT NULL,
        price           REAL    NOT NULL,
        total_value     REAL    NOT NULL,
        signal          TEXT    NOT NULL,
        agent_reasoning TEXT    NOT NULL,
        order_id        TEXT    NOT NULL,
        trade_date      TEXT    NOT NULL,
        timestamp       TEXT    NOT NULL
    );

    CREATE TABLE IF NOT EXISTS snapshots (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        snapshot_date   TEXT    NOT NULL UNIQUE,
        cash            REAL    NOT NULL,
        invested_value  REAL    NOT NULL,
        total_value     REAL    NOT NULL,
        daily_pnl       REAL    NOT NULL,
        daily_pnl_pct   REAL    NOT NULL,
        open_positions  INTEGER NOT NULL,
        timestamp       TEXT    NOT NULL
    );

    CREATE TABLE IF NOT EXISTS closed_positions (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        ticker          TEXT    NOT NULL,
        entry_price     REAL    NOT NULL,
        exit_price      REAL    NOT NULL,
        qty             REAL    NOT NULL,
        realized_pnl    REAL    NOT NULL,
        realized_pnl_pct REAL   NOT NULL,
        entry_date      TEXT    NOT NULL,
        exit_date       TEXT    NOT NULL,
        holding_days    INTEGER NOT NULL,
        entry_signal    TEXT,
        exit_signal     TEXT,
        timestamp       TEXT    NOT NULL
    );
    """

    def __init__(self, db_path: str):
        self._db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()
        logger.info("PortfolioDatabase ready at %s", db_path)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(self._SCHEMA)

    # ------------------------------------------------------------------ #
    # Trades                                                               #
    # ------------------------------------------------------------------ #

    def insert_trade(self, trade: TradeRecord) -> int:
        sql = """
        INSERT INTO trades
            (ticker, side, qty, price, total_value, signal, agent_reasoning,
             order_id, trade_date, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        with self._connect() as conn:
            cur = conn.execute(sql, (
                trade.ticker,
                trade.side,
                trade.qty,
                trade.price,
                trade.total_value,
                trade.signal,
                trade.agent_reasoning,
                trade.order_id,
                trade.trade_date,
                trade.timestamp.isoformat(),
            ))
            trade.id = cur.lastrowid
            return trade.id

    def get_trades(
        self,
        ticker: Optional[str] = None,
        limit: int = 200,
    ) -> List[TradeRecord]:
        if ticker:
            sql = "SELECT * FROM trades WHERE ticker = ? ORDER BY timestamp DESC LIMIT ?"
            params = (ticker.upper(), limit)
        else:
            sql = "SELECT * FROM trades ORDER BY timestamp DESC LIMIT ?"
            params = (limit,)

        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()

        return [self._row_to_trade(r) for r in rows]

    def _row_to_trade(self, row: sqlite3.Row) -> TradeRecord:
        return TradeRecord(
            id=row["id"],
            ticker=row["ticker"],
            side=row["side"],
            qty=row["qty"],
            price=row["price"],
            total_value=row["total_value"],
            signal=row["signal"],
            agent_reasoning=row["agent_reasoning"],
            order_id=row["order_id"],
            trade_date=row["trade_date"],
            timestamp=datetime.fromisoformat(row["timestamp"]),
        )

    # ------------------------------------------------------------------ #
    # Closed positions (for P&L calculation and reflection)               #
    # ------------------------------------------------------------------ #

    def record_closed_position(
        self,
        ticker: str,
        entry_price: float,
        exit_price: float,
        qty: float,
        entry_date: str,
        exit_date: str,
        entry_signal: Optional[str] = None,
        exit_signal: Optional[str] = None,
    ) -> float:
        """
        Persist a completed round-trip and return the realised P&L.
        """
        realized_pnl = (exit_price - entry_price) * qty
        realized_pnl_pct = (exit_price - entry_price) / entry_price if entry_price > 0 else 0.0

        from datetime import date as date_type
        try:
            d1 = date_type.fromisoformat(entry_date)
            d2 = date_type.fromisoformat(exit_date)
            holding_days = (d2 - d1).days
        except Exception:
            holding_days = 0

        sql = """
        INSERT INTO closed_positions
            (ticker, entry_price, exit_price, qty, realized_pnl, realized_pnl_pct,
             entry_date, exit_date, holding_days, entry_signal, exit_signal, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        with self._connect() as conn:
            conn.execute(sql, (
                ticker,
                entry_price,
                exit_price,
                qty,
                realized_pnl,
                realized_pnl_pct,
                entry_date,
                exit_date,
                holding_days,
                entry_signal,
                exit_signal,
                datetime.now().isoformat(),
            ))

        logger.info(
            "Closed position %s: P&L $%.2f (%.2f%%)",
            ticker, realized_pnl, realized_pnl_pct * 100,
        )
        return realized_pnl

    def get_closed_positions(self, limit: int = 200) -> List[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM closed_positions ORDER BY exit_date DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------ #
    # Snapshots                                                            #
    # ------------------------------------------------------------------ #

    def upsert_snapshot(self, snap: PortfolioSnapshot) -> None:
        sql = """
        INSERT INTO snapshots
            (snapshot_date, cash, invested_value, total_value,
             daily_pnl, daily_pnl_pct, open_positions, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(snapshot_date) DO UPDATE SET
            cash           = excluded.cash,
            invested_value = excluded.invested_value,
            total_value    = excluded.total_value,
            daily_pnl      = excluded.daily_pnl,
            daily_pnl_pct  = excluded.daily_pnl_pct,
            open_positions = excluded.open_positions,
            timestamp      = excluded.timestamp
        """
        with self._connect() as conn:
            conn.execute(sql, (
                snap.snapshot_date,
                snap.cash,
                snap.invested_value,
                snap.total_value,
                snap.daily_pnl,
                snap.daily_pnl_pct,
                snap.open_positions,
                snap.timestamp.isoformat(),
            ))

    def get_snapshots(self, limit: int = 365) -> List[PortfolioSnapshot]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM snapshots ORDER BY snapshot_date DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._row_to_snapshot(r) for r in reversed(rows)]

    def get_latest_snapshot(self) -> Optional[PortfolioSnapshot]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM snapshots ORDER BY snapshot_date DESC LIMIT 1"
            ).fetchone()
        return self._row_to_snapshot(row) if row else None

    def _row_to_snapshot(self, row: sqlite3.Row) -> PortfolioSnapshot:
        return PortfolioSnapshot(
            id=row["id"],
            snapshot_date=row["snapshot_date"],
            cash=row["cash"],
            invested_value=row["invested_value"],
            total_value=row["total_value"],
            daily_pnl=row["daily_pnl"],
            daily_pnl_pct=row["daily_pnl_pct"],
            open_positions=row["open_positions"],
            timestamp=datetime.fromisoformat(row["timestamp"]),
        )
