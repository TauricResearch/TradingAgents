"""A local store of OKX market history for evaluation.

Candles, settled funding and contract specs are fetched from the public endpoints
once, kept in a sqlite file, and read many times by replays and signal studies. The
store remembers which ranges it has fetched so a second request for an overlapping
range only fetches what is missing.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from trader.okx import OKX, Bar, ContractSpec, FundingEvent

MINUTE_MS = 60_000
HOUR_MS = 3_600_000
DAY_MS = 86_400_000

_BAR_MS = {"1m": MINUTE_MS, "5m": 5 * MINUTE_MS, "15m": 15 * MINUTE_MS, "1H": HOUR_MS,
           "4H": 4 * HOUR_MS, "1Dutc": DAY_MS}

FUNDING = "funding"  # the coverage table's name for the funding series

SCHEMA = """
CREATE TABLE IF NOT EXISTS bars (
    inst TEXT NOT NULL, bar TEXT NOT NULL, ts INTEGER NOT NULL,
    open REAL NOT NULL, high REAL NOT NULL, low REAL NOT NULL, close REAL NOT NULL,
    PRIMARY KEY (inst, bar, ts)
);
CREATE TABLE IF NOT EXISTS funding (
    inst TEXT NOT NULL, ts INTEGER NOT NULL, rate REAL NOT NULL,
    PRIMARY KEY (inst, ts)
);
CREATE TABLE IF NOT EXISTS covered (
    inst TEXT NOT NULL, series TEXT NOT NULL, start INTEGER NOT NULL, end INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS specs (
    inst TEXT PRIMARY KEY, contract_value REAL NOT NULL, lot_size REAL NOT NULL,
    min_size REAL NOT NULL, tick_size REAL NOT NULL
);
"""


def bar_ms(bar: str) -> int:
    """Length of a candle of size ``bar`` in milliseconds."""
    try:
        return _BAR_MS[bar]
    except KeyError:
        raise ValueError(f"unknown bar size {bar!r}") from None


class HistoryStore:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, isolation_level=None)
        self.db.executescript(SCHEMA)

    @contextmanager
    def _transaction(self) -> Iterator[None]:
        # Autocommit mode: one explicit transaction per batch, not one per row.
        self.db.execute("BEGIN")
        try:
            yield
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
        self.db.execute("COMMIT")

    # -- reading -------------------------------------------------------------

    def bars(self, inst: str, bar: str, start_ms: int, end_ms: int) -> list[Bar]:
        """Stored candles with ``start_ms <= ts < end_ms``, oldest first."""
        rows = self.db.execute(
            "SELECT ts, open, high, low, close FROM bars"
            " WHERE inst = ? AND bar = ? AND ts >= ? AND ts < ? ORDER BY ts",
            (inst, bar, start_ms, end_ms),
        )
        return [Bar(*row) for row in rows]

    def last_close(self, inst: str, bar: str, before_ms: int) -> float | None:
        """Close of the last stored candle of size ``bar`` that opened before
        ``before_ms``; None when there is none."""
        row = self.db.execute(
            "SELECT close FROM bars WHERE inst = ? AND bar = ? AND ts < ? ORDER BY ts DESC LIMIT 1",
            (inst, bar, before_ms),
        ).fetchone()
        return None if row is None else row[0]

    def funding(self, inst: str, start_ms: int, end_ms: int) -> list[FundingEvent]:
        """Stored settlements with ``start_ms <= ts < end_ms``, oldest first."""
        rows = self.db.execute(
            "SELECT ts, rate FROM funding WHERE inst = ? AND ts >= ? AND ts < ? ORDER BY ts",
            (inst, start_ms, end_ms),
        )
        return [FundingEvent(*row) for row in rows]

    def spec(self, inst: str) -> ContractSpec | None:
        row = self.db.execute(
            "SELECT contract_value, lot_size, min_size, tick_size FROM specs WHERE inst = ?", (inst,)
        ).fetchone()
        return None if row is None else ContractSpec(*row)

    def coverage(self, inst: str, series: str) -> list[tuple[int, int]]:
        """The fetched ranges of ``series`` (a bar size or FUNDING), merged, oldest first."""
        rows = self.db.execute(
            "SELECT start, end FROM covered WHERE inst = ? AND series = ? ORDER BY start",
            (inst, series),
        ).fetchall()
        return _merge(rows)

    def gaps(self, inst: str, series: str, start_ms: int, end_ms: int) -> list[tuple[int, int]]:
        """The parts of ``[start_ms, end_ms)`` not fetched yet, oldest first."""
        gaps, cursor = [], start_ms
        for s, e in self.coverage(inst, series):
            if e <= cursor:
                continue
            if s >= end_ms:
                break
            if s > cursor:
                gaps.append((cursor, min(s, end_ms)))
            cursor = max(cursor, e)
        if cursor < end_ms:
            gaps.append((cursor, end_ms))
        return gaps

    # -- writing -------------------------------------------------------------

    def put_bars(self, inst: str, bar: str, bars: list[Bar], start_ms: int, end_ms: int) -> None:
        """Store ``bars`` and record ``[start_ms, end_ms)`` as fetched."""
        with self._transaction():
            self.db.executemany(
                "INSERT OR REPLACE INTO bars (inst, bar, ts, open, high, low, close)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                [(inst, bar, b.ts, b.open, b.high, b.low, b.close) for b in bars],
            )
            self._cover(inst, bar, start_ms, end_ms)

    def put_funding(self, inst: str, events: list[FundingEvent], start_ms: int, end_ms: int) -> None:
        with self._transaction():
            self.db.executemany(
                "INSERT OR REPLACE INTO funding (inst, ts, rate) VALUES (?, ?, ?)",
                [(inst, e.ts, e.rate) for e in events],
            )
            self._cover(inst, FUNDING, start_ms, end_ms)

    def put_spec(self, inst: str, spec: ContractSpec) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO specs (inst, contract_value, lot_size, min_size, tick_size)"
            " VALUES (?, ?, ?, ?, ?)",
            (inst, spec.contract_value, spec.lot_size, spec.min_size, spec.tick_size),
        )

    def _cover(self, inst: str, series: str, start_ms: int, end_ms: int) -> None:
        rows = self.db.execute(
            "SELECT start, end FROM covered WHERE inst = ? AND series = ?", (inst, series)
        ).fetchall()
        merged = _merge(rows + [(start_ms, end_ms)])
        self.db.execute("DELETE FROM covered WHERE inst = ? AND series = ?", (inst, series))
        self.db.executemany(
            "INSERT INTO covered (inst, series, start, end) VALUES (?, ?, ?, ?)",
            [(inst, series, s, e) for s, e in merged],
        )

    # -- filling from OKX ----------------------------------------------------

    def ensure_bars(self, okx: OKX, inst: str, bar: str, start_ms: int, end_ms: int,
                    now_ms: int) -> int:
        """Fetch the candles of ``[start_ms, end_ms)`` the store lacks. Only candles
        closed by ``now_ms`` can be fetched, so coverage stops at the last of them;
        returns how many candles were fetched."""
        closed = min(end_ms, now_ms - now_ms % bar_ms(bar))
        fetched = 0
        for s, e in self.gaps(inst, bar, start_ms, closed):
            bars = okx.bars(inst, bar, s, e)
            self.put_bars(inst, bar, bars, s, e)
            fetched += len(bars)
        return fetched

    def ensure_funding(self, okx: OKX, inst: str, start_ms: int, end_ms: int, now_ms: int) -> int:
        settled = min(end_ms, now_ms)
        fetched = 0
        for s, e in self.gaps(inst, FUNDING, start_ms, settled):
            events = okx.funding(inst, s, e)
            self.put_funding(inst, events, s, e)
            fetched += len(events)
        return fetched

    def ensure_spec(self, okx: OKX, inst: str) -> ContractSpec:
        spec = self.spec(inst)
        if spec is None:
            spec = okx.contract_spec(inst)
            self.put_spec(inst, spec)
        return spec


def _merge(ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
    merged: list[tuple[int, int]] = []
    for s, e in sorted(ranges):
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    return merged
