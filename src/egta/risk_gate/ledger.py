"""SQLite paper ledger, idempotency, and audit outbox for FR-04."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

from .canonical import sha256_hex
from .models import (
    PortfolioSnapshot,
    Position,
    ReasonCode,
    RiskVerdict,
    VerdictStatus,
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS portfolios (
    portfolio_id TEXT PRIMARY KEY,
    version INTEGER NOT NULL,
    base_currency TEXT NOT NULL,
    cash TEXT NOT NULL,
    as_of TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS positions (
    portfolio_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    mark_price TEXT NOT NULL,
    PRIMARY KEY (portfolio_id, symbol)
);

CREATE TABLE IF NOT EXISTS ledger_entries (
    entry_id TEXT PRIMARY KEY,
    proposal_hash TEXT NOT NULL UNIQUE,
    verdict_id TEXT NOT NULL,
    side TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    exec_price TEXT NOT NULL,
    fee TEXT NOT NULL,
    cash_after TEXT NOT NULL,
    position_after INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS risk_verdicts (
    verdict_id TEXT PRIMARY KEY,
    proposal_hash TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL,
    reasons TEXT NOT NULL,
    checked_rules TEXT NOT NULL,
    portfolio_version INTEGER NOT NULL,
    expires_at TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS outbox_events (
    schema_version TEXT NOT NULL,
    event_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    sequence INTEGER NOT NULL,
    phase TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    duration_ms INTEGER NOT NULL,
    status TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    prev_event_hash TEXT NOT NULL,
    metrics TEXT NOT NULL,
    reason_code TEXT,
    UNIQUE (run_id, sequence)
);

CREATE TABLE IF NOT EXISTS schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def connect(db_path: str | Path, busy_timeout_seconds: float) -> sqlite3.Connection:
    connection = sqlite3.connect(
        str(Path(db_path)),
        timeout=busy_timeout_seconds,
        isolation_level=None,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute(f"PRAGMA busy_timeout = {int(busy_timeout_seconds * 1000)}")
    return connection


def initialize(db_path: str | Path, portfolio: Any) -> None:
    connection = connect(db_path, 5.0)
    try:
        connection.executescript(_SCHEMA)
        existing = connection.execute(
            "SELECT 1 FROM portfolios WHERE portfolio_id = ?",
            (portfolio.portfolio_id,),
        ).fetchone()
        if existing is None:
            connection.execute(
                "INSERT INTO portfolios "
                "(portfolio_id, version, base_currency, cash, as_of) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    portfolio.portfolio_id,
                    int(portfolio.version),
                    portfolio.base_currency,
                    str(portfolio.cash),
                    portfolio.as_of.isoformat(),
                ),
            )
            for position in portfolio.positions:
                connection.execute(
                    "INSERT INTO positions "
                    "(portfolio_id, symbol, quantity, mark_price) "
                    "VALUES (?, ?, ?, ?)",
                    (
                        portfolio.portfolio_id,
                        position.symbol,
                        int(position.quantity),
                        str(position.mark_price),
                    ),
                )
        connection.execute(
            "INSERT OR IGNORE INTO schema_meta (key, value) VALUES ('schema_version', '1')"
        )
        connection.commit()
    finally:
        connection.close()


def read_portfolio(connection: sqlite3.Connection, portfolio_id: str) -> PortfolioSnapshot:
    row = connection.execute(
        "SELECT version, base_currency, cash, as_of "
        "FROM portfolios WHERE portfolio_id = ?",
        (portfolio_id,),
    ).fetchone()
    if row is None:
        raise KeyError(f"portfolio {portfolio_id!r} not found")
    positions = tuple(
        Position(
            symbol=item["symbol"],
            quantity=int(item["quantity"]),
            mark_price=Decimal(str(item["mark_price"])),
        )
        for item in connection.execute(
            "SELECT symbol, quantity, mark_price FROM positions "
            "WHERE portfolio_id = ? ORDER BY symbol",
            (portfolio_id,),
        )
    )
    return PortfolioSnapshot(
        portfolio_id=portfolio_id,
        version=int(row["version"]),
        base_currency=row["base_currency"],
        cash=Decimal(str(row["cash"])),
        positions=positions,
        as_of=datetime.fromisoformat(row["as_of"]),
    )


def read_verdict(
    connection: sqlite3.Connection, proposal_hash: str
) -> RiskVerdict | None:
    row = connection.execute(
        "SELECT verdict_id, proposal_hash, status, reasons, checked_rules, "
        "portfolio_version, expires_at "
        "FROM risk_verdicts WHERE proposal_hash = ?",
        (proposal_hash,),
    ).fetchone()
    if row is None:
        return None
    reasons = tuple(ReasonCode(value) for value in json.loads(row["reasons"]))
    checked = tuple(json.loads(row["checked_rules"]))
    expires_at = (
        datetime.fromisoformat(row["expires_at"]) if row["expires_at"] else None
    )
    return RiskVerdict(
        proposal_hash=row["proposal_hash"],
        status=VerdictStatus(row["status"]),
        reasons=reasons,
        checked_rules=checked,
        portfolio_version=int(row["portfolio_version"]),
        expires_at=expires_at,
        verdict_id=row["verdict_id"],
    )


def store_verdict(
    connection: sqlite3.Connection, verdict: RiskVerdict, created_at: datetime
) -> None:
    connection.execute(
        "INSERT INTO risk_verdicts "
        "(verdict_id, proposal_hash, status, reasons, checked_rules, "
        "portfolio_version, expires_at, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            verdict.verdict_id,
            verdict.proposal_hash,
            verdict.status.value,
            json.dumps([reason.value for reason in verdict.reasons]),
            json.dumps(list(verdict.checked_rules)),
            verdict.portfolio_version,
            verdict.expires_at.isoformat() if verdict.expires_at else None,
            created_at.isoformat(),
        ),
    )


def store_ledger_entry(
    connection: sqlite3.Connection,
    *,
    proposal_hash: str,
    verdict_id: str,
    side: str,
    quantity: int,
    exec_price: Decimal,
    fee: Decimal,
    cash_after: Decimal,
    position_after: int,
    created_at: datetime,
) -> None:
    connection.execute(
        "INSERT INTO ledger_entries "
        "(entry_id, proposal_hash, verdict_id, side, quantity, exec_price, fee, "
        "cash_after, position_after, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            uuid4().hex,
            proposal_hash,
            verdict_id,
            side,
            quantity,
            str(exec_price),
            str(fee),
            str(cash_after),
            position_after,
            created_at.isoformat(),
        ),
    )


def update_portfolio(
    connection: sqlite3.Connection,
    *,
    portfolio_id: str,
    old_version: int,
    new_version: int,
    cash_after: Decimal,
    position_symbol: str,
    position_after: int,
    mark_price: Decimal,
    as_of: datetime,
) -> None:
    cursor = connection.execute(
        "UPDATE portfolios SET version = ?, cash = ?, as_of = ? "
        "WHERE portfolio_id = ? AND version = ?",
        (
            new_version,
            str(cash_after),
            as_of.isoformat(),
            portfolio_id,
            old_version,
        ),
    )
    if cursor.rowcount != 1:
        raise RuntimeError("portfolio version conflict")
    connection.execute(
        "INSERT INTO positions (portfolio_id, symbol, quantity, mark_price) "
        "VALUES (?, ?, ?, ?) "
        "ON CONFLICT(portfolio_id, symbol) DO UPDATE SET "
        "quantity = excluded.quantity, mark_price = excluded.mark_price",
        (portfolio_id, position_symbol, position_after, str(mark_price)),
    )


def store_outbox_event(
    connection: sqlite3.Connection,
    *,
    run_id: str,
    status: str,
    reason_code: str | None,
    metrics: dict[str, Any],
    timestamp: datetime,
) -> None:
    row = connection.execute(
        "SELECT COALESCE(MAX(sequence), -1) + 1 AS next_sequence "
        "FROM outbox_events WHERE run_id = ?",
        (run_id,),
    ).fetchone()
    sequence = int(row["next_sequence"])
    previous = connection.execute(
        "SELECT payload_hash FROM outbox_events WHERE run_id = ? "
        "ORDER BY sequence DESC LIMIT 1",
        (run_id,),
    ).fetchone()
    prev_hash = previous["payload_hash"] if previous is not None else ""
    event_id = uuid4().hex
    timestamp_iso = timestamp.astimezone(UTC).isoformat()
    payload = {
        "schema_version": "1.0",
        "event_id": event_id,
        "run_id": run_id,
        "sequence": sequence,
        "phase": "risk_gate",
        "timestamp": timestamp_iso,
        "duration_ms": 0,
        "status": status,
        "prev_event_hash": prev_hash,
        "metrics": metrics,
        "reason_code": reason_code,
    }
    digest = sha256_hex(payload)
    connection.execute(
        "INSERT INTO outbox_events "
        "(schema_version, event_id, run_id, sequence, phase, timestamp, "
        "duration_ms, status, payload_hash, prev_event_hash, metrics, reason_code) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "1.0",
            event_id,
            run_id,
            sequence,
            "risk_gate",
            timestamp_iso,
            0,
            status,
            digest,
            prev_hash,
            json.dumps(metrics, sort_keys=True, separators=(",", ":")),
            reason_code,
        ),
    )


def snapshot(db_path: str | Path, portfolio_id: str) -> PortfolioSnapshot:
    connection = connect(db_path, 5.0)
    try:
        return read_portfolio(connection, portfolio_id)
    finally:
        connection.close()
