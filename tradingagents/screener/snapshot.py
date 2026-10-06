"""The metrics snapshot: every catalog metric for every security, precomputed.

``metrics_snapshot`` lives in the India database beside the data it is built
from: a row per security and snapshot, a column per catalog metric, keyed by
``as_of_date``. Screens query it instead of recomputing a hundred metrics for
two thousand stocks on every keystroke.

``as_of_date`` is ``live`` for the snapshot of the latest data (rebuilt by
``tradingagents india build-snapshot`` and at the end of ``india sync-all``), or
a date for a historical one built with ``--as-of``. A historical snapshot reads
the database point in time: only filings with ``filed_at`` on or before that day,
prices up to that day, adjustments and corporate actions known by then. Kept side
by side, the snapshots let a screen run as of any of those dates, which is what a
later backtest of a screen needs.

The universe (``screener_universe``):

    eq      stocks in NSE's EQ series: listed in EQ today for the live snapshot; for
            a historical one, traded in EQ in the 15 days before its date, so stocks
            delisted since are still in it (no survivorship bias)
    listed  the same for every series (EQ, BE, BZ, ...)
    all     every security in the database

Missing data is NULL, never 0.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from tradingagents.dataflows.vendors.india import store
from tradingagents.screener import catalog
from tradingagents.screener.company import dividends_covered, load_company

LIVE = "live"
UNIVERSES = ("eq", "listed", "all")
TRADED_WINDOW_DAYS = 15
EXTRA_COLUMNS = {"bse_code": "TEXT", "price_date": "TEXT", "financial": "INTEGER", "basis": "TEXT"}


class SnapshotError(Exception):
    """A snapshot that cannot be built or read; the message says what to run."""


@dataclass
class BuildResult:
    as_of_date: str
    data_date: str
    rows: int
    elapsed: float
    universe: str
    db_bytes: int = 0
    added_bytes: int = 0


def columns() -> dict[str, str]:
    """Every metric column and its SQL type."""
    return {k: ("TEXT" if m.kind == catalog.TEXT else "REAL") for k, m in catalog.METRICS.items()}


def ensure_schema(conn) -> None:
    """Create the snapshot tables, and add a column for any metric the catalog
    gained since: older snapshots have it as NULL until they are rebuilt."""
    conn.execute("""CREATE TABLE IF NOT EXISTS snapshot_builds (
        as_of_date TEXT PRIMARY KEY, data_date TEXT, built_at TEXT NOT NULL, rows INTEGER NOT NULL,
        universe TEXT, elapsed_s REAL, catalog_version INTEGER)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS metrics_snapshot (
        as_of_date TEXT NOT NULL, isin TEXT NOT NULL, built_at TEXT NOT NULL,
        PRIMARY KEY (as_of_date, isin))""")
    have = {r[1] for r in conn.execute("PRAGMA table_info(metrics_snapshot)")}
    for name, kind in {**EXTRA_COLUMNS, **columns()}.items():
        if name not in have:
            conn.execute(f'ALTER TABLE metrics_snapshot ADD COLUMN "{name}" {kind}')  # names from the catalog


def has_snapshots(conn) -> bool:
    return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='snapshot_builds'").fetchone())


def list_snapshots(conn) -> list[dict]:
    """The snapshots built, live first, then newest date first."""
    if not has_snapshots(conn):
        return []
    rows = [dict(zip(("as_of", "data_date", "built_at", "rows", "universe", "elapsed", "catalog_version"), r,
                     strict=True))
            for r in conn.execute("SELECT as_of_date, data_date, built_at, rows, universe, elapsed_s, "
                                  "catalog_version FROM snapshot_builds")]
    live = [r for r in rows if r["as_of"] == LIVE]
    return live + sorted((r for r in rows if r["as_of"] != LIVE), key=lambda r: r["as_of"], reverse=True)


def newest_price_day(conn) -> date | None:
    row = conn.execute("SELECT MAX(date) FROM prices_daily").fetchone()
    return date.fromisoformat(row[0]) if row and row[0] else None


def universe_rows(conn, universe: str, as_of: str | None, day: date) -> list[dict]:
    """The securities a snapshot covers (see the module docstring)."""
    universe = (universe or "eq").strip().lower()
    if universe == "all":
        return [dict(r) for r in conn.execute("SELECT * FROM securities ORDER BY isin")]
    if universe not in ("eq", "listed"):
        names = [s.strip() for s in universe.split(",") if s.strip()]
        found, unknown = [], []
        for name in names:
            hit = store.resolve(name, conn)
            (found.append(hit) if hit else unknown.append(name))
        if unknown or not found:
            raise SnapshotError(f"unknown universe {universe!r}: use eq, listed, all or comma-separated "
                                f"symbols{' (not found: ' + ', '.join(unknown) + ')' if unknown else ''}")
        return found
    series = " AND series = 'EQ'" if universe == "eq" else ""
    if as_of is None:
        return [dict(r) for r in conn.execute(
            f"SELECT * FROM securities WHERE status = 'listed'{series} ORDER BY isin")]
    start = (day - timedelta(days=TRADED_WINDOW_DAYS)).isoformat()
    traded = conn.execute(f"SELECT DISTINCT isin FROM prices_daily WHERE date > ? AND date <= ?{series}",
                          (start, day.isoformat())).fetchall()
    if not traded:
        raise SnapshotError(f"no prices in the {TRADED_WINDOW_DAYS} days to {as_of}; sync that period first: "
                            f"tradingagents india sync-prices --from {(day - timedelta(days=400)).isoformat()} "
                            f"--to {as_of}")
    isins = {r[0] for r in traded}
    return [dict(r) for r in conn.execute("SELECT * FROM securities ORDER BY isin") if r["isin"] in isins]


def compute_row(company) -> dict:
    """One security's snapshot row: every catalog metric, plus what the page shows beside it."""
    values = {k: m.value(company) for k, m in catalog.METRICS.items()}
    values.update(isin=company.security["isin"], bse_code=company.security.get("bse_code"),
                  price_date=company.price_day.isoformat() if company.price_day else None,
                  financial=1 if company.financial else 0, basis=company.statements.basis
                  if not company.statements.empty else None)
    return values


