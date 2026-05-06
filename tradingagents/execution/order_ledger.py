"""SQLite ledger for order + fill lifecycle tracking.

Adapted from the kalshi-trader pattern (``order_ledger`` table) but pared
down for the daily-horizon Kalshi pipeline:

- One row per agent decision (paper or live), inserted at decision time.
- Rows are updated through the lifecycle: ``recorded`` -> ``submitted``
  -> ``partial`` -> ``filled`` -> ``settled`` (or ``rejected`` /
  ``cancelled`` on failure paths).
- Settlement outcome (won/lost + payoff) is appended once Kalshi settles
  the contract, so the memory log can reflect on win-rate over time.

The ledger lives at ``{data_cache_dir}/orders.db`` so it cohabits with
the agent run cache + checkpoints under ``~/.tradingagents/cache/``.
"""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


SCHEMA = """
CREATE TABLE IF NOT EXISTS order_ledger (
    decision_id      TEXT PRIMARY KEY,
    contract_id      TEXT NOT NULL,
    trade_date       TEXT NOT NULL,
    mode             TEXT NOT NULL,
    side             TEXT,
    count            INTEGER,
    price_cents      INTEGER,
    p_yes            REAL,
    market_p_yes     REAL,
    edge_bps         REAL,
    confidence       TEXT,
    kelly_fraction   REAL,
    stake_usd        REAL,
    venue_order_id   TEXT,
    status           TEXT NOT NULL,
    fills_filled     INTEGER DEFAULT 0,
    avg_fill_cents   REAL,
    settlement       TEXT,
    realized_pnl_usd REAL,
    submitted_at     REAL,
    first_fill_at    REAL,
    full_fill_at     REAL,
    settled_at       REAL,
    decision_payload TEXT,
    last_error       TEXT,
    created_at       REAL NOT NULL,
    updated_at       REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_order_ledger_status
    ON order_ledger(status);

CREATE INDEX IF NOT EXISTS idx_order_ledger_contract
    ON order_ledger(contract_id);
"""


def _ledger_path(config: Dict) -> Path:
    cache_dir = Path(config.get("data_cache_dir", str(Path.home() / ".tradingagents/cache")))
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / "orders.db"


@contextmanager
def _connection(config: Dict):
    path = _ledger_path(config)
    conn = sqlite3.connect(str(path), timeout=10)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = sqlite3.Row
        conn.executescript(SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def record_decision(
    *,
    config: Dict,
    contract_id: str,
    trade_date: str,
    mode: str,
    side: Optional[str],
    count: Optional[int],
    price_cents: Optional[int],
    p_yes: Optional[float],
    market_p_yes: Optional[float],
    edge_bps: Optional[float],
    confidence: Optional[str],
    kelly_fraction: Optional[float],
    stake_usd: Optional[float],
    decision_payload: Optional[Dict] = None,
) -> str:
    """Insert a fresh ledger row for a Portfolio Manager decision.

    Returns the freshly-minted ``decision_id`` so the caller can update
    the row as the order moves through its lifecycle.
    """
    decision_id = str(uuid.uuid4())
    now = time.time()

    with _connection(config) as conn:
        conn.execute(
            """
            INSERT INTO order_ledger (
                decision_id, contract_id, trade_date, mode, side, count,
                price_cents, p_yes, market_p_yes, edge_bps, confidence,
                kelly_fraction, stake_usd, status,
                decision_payload, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                decision_id, contract_id, trade_date, mode, side, count,
                price_cents, p_yes, market_p_yes, edge_bps, confidence,
                kelly_fraction, stake_usd, "recorded",
                json.dumps(decision_payload, default=str) if decision_payload else None,
                now, now,
            ),
        )
    return decision_id


def update_status(
    *,
    config: Dict,
    decision_id: str,
    status: str,
    venue_order_id: Optional[str] = None,
    fills_filled: Optional[int] = None,
    avg_fill_cents: Optional[float] = None,
    submitted_at: Optional[float] = None,
    first_fill_at: Optional[float] = None,
    full_fill_at: Optional[float] = None,
    settled_at: Optional[float] = None,
    settlement: Optional[str] = None,
    realized_pnl_usd: Optional[float] = None,
    last_error: Optional[str] = None,
) -> None:
    """Update a ledger row. Only non-None fields are written."""
    fields: Dict[str, Any] = {"status": status, "updated_at": time.time()}
    if venue_order_id is not None:
        fields["venue_order_id"] = venue_order_id
    if fills_filled is not None:
        fields["fills_filled"] = fills_filled
    if avg_fill_cents is not None:
        fields["avg_fill_cents"] = avg_fill_cents
    if submitted_at is not None:
        fields["submitted_at"] = submitted_at
    if first_fill_at is not None:
        fields["first_fill_at"] = first_fill_at
    if full_fill_at is not None:
        fields["full_fill_at"] = full_fill_at
    if settled_at is not None:
        fields["settled_at"] = settled_at
    if settlement is not None:
        fields["settlement"] = settlement
    if realized_pnl_usd is not None:
        fields["realized_pnl_usd"] = realized_pnl_usd
    if last_error is not None:
        fields["last_error"] = last_error

    set_sql = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [decision_id]

    with _connection(config) as conn:
        conn.execute(
            f"UPDATE order_ledger SET {set_sql} WHERE decision_id = ?",
            values,
        )


def get_decision(config: Dict, decision_id: str) -> Optional[Dict]:
    with _connection(config) as conn:
        row = conn.execute(
            "SELECT * FROM order_ledger WHERE decision_id = ?",
            (decision_id,),
        ).fetchone()
    return dict(row) if row else None


def list_open(config: Dict) -> List[Dict]:
    """Decisions that have been submitted but not yet settled."""
    open_states = ("submitted", "partial", "filled")
    placeholders = ",".join("?" * len(open_states))
    with _connection(config) as conn:
        rows = conn.execute(
            f"SELECT * FROM order_ledger WHERE status IN ({placeholders}) ORDER BY created_at",
            open_states,
        ).fetchall()
    return [dict(r) for r in rows]


def list_recent(config: Dict, limit: int = 25) -> List[Dict]:
    with _connection(config) as conn:
        rows = conn.execute(
            "SELECT * FROM order_ledger ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def daily_realized_pnl_usd(config: Dict, trade_date: str) -> float:
    with _connection(config) as conn:
        row = conn.execute(
            """
            SELECT COALESCE(SUM(realized_pnl_usd), 0) AS pnl
            FROM order_ledger
            WHERE trade_date = ?
              AND realized_pnl_usd IS NOT NULL
            """,
            (trade_date,),
        ).fetchone()
    return float(row["pnl"] or 0.0)
