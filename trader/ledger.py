"""The paper account in SQLite: cash, positions, fills, funding, equity, research attempts.

A replay or an execution writes everything it changed in one transaction, so a
run that fails part way leaves the account as it was and the next run redoes it.

The ``signals`` table holds the intraday account's hourly decisions (ADR 0006);
the daily account's ledger has it too, empty. The ``transfers`` table holds the money
a person moved into an account on the exchange or out of it (#40); a paper account's
is empty.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS positions (
    inst TEXT PRIMARY KEY, qty REAL NOT NULL, entry REAL NOT NULL, stop REAL);
CREATE TABLE IF NOT EXISTS fills (
    id INTEGER PRIMARY KEY, ts INTEGER NOT NULL, inst TEXT NOT NULL, qty REAL NOT NULL,
    price REAL NOT NULL, fee REAL NOT NULL, reason TEXT NOT NULL, trade_date TEXT);
CREATE TABLE IF NOT EXISTS funding (
    ts INTEGER NOT NULL, inst TEXT NOT NULL, rate REAL NOT NULL, amount REAL NOT NULL,
    PRIMARY KEY (ts, inst));
CREATE TABLE IF NOT EXISTS equity (
    ts INTEGER PRIMARY KEY, equity REAL NOT NULL, units REAL, contributed REAL);
CREATE TABLE IF NOT EXISTS attempts (
    id INTEGER PRIMARY KEY, trade_date TEXT NOT NULL, coin TEXT NOT NULL, ts INTEGER NOT NULL,
    rating TEXT, error TEXT, tokens_in INTEGER, tokens_out INTEGER, cost_usd REAL);
CREATE TABLE IF NOT EXISTS executions (trade_date TEXT PRIMARY KEY, ts INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY, ts INTEGER NOT NULL, kind TEXT NOT NULL, text TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS signals (
    id INTEGER PRIMARY KEY, ts INTEGER NOT NULL, coin TEXT NOT NULL, signal TEXT,
    conviction INTEGER, reason TEXT, error TEXT, tokens_in INTEGER, tokens_out INTEGER,
    cost_usd REAL);
CREATE TABLE IF NOT EXISTS transfers (
    bill_id TEXT PRIMARY KEY, ts INTEGER NOT NULL, amount REAL NOT NULL);
CREATE INDEX IF NOT EXISTS fills_ts ON fills (ts);
CREATE INDEX IF NOT EXISTS attempts_ts ON attempts (ts);
CREATE INDEX IF NOT EXISTS attempts_trade_date_coin ON attempts (trade_date, coin);
CREATE INDEX IF NOT EXISTS signals_ts ON signals (ts);
CREATE INDEX IF NOT EXISTS signals_coin_id ON signals (coin, id);
"""

BUDGET_ERROR = "budget: monthly LLM cap reached"

# (table, column) a ledger written before them lacks: a writer adds them when it opens it.
ADDED_COLUMNS = (("equity", "units REAL"), ("equity", "contributed REAL"))


@dataclass
class Position:
    qty: float           # signed coins: positive long, negative short
    entry: float         # average entry price
    stop: float | None


@dataclass(frozen=True)
class Fill:
    ts: int
    inst: str
    qty: float           # signed coins traded: positive bought, negative sold
    price: float
    fee: float
    reason: str          # "trade", "stop" or "kill"; on the exchange also "manual" and "adjust"
    trade_date: str | None = None


@dataclass(frozen=True)
class Snapshot:
    """The equity at a UTC midnight, with the account's units and the capital put into it
    by then. A transfer buys units at the equity per unit of the moment, or sells them
    (``Ledger.commit``), so the equity per unit moves with the trading alone: it is the
    account's time-weighted value, which no transfer adds to or takes from. Until the
    first transfer, and in a paper account always, both are the capital."""

    ts: int
    equity: float
    units: float
    contributed: float   # the capital and the transfers since, net: USDT put in less taken out


class SignalLike(Protocol):
    """What ``record_signal`` stores of an hourly decision; the intraday module's
    ``SignalResult`` has these fields, the ledger does not depend on it."""

    signal: str | None
    conviction: int | None
    reason: str
    error: str | None
    tokens_in: int
    tokens_out: int
    cost_usd: float | None