def _db_bytes(conn) -> int:
    row = conn.execute("PRAGMA database_list").fetchone()
    path = Path(row[2]) if row and row[2] else None
    if path is None:
        return 0
    return sum(p.stat().st_size for p in (path, Path(f"{path}-wal")) if p.exists())


def build_snapshot(conn, as_of: str | date | None = None, universe: str | None = None,
                   progress=None) -> BuildResult:
    """Build (or rebuild) one snapshot. ``progress(done, total)`` is called as it goes."""
    began = time.monotonic()
    universe = universe or "eq"
    if as_of not in (None, ""):
        day = as_of if isinstance(as_of, date) else date.fromisoformat(str(as_of))
        as_of, key = day.isoformat(), day.isoformat()
        if day > date.today():
            raise SnapshotError(f"--as-of {as_of} is in the future")
    else:
        as_of, key = None, LIVE
        day = newest_price_day(conn) or date.today()
    securities = universe_rows(conn, universe, as_of, day)
    if not securities:
        raise SnapshotError("no securities to build a snapshot of; run `tradingagents india sync-securities` "
                            "and `tradingagents india sync-prices --from <date>` first")
    before = _db_bytes(conn)
    ensure_schema(conn)
    known = dividends_covered(conn, day)
    built_at = datetime.now().isoformat(timespec="seconds")
    names = ["as_of_date", "built_at", *EXTRA_COLUMNS, "isin", *catalog.METRICS]
    names = list(dict.fromkeys(names))
    sql = (f"INSERT INTO metrics_snapshot ({', '.join(chr(34) + n + chr(34) for n in names)}) "
           f"VALUES ({', '.join('?' * len(names))})")
    rows = []
    for i, security in enumerate(securities):
        company = load_company(conn, security, day, as_of=as_of, dividends_known=known)
        values = {**compute_row(company), "as_of_date": key, "built_at": built_at}
        rows.append([values.get(n) for n in names])
        if progress:
            progress(i + 1, len(securities))
    with conn:
        conn.execute("DELETE FROM metrics_snapshot WHERE as_of_date = ?", (key,))
        conn.executemany(sql, rows)
        conn.execute("INSERT OR REPLACE INTO snapshot_builds VALUES (?,?,?,?,?,?,?)",
                     (key, day.isoformat(), built_at, len(rows), universe, round(time.monotonic() - began, 2),
                      catalog.CATALOG_VERSION))
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    after = _db_bytes(conn)
    return BuildResult(key, day.isoformat(), len(rows), time.monotonic() - began, universe, after,
                       max(0, after - before))


def snapshot_info(conn, as_of: str | None) -> dict:
    """The build record of one snapshot, or a SnapshotError saying how to build it."""
    key = as_of or LIVE
    if not has_snapshots(conn):
        raise SnapshotError("There is no metrics snapshot yet. Build one with: "
                            "python -m cli.main india build-snapshot")
    row = conn.execute("SELECT as_of_date, data_date, built_at, rows, universe FROM snapshot_builds "
                       "WHERE as_of_date = ?", (key,)).fetchone()
    if row is None:
        built = [s["as_of"] for s in list_snapshots(conn)]
        command = ("python -m cli.main india build-snapshot" if key == LIVE
                   else f"python -m cli.main india build-snapshot --as-of {key}")
        raise SnapshotError(f"There is no {'live' if key == LIVE else key} snapshot. Build it with: {command}"
                            + (f" (built: {', '.join(built)})" if built else ""))
    return dict(zip(("as_of", "data_date", "built_at", "rows", "universe"), row, strict=True))
