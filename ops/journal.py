"""Append-only SQLite journal for the live-trading layer.

The journal is the source of truth for state recovery. Every state change
in the system MUST land here before any other side effect.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    at TEXT NOT NULL,
    kind TEXT NOT NULL,
    payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_kind ON events(kind);

CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    at TEXT NOT NULL,
    client_order_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    notional_dollars TEXT NOT NULL,
    stop_loss_price TEXT
);

CREATE TABLE IF NOT EXISTS fills (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    at TEXT NOT NULL,
    order_id TEXT NOT NULL,
    client_order_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    quantity TEXT NOT NULL,
    price TEXT NOT NULL,
    filled_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS equity_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    at TEXT NOT NULL,
    equity TEXT NOT NULL,
    cash TEXT NOT NULL
);
"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        raise ValueError("naive datetimes are not allowed in the journal")
    return dt.isoformat()


def _from_iso(s: str) -> datetime:
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        raise ValueError(f"stored datetime lacks timezone info: {s!r}")
    return dt


class Journal:
    def __init__(self, path: str):
        self._path = path
        self._conn = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)

    def record_event(self, kind: str, payload: dict[str, Any]) -> None:
        self._conn.execute(
            "INSERT INTO events (at, kind, payload) VALUES (?, ?, ?)",
            (_now_iso(), kind, json.dumps(payload, default=str)),
        )

    def read_events(self) -> list[dict[str, Any]]:
        cur = self._conn.execute("SELECT at, kind, payload FROM events ORDER BY id")
        return [
            {"at": _from_iso(row[0]), "kind": row[1], "payload": json.loads(row[2])}
            for row in cur
        ]

    def record_order(
        self, *, client_order_id: str, symbol: str, side: str,
        notional_dollars: Decimal, stop_loss_price: Decimal | None,
    ) -> None:
        self._conn.execute(
            "INSERT INTO orders (at, client_order_id, symbol, side, notional_dollars, stop_loss_price)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (
                _now_iso(), client_order_id, symbol, side,
                str(notional_dollars),
                str(stop_loss_price) if stop_loss_price is not None else None,
            ),
        )

    def read_orders(self) -> list[dict[str, Any]]:
        cur = self._conn.execute(
            "SELECT at, client_order_id, symbol, side, notional_dollars, stop_loss_price"
            " FROM orders ORDER BY id"
        )
        return [
            {
                "at": _from_iso(row[0]), "client_order_id": row[1],
                "symbol": row[2], "side": row[3],
                "notional_dollars": Decimal(row[4]),
                "stop_loss_price": Decimal(row[5]) if row[5] is not None else None,
            }
            for row in cur
        ]

    def record_fill(
        self, *, order_id: str, client_order_id: str, symbol: str, side: str,
        quantity: Decimal, price: Decimal, filled_at: datetime,
    ) -> None:
        self._conn.execute(
            "INSERT INTO fills (at, order_id, client_order_id, symbol, side, quantity, price, filled_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                _now_iso(), order_id, client_order_id, symbol, side,
                str(quantity), str(price), _to_iso(filled_at),
            ),
        )

    def read_fills(self) -> list[dict[str, Any]]:
        cur = self._conn.execute(
            "SELECT at, order_id, client_order_id, symbol, side, quantity, price, filled_at"
            " FROM fills ORDER BY id"
        )
        return [
            {
                "at": _from_iso(row[0]), "order_id": row[1],
                "client_order_id": row[2], "symbol": row[3], "side": row[4],
                "quantity": Decimal(row[5]), "price": Decimal(row[6]),
                "filled_at": _from_iso(row[7]),
            }
            for row in cur
        ]

    def record_equity_snapshot(self, *, at: datetime, equity: Decimal, cash: Decimal) -> None:
        self._conn.execute(
            "INSERT INTO equity_snapshots (at, equity, cash) VALUES (?, ?, ?)",
            (_to_iso(at), str(equity), str(cash)),
        )

    def read_equity_snapshots(self) -> list[dict[str, Any]]:
        cur = self._conn.execute("SELECT at, equity, cash FROM equity_snapshots ORDER BY id")
        return [
            {"at": _from_iso(row[0]), "equity": Decimal(row[1]), "cash": Decimal(row[2])}
            for row in cur
        ]

    def __enter__(self) -> "Journal":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        self._conn.close()
