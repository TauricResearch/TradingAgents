"""The platform's record of every run: one row per (ticker, analysis date), in SQLite.

The memory log stays the graph's own record; this table adds what the platform needs
beside it: the report folder, the risk-based size and stop recorded at the analysis
date, and whether the run failed. All columns are written by Python; the model only
supplies the decision text and its rating.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, fields
from datetime import datetime
from pathlib import Path

RATINGS = ("Buy", "Overweight", "Hold", "Underweight", "Sell")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS signals (
    ticker         TEXT NOT NULL,
    date           TEXT NOT NULL,
    asset_type     TEXT NOT NULL DEFAULT 'stock',
    status         TEXT NOT NULL,              -- done | failed
    rating         TEXT,
    decision       TEXT,
    error          TEXT,
    analysts       TEXT,
    price          REAL,                       -- last final close on or before the date
    stop_long      REAL,
    size_pct       REAL,                       -- risk-based size, share of the book
    atr            REAL,
    volatility     REAL,
    report_path    TEXT,
    llm_provider   TEXT,
    deep_model     TEXT,
    quick_model    TEXT,
    watchlist      TEXT,
    recorded_at    TEXT NOT NULL,
    PRIMARY KEY (ticker, date)
)
"""


@dataclass
class Signal:
    ticker: str
    date: str
    status: str = "done"
    asset_type: str = "stock"
    rating: str | None = None
    decision: str | None = None
    error: str | None = None
    analysts: str | None = None
    price: float | None = None
    stop_long: float | None = None
    size_pct: float | None = None
    atr: float | None = None
    volatility: float | None = None
    report_path: str | None = None
    llm_provider: str | None = None
    deep_model: str | None = None
    quick_model: str | None = None
    watchlist: str | None = None
    recorded_at: str = ""

    @property
    def ok(self) -> bool:
        return self.status == "done" and self.rating in RATINGS


_COLUMNS = [f.name for f in fields(Signal)]


class SignalStore:
    """Read and write the signals table at ``path``."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute(_SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        finally:
            db.close()

    def save(self, signal: Signal) -> None:
        """Insert or replace the row for the signal's ticker and date."""
        if not signal.recorded_at:
            signal.recorded_at = datetime.now().isoformat(timespec="seconds")
        values = asdict(signal)
        placeholders = ", ".join("?" for _ in _COLUMNS)
        with self._connect() as db:
            db.execute(f"INSERT OR REPLACE INTO signals ({', '.join(_COLUMNS)}) VALUES ({placeholders})",
                       [values[c] for c in _COLUMNS])

    def get(self, ticker: str, date: str) -> Signal | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM signals WHERE ticker = ? AND date = ?", (ticker, date)).fetchone()
        return Signal(**dict(row)) if row else None

    def all(self, ticker: str | None = None, only_ok: bool = False) -> list[Signal]:
        """Every signal, oldest analysis date first; optionally one ticker, or only usable ones."""
        query, args = "SELECT * FROM signals", []
        if ticker:
            query += " WHERE ticker = ?"
            args.append(ticker)
        query += " ORDER BY date, ticker"
        with self._connect() as db:
            rows = [Signal(**dict(r)) for r in db.execute(query, args).fetchall()]
        return [s for s in rows if s.ok] if only_ok else rows

    def delete(self, ticker: str, date: str) -> None:
        with self._connect() as db:
            db.execute("DELETE FROM signals WHERE ticker = ? AND date = ?", (ticker, date))