class Ledger:
    def __init__(self, path: Path, readonly: bool = False):
        self.path = path
        if readonly:
            # A reader (the web API) opens the file as it is: no directory, no
            # schema, and sqlite raises when there is no ledger at ``path``. The
            # connection may be used from another thread than the one that opened
            # it (FastAPI runs a request's steps on worker threads), one at a time.
            self.db = sqlite3.connect(
                f"file:{path}?mode=ro", uri=True, timeout=30, isolation_level=None,
                check_same_thread=False,
            )
            # It may be a ledger no writer has opened since the transfers were added,
            # with none booked.
            self._flows = not self._lacking() and self.db.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'transfers'"
            ).fetchone() is not None
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        # The research phase writes attempts while an hourly replay may hold a
        # write transaction; the timeout lets one wait for the other.
        self.db = sqlite3.connect(path, timeout=30, isolation_level=None)
        # Write-ahead logging, persistent in the file: the web API's readers no longer
        # wait on a writer's commit, and a writer not on theirs.
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript(SCHEMA)
        if self._lacking():
            with self.transaction():  # one writer adds them, the next finds them there
                for table, column in self._lacking():
                    self.db.execute(f"ALTER TABLE {table} ADD COLUMN {column}")
        self._flows = True

    def _lacking(self) -> list[tuple[str, str]]:
        """The ADDED_COLUMNS this ledger does not have yet."""
        return [
            (table, column) for table, column in ADDED_COLUMNS
            if column.split()[0] not in {row[1] for row in self.db.execute(f"PRAGMA table_info({table})")}
        ]

    # -- meta ---------------------------------------------------------------

    def get(self, key: str, default=None):
        row = self.db.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def set(self, key: str, value) -> None:
        self._set(key, value)

    def _set(self, key: str, value) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, json.dumps(value))
        )

    @property
    def initialized(self) -> bool:
        return self.get("capital") is not None

    def initialize(self, capital: float, now_ms: int) -> None:
        with self.transaction():
            for key, value in (
                ("capital", capital), ("cash", capital), ("peak", capital),
                ("halted", False), ("processed_to", now_ms - now_ms % 60_000),
            ):
                self._set(key, value)

    # -- account ------------------------------------------------------------

    @contextmanager
    def transaction(self):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
        self.db.execute("COMMIT")

    def positions(self) -> dict[str, Position]:
        rows = self.db.execute("SELECT inst, qty, entry, stop FROM positions")
        return {inst: Position(qty, entry, stop) for inst, qty, entry, stop in rows}

    def commit(
        self,
        *,
        positions: dict[str, Position],
        cash: float,
        fills: list[Fill] = (),
        funding: list[tuple[int, str, float, float]] = (),
        snapshots: list[tuple[int, float]] = (),
        meta: dict | None = None,
        executed: tuple[str, int] | None = None,
        events: list[tuple[int, str, str]] = (),
        transfers: list[tuple[str, int, float]] = (),
    ) -> None:
        """Replace the positions and write everything a replay or execution changed,
        ``events`` (ts, kind, text) and ``transfers`` (bill id, ts, amount) among it.

        A snapshot is written with the units and the contributed capital in meta
        (``units``, ``contributed``) once ``meta`` has set them: those of the equity it
        measured, which includes what this commit booked. A sync that books transfers
        sets both (``Snapshot``); until one has, they are null, which reads as the
        capital."""
        with self.transaction():
            self.db.execute("DELETE FROM positions")
            self.db.executemany(
                "INSERT INTO positions (inst, qty, entry, stop) VALUES (?, ?, ?, ?)",
                [(inst, p.qty, p.entry, p.stop) for inst, p in positions.items()],
            )
            self.db.executemany(
                "INSERT INTO fills (ts, inst, qty, price, fee, reason, trade_date)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                [(f.ts, f.inst, f.qty, f.price, f.fee, f.reason, f.trade_date) for f in fills],
            )
            self.db.executemany(
                "INSERT INTO funding (ts, inst, rate, amount) VALUES (?, ?, ?, ?)", funding
            )
            self.db.executemany(
                "INSERT INTO transfers (bill_id, ts, amount) VALUES (?, ?, ?)", transfers
            )
            self._set("cash", cash)
            for key, value in (meta or {}).items():
                self._set(key, value)
            # A midnight a replay already marked keeps its value.
            units, contributed = self.get("units"), self.get("contributed")
            self.db.executemany(
                "INSERT OR IGNORE INTO equity (ts, equity, units, contributed) VALUES (?, ?, ?, ?)",
                [(ts, equity, units, contributed) for ts, equity in snapshots],
            )
            if executed:
                self.db.execute(
                    "INSERT INTO executions (trade_date, ts) VALUES (?, ?)", executed
                )
            self.db.executemany("INSERT INTO events (ts, kind, text) VALUES (?, ?, ?)", events)

    def executed(self, trade_date: str) -> bool:
        return self.db.execute(
            "SELECT 1 FROM executions WHERE trade_date = ?", (trade_date,)
        ).fetchone() is not None

    def net_fills(self) -> dict[str, float]:
        """What the fills add up to per instrument: the position they explain for an
        account that started flat."""
        rows = self.db.execute("SELECT inst, SUM(qty) FROM fills GROUP BY inst")
        return {inst: round(qty, 12) for inst, qty in rows}

    def fills(self, since_ms: int = 0) -> list[Fill]:
        """The fills since ``since_ms`` in time order, booking order within a time."""
        rows = self.db.execute(
            "SELECT ts, inst, qty, price, fee, reason, trade_date FROM fills"
            " WHERE ts >= ? ORDER BY ts, id", (since_ms,),
        )
        return [Fill(*row) for row in rows]

    def funding(self, since_ms: int = 0) -> list[tuple[int, str, float, float]]:
        """(ts, inst, rate, amount) of the funding booked since ``since_ms``, in time order."""
        return self.db.execute(
            "SELECT ts, inst, rate, amount FROM funding WHERE ts >= ? ORDER BY ts, inst", (since_ms,)
        ).fetchall()

    def funding_total(self, since_ms: int = 0) -> float:
        row = self.db.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM funding WHERE ts >= ?", (since_ms,)
        ).fetchone()
        return row[0]

    def equity_series(self, since_ms: int = 0) -> list[tuple[int, float]]:
        return self.db.execute(
            "SELECT ts, equity FROM equity WHERE ts >= ? ORDER BY ts", (since_ms,)
        ).fetchall()

    def snapshots(self, since_ms: int = 0) -> list[Snapshot]:
        """The midnight snapshots since ``since_ms`` in time order."""
        capital = self.get("capital")
        if not self._flows:
            return [Snapshot(ts, equity, capital, capital) for ts, equity in self.equity_series(since_ms)]
        rows = self.db.execute(
            "SELECT ts, equity, COALESCE(units, ?), COALESCE(contributed, ?) FROM equity"
            " WHERE ts >= ? ORDER BY ts", (capital, capital, since_ms),
        )
        return [Snapshot(*row) for row in rows]

    def adjusted_series(self, since_ms: int = 0) -> list[tuple[int, float]]:
        """The midnight equity per unit, times the capital: what the capital would have
        grown to without the transfers, the equity itself until the first. Its returns
        are time-weighted (``Snapshot``)."""
        capital = self.get("capital")
        # Divided by the ratio, so that an equity measured with the capital's units stays
        # the same float.
        return [(s.ts, s.equity / (s.units / capital)) for s in self.snapshots(since_ms)]

    def units(self) -> float:
        """The account's units now (``Snapshot``)."""
        return self.get("units", self.get("capital"))

    def contributed(self) -> float:
        """The capital put into the account now: the capital and the transfers, net."""
        return self.get("contributed", self.get("capital"))

    def transfers(self, since_ms: int = 0) -> list[tuple[int, float]]:
        """(ts, amount) of the transfers booked since ``since_ms`` in time order; the
        amount is the USDT moved in, negative when moved out."""
        if not self._flows:
            return []
        return self.db.execute(
            "SELECT ts, amount FROM transfers WHERE ts >= ? ORDER BY ts, bill_id", (since_ms,)
        ).fetchall()

    def add_event(self, ts: int, kind: str, text: str) -> None:
        self.db.execute("INSERT INTO events (ts, kind, text) VALUES (?, ?, ?)", (ts, kind, text))

    def events(self, since_ms: int = 0, kinds: tuple[str, ...] = ()) -> list[tuple[int, str, str]]:
        """(ts, kind, text) of the events since ``since_ms`` in the order they were
        added; of ``kinds`` only, when given."""
        sql, params = "SELECT ts, kind, text FROM events WHERE ts >= ?", [since_ms]
        if kinds:
            sql += f" AND kind IN ({', '.join('?' * len(kinds))})"
            params += kinds
        return self.db.execute(sql + " ORDER BY id", params).fetchall()

    # -- research -----------------------------------------------------------

    def record_attempt(
        self, trade_date: str, coin: str, ts: int, *, rating: str | None, error: str | None,
        tokens_in: int = 0, tokens_out: int = 0, cost_usd: float | None = 0.0,
    ) -> None:
        self.db.execute(
            "INSERT INTO attempts (trade_date, coin, ts, rating, error, tokens_in, tokens_out,"
            " cost_usd) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (trade_date, coin, ts, rating, error, tokens_in, tokens_out, cost_usd),
        )

    def attempts(self, trade_date: str, coin: str) -> list[tuple[str | None, str | None]]:
        """(rating, error) of each attempt, oldest first."""
        return self.db.execute(
            "SELECT rating, error FROM attempts WHERE trade_date = ? AND coin = ? ORDER BY id",
            (trade_date, coin),
        ).fetchall()

    def cost_since(self, since_ms: int) -> tuple[float, bool]:
        """LLM cost of the attempts made since ``since_ms``, and whether any cost is unknown."""
        total, unknown = self.db.execute(
            "SELECT COALESCE(SUM(cost_usd), 0), COUNT(*) - COUNT(cost_usd) FROM attempts"
            " WHERE ts >= ?", (since_ms,),
        ).fetchone()
        return total, unknown > 0

    def cost_of(self, trade_date: str) -> tuple[float, bool]:
        """LLM cost of one trade date's attempts, and whether any cost is unknown."""
        total, unknown = self.db.execute(
            "SELECT COALESCE(SUM(cost_usd), 0), COUNT(*) - COUNT(cost_usd) FROM attempts"
            " WHERE trade_date = ?", (trade_date,),
        ).fetchone()
        return total, unknown > 0

    def costs(self, since_ms: int) -> list[tuple[int, float | None]]:
        """(ts, cost_usd) of each attempt since ``since_ms``, oldest first."""
        return self.db.execute(
            "SELECT ts, cost_usd FROM attempts WHERE ts >= ? ORDER BY ts", (since_ms,)
        ).fetchall()

    def daily_costs(self, before_trade_date: str) -> list[tuple[str, float | None]]:
        """Cost per trade date before ``before_trade_date``, oldest first; None when any
        attempt of that day has an unknown cost."""
        return self.db.execute(
            "SELECT trade_date, CASE WHEN COUNT(*) = COUNT(cost_usd) THEN SUM(cost_usd) END"
            " FROM attempts WHERE trade_date < ? AND error IS NOT ? GROUP BY trade_date"
            " ORDER BY trade_date", (before_trade_date, BUDGET_ERROR),
        ).fetchall()

    # -- intraday signals ---------------------------------------------------

    def record_signal(self, ts: int, coin: str, result: SignalLike) -> None:
        self.db.execute(
            "INSERT INTO signals (ts, coin, signal, conviction, reason, error, tokens_in,"
            " tokens_out, cost_usd) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                ts, coin, result.signal, result.conviction, result.reason, result.error,
                result.tokens_in, result.tokens_out, result.cost_usd,
            ),
        )

    def signals(self, since_ms: int = 0, limit: int = 500) -> list[tuple]:
        """(ts, coin, signal, conviction, reason, error, tokens_in, tokens_out, cost_usd)
        of the signals recorded since ``since_ms``, newest first, at most ``limit``."""
        return self.db.execute(
            "SELECT ts, coin, signal, conviction, reason, error, tokens_in, tokens_out,"
            " cost_usd FROM signals WHERE ts >= ? ORDER BY ts DESC, id DESC LIMIT ?",
            (since_ms, limit),
        ).fetchall()

    def latest_signals(self) -> dict[str, tuple[int, str | None]]:
        """Each coin's most recent (ts, signal)."""
        rows = self.db.execute(
            "SELECT coin, ts, signal FROM signals"
            " WHERE id IN (SELECT MAX(id) FROM signals GROUP BY coin)"
        )
        return {coin: (ts, signal) for coin, ts, signal in rows}

    def signal_cost_since(self, since_ms: int) -> tuple[float, bool]:
        """LLM cost of the signals since ``since_ms``, and whether any cost is unknown."""
        total, unknown = self.db.execute(
            "SELECT COALESCE(SUM(cost_usd), 0), COUNT(*) - COUNT(cost_usd) FROM signals"
            " WHERE ts >= ?", (since_ms,),
        ).fetchone()
        return total, unknown > 0

    def signal_costs(self, since_ms: int) -> list[tuple[int, float | None]]:
        """(ts, cost_usd) of each signal since ``since_ms``, oldest first."""
        return self.db.execute(
            "SELECT ts, cost_usd FROM signals WHERE ts >= ? ORDER BY ts, id", (since_ms,)
        ).fetchall()


@contextmanager
def locked(path: Path):
    """Hold an exclusive lock on ``path`` so one process at a time changes the account."""
    import fcntl  # POSIX only, like the server this runs on

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield
