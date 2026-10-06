"""The India database: schema, idempotent writes, and point-in-time reads.

SQLite through the standard library, at TRADINGAGENTS_INDIA_DB (default
``~/.tradingagents/india/india.db``). Every write is an upsert on the table's
key, so a sync run twice stores each row once.

Point in time
-------------
Every financial and shareholding value carries ``filed_at``, when its filing
became public (India time, ``YYYY-MM-DDTHH:MM:SS``). A restated period is a
second row with a later ``filed_at``; nothing is overwritten. A read "as of D"
sees only rows filed on or before D (a date means the whole of that day, as in
the SEC EDGAR vendor) and, for each period and field, the latest of those. No
``as_of`` reads the latest of everything: the live Company page.

These reads import nothing from the Company page's code, so a later phase can
serve them to the agents through ``router.py`` as an ``india`` vendor:

    get_financials(isin, as_of=..., basis=...)    get_shareholding(isin, as_of=...)
    get_prices(isin, as_of=..., adjusted=True)    get_corporate_actions(isin, as_of=...)
    get_documents(isin, as_of=...)                get_shares_outstanding(isin, as_of=...)
    resolve(symbol)                               status()
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from contextlib import closing
from datetime import date, datetime, timedelta
from pathlib import Path

from tradingagents.dataflows.config import get_config
from tradingagents.dataflows.vendors.india.actions import cumulative_factors, rights_factor

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);

-- One row per ISIN: NSE's equity list joined with NSE's index industry lists.
CREATE TABLE IF NOT EXISTS securities (
    isin TEXT PRIMARY KEY,
    nse_symbol TEXT, bse_code TEXT, name TEXT, series TEXT,
    industry TEXT,            -- NSE's industry from its index lists (e.g. "Oil Gas & Consumable Fuels")
    sector TEXT,              -- reserved for a finer classification
    face_value REAL, listing_date TEXT,
    status TEXT,              -- listed (in today's EQUITY_L) | unlisted (seen before, not now) | filing-only
    updated_at TEXT
);
CREATE INDEX IF NOT EXISTS securities_symbol ON securities (nse_symbol);

-- Which ISIN a symbol meant, from the bhavcopies that carry both; maps files keyed
-- by symbol alone (old prices, deliveries, corporate actions) across renames.
CREATE TABLE IF NOT EXISTS symbol_history (
    symbol TEXT NOT NULL, isin TEXT NOT NULL, first_date TEXT, last_date TEXT,
    PRIMARY KEY (symbol, isin)
) WITHOUT ROWID;

-- Daily prices as traded (never adjusted in storage; reads adjust).
CREATE TABLE IF NOT EXISTS prices_daily (
    isin TEXT NOT NULL, date TEXT NOT NULL,
    open REAL, high REAL, low REAL, close REAL NOT NULL, volume INTEGER, deliverable_qty INTEGER,
    series TEXT, source TEXT,
    PRIMARY KEY (isin, date)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS prices_daily_date ON prices_daily (date);

-- Shares issued, a row each time NSE's figure changes (PR zip, mcap file).
CREATE TABLE IF NOT EXISTS shares_outstanding (
    isin TEXT NOT NULL, date TEXT NOT NULL, shares INTEGER NOT NULL, face_value REAL, source TEXT,
    PRIMARY KEY (isin, date)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS corporate_actions (
    isin TEXT NOT NULL, ex_date TEXT NOT NULL,
    type TEXT NOT NULL,       -- dividend | split | bonus | rights | demerger | buyback | capital_reduction
    details TEXT NOT NULL,    -- NSE's purpose text, as published
    ratio_num REAL, ratio_den REAL,   -- bonus/rights a:b; split old:new face value
    amount REAL,              -- dividend per share, or the rights issue price
    factor REAL,              -- what earlier prices are divided by (split, bonus); NULL otherwise
    record_date TEXT, symbol TEXT, series TEXT,
    first_seen TEXT,          -- the first PR file that listed it: when it was known
    source TEXT,
    PRIMARY KEY (isin, ex_date, type, details)
) WITHOUT ROWID;

-- Each XBRL filing imported, with when it became public and how that was told.
CREATE TABLE IF NOT EXISTS filings (
    filing_id TEXT PRIMARY KEY,
    isin TEXT NOT NULL, kind TEXT NOT NULL,   -- results | shareholding
    format TEXT,              -- indas | banking | nbfc | shp
    basis TEXT,               -- standalone | consolidated (results)
    period_end TEXT, filed_at TEXT NOT NULL, filed_at_basis TEXT,
    symbol TEXT, scrip_code TEXT, taxonomy TEXT, url TEXT, raw_path TEXT, source TEXT, imported_at TEXT
);
CREATE INDEX IF NOT EXISTS filings_isin ON filings (isin, kind, period_end);

-- Results, long and narrow: one row per company, period, basis, field and vintage.
CREATE TABLE IF NOT EXISTS financials (
    isin TEXT NOT NULL,
    period_end TEXT NOT NULL,
    period_type TEXT NOT NULL,   -- Q quarter | H half year | N nine months | A year | I balance sheet date
    basis TEXT NOT NULL,         -- standalone | consolidated
    field TEXT NOT NULL,         -- field_aliases' names: sales, net_profit, eps, total_debt, ...
    value REAL NOT NULL,
    unit TEXT NOT NULL,          -- INR (rupees, never crores) | INR/share | pure | shares
    period_start TEXT,
    source TEXT NOT NULL, filing_id TEXT NOT NULL,
    filed_at TEXT NOT NULL,
    PRIMARY KEY (isin, period_end, period_type, basis, field, filed_at)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS financials_field_period ON financials (field, period_end);

CREATE TABLE IF NOT EXISTS shareholding (
    isin TEXT NOT NULL, quarter_end TEXT NOT NULL, filed_at TEXT NOT NULL,
    promoter_pct REAL, fii_pct REAL, dii_pct REAL, govt_pct REAL, public_pct REAL, others_pct REAL,
    num_shareholders INTEGER, total_shares INTEGER,
    pledged_pct REAL,         -- promoter shares pledged, % of promoter shares
    encumbered_pct REAL,      -- pledged or otherwise encumbered, % of promoter shares
    filing_id TEXT, source TEXT,
    PRIMARY KEY (isin, quarter_end, filed_at)
) WITHOUT ROWID;

-- Links only; the documents themselves are never downloaded.
CREATE TABLE IF NOT EXISTS documents (
    isin TEXT NOT NULL, date TEXT NOT NULL,
    kind TEXT NOT NULL,       -- results | shareholding | annual_report | concall | credit_rating |
                              -- investor_presentation | board_meeting | announcement
    title TEXT NOT NULL, url TEXT, source TEXT,
    PRIMARY KEY (isin, date, kind, title)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS documents_date ON documents (date);

-- What each sync did with each key (a day, a file): resumability and audit.
CREATE TABLE IF NOT EXISTS ingest_log (
    job TEXT NOT NULL, key TEXT NOT NULL,
    status TEXT NOT NULL,     -- ok | missing (no such file: a holiday) | failed
    error TEXT, detail TEXT, rows INTEGER, fetched_at TEXT NOT NULL,
    PRIMARY KEY (job, key)
);

-- XBRL elements no field reads and no list explains, counted across filings.
CREATE TABLE IF NOT EXISTS xbrl_unknown_tags (
    tag TEXT NOT NULL, format TEXT NOT NULL, count INTEGER NOT NULL, last_filing TEXT,
    PRIMARY KEY (tag, format)
);
"""

DONE = ("ok", "missing")


def db_path() -> Path:
    return Path(get_config()["india_db_path"]).expanduser()


def connect(path: str | Path | None = None) -> sqlite3.Connection:
    """The database, created with its schema when absent."""
    path = Path(path) if path else db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=60)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.executescript(SCHEMA)
    conn.execute("INSERT OR IGNORE INTO meta VALUES ('schema_version', ?)", (str(SCHEMA_VERSION),))
    conn.commit()
    return conn


def open_existing(path: str | Path | None = None) -> sqlite3.Connection | None:
    """The database read-only, or None when it does not exist yet (the Company
    page then shows what it did before any sync)."""
    path = Path(path) if path else db_path()
    if not path.is_file():
        return None
    try:
        conn = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("SELECT 1 FROM financials LIMIT 1")
        return conn
    except sqlite3.Error:
        return None


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def cutoff(as_of: str | date | datetime | None) -> str | None:
    """The last ``filed_at`` an as-of read may see. A date covers its whole day."""
    if as_of is None or as_of == "":
        return None
    if isinstance(as_of, datetime):
        return as_of.replace(tzinfo=None).isoformat(timespec="seconds")
    text = as_of.isoformat() if isinstance(as_of, date) else str(as_of).strip().replace(" ", "T")
    if len(text) == 10:
        date.fromisoformat(text)  # a malformed date raises rather than silently matching nothing
        return f"{text}T23:59:59"
    return datetime.fromisoformat(text).replace(tzinfo=None).isoformat(timespec="seconds")


def _day(as_of) -> str | None:
    limit = cutoff(as_of)
    return limit[:10] if limit else None


# --- Writes ---------------------------------------------------------------------------

def log(conn, job: str, key: str, status: str, *, error: str | None = None, detail: str | None = None,
        rows: int | None = None) -> None:
    conn.execute("INSERT OR REPLACE INTO ingest_log VALUES (?,?,?,?,?,?,?)",
                 (job, key, status, error, detail, rows, _now()))


def is_done(conn, job: str, key: str) -> bool:
    row = conn.execute("SELECT status FROM ingest_log WHERE job=? AND key=?", (job, key)).fetchone()
    return row is not None and row[0] in DONE


def upsert_securities(conn, rows: Iterable[dict]) -> int:
    """Securities by ISIN; a field a row leaves blank keeps its stored value."""
    n = 0
    for r in rows:
        conn.execute("""
            INSERT INTO securities (isin, nse_symbol, bse_code, name, series, industry, sector, face_value,
                                    listing_date, status, updated_at)
            VALUES (:isin, :nse_symbol, :bse_code, :name, :series, :industry, :sector, :face_value,
                    :listing_date, :status, :updated_at)
            ON CONFLICT (isin) DO UPDATE SET
                nse_symbol = COALESCE(excluded.nse_symbol, nse_symbol),
                bse_code = COALESCE(excluded.bse_code, bse_code),
                name = COALESCE(excluded.name, name), series = COALESCE(excluded.series, series),
                industry = COALESCE(excluded.industry, industry), sector = COALESCE(excluded.sector, sector),
                face_value = COALESCE(excluded.face_value, face_value),
                listing_date = COALESCE(excluded.listing_date, listing_date),
                status = CASE WHEN excluded.status = 'filing-only' AND status IS NOT NULL THEN status
                              ELSE COALESCE(excluded.status, status) END,
                updated_at = excluded.updated_at""",
                     {"isin": r["isin"], "nse_symbol": r.get("nse_symbol"), "bse_code": r.get("bse_code"),
                      "name": r.get("name"), "series": r.get("series"), "industry": r.get("industry"),
                      "sector": r.get("sector"), "face_value": r.get("face_value"),
                      "listing_date": r.get("listing_date"), "status": r.get("status"), "updated_at": _now()})
        n += 1
    return n


def upsert_symbol_history(conn, rows: Iterable[tuple[str, str, str]]) -> None:
    """(symbol, isin, day) sightings, widened into first/last dates."""
    conn.executemany("""
        INSERT INTO symbol_history VALUES (?, ?, ?, ?)
        ON CONFLICT (symbol, isin) DO UPDATE SET
            first_date = MIN(first_date, excluded.first_date), last_date = MAX(last_date, excluded.last_date)""",
                     [(s, i, d, d) for s, i, d in rows])


def symbol_map(conn, day: str) -> dict[str, str]:
    """symbol -> ISIN as of ``day``: the bhavcopies' own pairing nearest that day,
    else today's equity list."""
    out = {r[0]: r[1] for r in conn.execute(
        "SELECT nse_symbol, isin FROM securities WHERE nse_symbol IS NOT NULL")}
    target = date.fromisoformat(day)
    best: dict[str, tuple[int, str]] = {}
    for symbol, isin, first, last in conn.execute("SELECT symbol, isin, first_date, last_date FROM symbol_history"):
        if first <= day <= last:
            distance = 0
        else:
            distance = min(abs((target - date.fromisoformat(first)).days),
                           abs((target - date.fromisoformat(last)).days))
        if symbol not in best or distance < best[symbol][0]:
            best[symbol] = (distance, isin)
    out.update({symbol: isin for symbol, (_, isin) in best.items()})
    return out


def upsert_prices(conn, rows: Iterable[tuple]) -> int:
    """(isin, date, open, high, low, close, volume, series, source); EQ beats other series."""
    rows = list(rows)
    conn.executemany("""
        INSERT INTO prices_daily (isin, date, open, high, low, close, volume, series, source)
        VALUES (?,?,?,?,?,?,?,?,?)
        ON CONFLICT (isin, date) DO UPDATE SET
            open = excluded.open, high = excluded.high, low = excluded.low, close = excluded.close,
            volume = excluded.volume, series = excluded.series, source = excluded.source
        WHERE excluded.series = 'EQ' OR prices_daily.series IS NOT 'EQ'""", rows)
    return len(rows)


def set_deliveries(conn, day: str, deliveries: Iterable[tuple[str, int]]) -> None:
    conn.executemany("UPDATE prices_daily SET deliverable_qty=? WHERE isin=? AND date=?",
                     [(qty, isin, day) for isin, qty in deliveries])


def record_shares(conn, isin: str, day: str, shares: int, face_value: float | None, source: str) -> bool:
    """Store shares issued when they differ from the figure in force on ``day``."""
    row = conn.execute("SELECT shares FROM shares_outstanding WHERE isin=? AND date<=? ORDER BY date DESC LIMIT 1",
                       (isin, day)).fetchone()
    if row is not None and row[0] == shares:
        return False
    conn.execute("INSERT OR REPLACE INTO shares_outstanding VALUES (?,?,?,?,?)",
                 (isin, day, shares, face_value, source))
    return True


def upsert_action(conn, *, isin, ex_date, type, details, ratio_num=None, ratio_den=None, amount=None,
                  factor=None, record_date=None, symbol=None, series=None, seen=None, source="NSE PR") -> None:
    conn.execute("""
        INSERT INTO corporate_actions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT (isin, ex_date, type, details) DO UPDATE SET
            ratio_num = excluded.ratio_num, ratio_den = excluded.ratio_den, amount = excluded.amount,
            factor = excluded.factor, record_date = COALESCE(excluded.record_date, record_date),
            first_seen = MIN(COALESCE(first_seen, excluded.first_seen), excluded.first_seen)""",
                 (isin, ex_date, type, details, ratio_num, ratio_den, amount, factor, record_date, symbol,
                  series, seen, source))


def upsert_filing(conn, *, filing_id, isin, kind, format, basis, period_end, filed_at, filed_at_basis,
                  symbol, scrip_code, taxonomy, url, raw_path, source) -> None:
    conn.execute("INSERT OR REPLACE INTO filings VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                 (filing_id, isin, kind, format, basis, period_end, filed_at, filed_at_basis, symbol,
                  scrip_code, taxonomy, url, raw_path, source, _now()))


def upsert_financials(conn, *, isin, basis, filing_id, filed_at, source, rows) -> int:
    """A filing's rows, keyed by vintage: re-importing it rewrites the same rows,
    and a later filing of the same period adds rows beside them."""
    data = [(isin, end, kind, basis, field, value, unit, start, source, filing_id, filed_at)
            for end, kind, start, field, value, unit in rows]
    conn.executemany("INSERT OR REPLACE INTO financials VALUES (?,?,?,?,?,?,?,?,?,?,?)", data)
    return len(data)


def upsert_shareholding(conn, *, isin, quarter_end, filed_at, values, filing_id, source) -> None:
    conn.execute("INSERT OR REPLACE INTO shareholding VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                 (isin, quarter_end, filed_at, values.get("promoter_pct"), values.get("fii_pct"),
                  values.get("dii_pct"), values.get("govt_pct"), values.get("public_pct"),
                  values.get("others_pct"), _int(values.get("num_shareholders")),
                  _int(values.get("total_shares")), values.get("pledged_pct"), values.get("encumbered_pct"),
                  filing_id, source))


def _int(value):
    return None if value is None else int(round(value))


def upsert_documents(conn, rows: Iterable[tuple]) -> int:
    """(isin, date, kind, title, url, source)."""
    rows = list(rows)
    conn.executemany("""
        INSERT INTO documents VALUES (?,?,?,?,?,?)
        ON CONFLICT (isin, date, kind, title) DO UPDATE SET url = COALESCE(excluded.url, url)""", rows)
    return len(rows)


def record_unknown_tags(conn, counts, fmt: str, filing_id: str) -> None:
    conn.executemany("""
        INSERT INTO xbrl_unknown_tags VALUES (?,?,?,?)
        ON CONFLICT (tag, format) DO UPDATE SET count = count + excluded.count, last_filing = excluded.last_filing""",
                     [(tag, fmt, n, filing_id) for tag, n in counts.items()])


# --- Point-in-time reads ------------------------------------------------------------------

def _conn(conn):
    return closing(connect()) if conn is None else _Borrowed(conn)


class _Borrowed:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self.conn

    def __exit__(self, *exc):
        return False


def resolve(symbol: str, conn=None) -> dict | None:
    """The security a symbol names: an ISIN, an NSE symbol (``RELIANCE``,
    ``RELIANCE.NS``) or a BSE code or symbol (``500325.BO``, ``RELIANCE.BO``)."""
    text = (symbol or "").strip().upper()
    base, _, suffix = text.rpartition(".") if text.endswith((".NS", ".BO")) else (text, "", "")
    with _conn(conn) as c:
        if len(base) == 12 and base.startswith("IN"):
            row = c.execute("SELECT * FROM securities WHERE isin=?", (base,)).fetchone()
        elif suffix == "BO" and base.isdigit():
            row = c.execute("SELECT * FROM securities WHERE bse_code=?", (base,)).fetchone()
        else:
            row = c.execute("SELECT * FROM securities WHERE nse_symbol=? ORDER BY status='listed' DESC",
                            (base,)).fetchone()
            if row is None:
                hit = c.execute("SELECT isin FROM symbol_history WHERE symbol=? ORDER BY last_date DESC",
                                (base,)).fetchone()
                row = hit and c.execute("SELECT * FROM securities WHERE isin=?", (hit[0],)).fetchone()
        return dict(row) if row else None


def get_financials(isin: str, as_of=None, basis: str | None = None, period_types: Iterable[str] | None = None,
                   fields: Iterable[str] | None = None, conn=None) -> list[dict]:
    """Each period's figures as known ``as_of``: per period, basis and field, the
    latest row filed on or before it. Rows are dicts with period_end, period_type,
    period_start, basis, field, value, unit, filed_at and filing_id."""
    where, args = ["isin = ?"], [isin]
    if (limit := cutoff(as_of)) is not None:
        where.append("filed_at <= ?")
        args.append(limit)
    if basis:
        where.append("basis = ?")
        args.append(basis)
    for column, values in (("period_type", period_types), ("field", fields)):
        if values is not None:
            values = list(values)
            where.append(f"{column} IN ({','.join('?' * len(values))})")
            args += values
    sql = f"""
        SELECT period_end, period_type, period_start, basis, field, value, unit, filed_at, filing_id FROM (
            SELECT *, ROW_NUMBER() OVER (PARTITION BY period_end, period_type, basis, field
                                         ORDER BY filed_at DESC) AS vintage
            FROM financials WHERE {' AND '.join(where)})
        WHERE vintage = 1 ORDER BY period_end, period_type, field"""
    with _conn(conn) as c:
        return [dict(r) for r in c.execute(sql, args)]


def get_shareholding(isin: str, as_of=None, conn=None) -> list[dict]:
    """Each quarter's shareholding pattern as known ``as_of``, oldest first."""
    where, args = "isin = ?", [isin]
    if (limit := cutoff(as_of)) is not None:
        where += " AND filed_at <= ?"
        args.append(limit)
    sql = f"""
        SELECT * FROM (SELECT *, ROW_NUMBER() OVER (PARTITION BY quarter_end ORDER BY filed_at DESC) AS vintage
                       FROM shareholding WHERE {where})
        WHERE vintage = 1 ORDER BY quarter_end"""
    with _conn(conn) as c:
        rows = [dict(r) for r in c.execute(sql, args)]
    for r in rows:
        r.pop("vintage", None)
    return rows


def get_corporate_actions(isin: str, as_of=None, conn=None) -> list[dict]:
    """Actions known by ``as_of`` (first listed in a PR file by then), by ex-date."""
    where, args = "isin = ?", [isin]
    if (day := _day(as_of)) is not None:
        where += " AND COALESCE(first_seen, ex_date) <= ?"
        args.append(day)
    with _conn(conn) as c:
        return [dict(r) for r in c.execute(f"SELECT * FROM corporate_actions WHERE {where} ORDER BY ex_date", args)]


def adjustment_events(isin: str, as_of=None, conn=None) -> list[dict]:
    """The split, bonus and rights actions that moved per-share figures by
    ``as_of`` (ex-date on or before it; today without one, since NSE lists an
    action before its ex-date), each with its factor; rights get theirs from the
    close before the ex-date."""
    day = _day(as_of) or date.today().isoformat()
    out = []
    with _conn(conn) as c:
        for a in get_corporate_actions(isin, as_of, c):
            if a["type"] not in ("split", "bonus", "rights") or (day and a["ex_date"] > day):
                continue
            factor = a["factor"]
            if a["type"] == "rights":
                cum = c.execute("SELECT close FROM prices_daily WHERE isin=? AND date<? ORDER BY date DESC LIMIT 1",
                                (isin, a["ex_date"])).fetchone()
                factor = rights_factor(a["ratio_num"] or 0, a["ratio_den"] or 0, a["amount"], cum and cum[0])
            if factor and factor > 0 and abs(factor - 1) > 1e-9:
                out.append({**a, "factor": factor})
    return out


def get_prices(isin: str, start: str | None = None, end: str | None = None, adjusted: bool = True,
               as_of=None, conn=None) -> list[dict]:
    """Daily prices, oldest first, up to ``as_of``. Adjusted prices divide each day
    before a split, bonus or rights ex-date by its factor and multiply volume by it,
    using only actions in force by ``as_of``; dividends are not adjusted for."""
    where, args = ["isin = ?"], [isin]
    day = _day(as_of)
    last = min(d for d in (end, day) if d) if (end or day) else None
    if start:
        where.append("date >= ?")
        args.append(start)
    if last:
        where.append("date <= ?")
        args.append(last)
    with _conn(conn) as c:
        rows = [dict(r) for r in c.execute(
            f"SELECT date, open, high, low, close, volume, deliverable_qty, series, source FROM prices_daily "
            f"WHERE {' AND '.join(where)} ORDER BY date", args)]
        if not adjusted or not rows:
            return rows
        events = [(e["ex_date"], e["factor"]) for e in adjustment_events(isin, as_of or last, c)]
    factors = cumulative_factors([r["date"] for r in rows], events)
    for r, f in zip(rows, factors, strict=True):
        if f != 1.0:
            for k in ("open", "high", "low", "close"):
                if r[k] is not None:
                    r[k] = r[k] / f
            for k in ("volume", "deliverable_qty"):
                if r[k] is not None:
                    r[k] = int(round(r[k] * f))
    return rows


def per_share_factor(filed_at: str, events: list[dict]) -> float:
    """What an as-filed per-share figure (EPS) is divided by to compare with today's
    shares: the splits and bonuses after it was filed. Ind AS 33 restates EPS for
    those between the period end and the approval, so the filing date is the line."""
    product = 1.0
    for e in events:
        if e["ex_date"] > filed_at[:10]:
            product *= e["factor"]
    return product


def get_shares_outstanding(isin: str, as_of=None, conn=None) -> dict | None:
    where, args = "isin = ?", [isin]
    if (day := _day(as_of)) is not None:
        where += " AND date <= ?"
        args.append(day)
    with _conn(conn) as c:
        row = c.execute(f"SELECT * FROM shares_outstanding WHERE {where} ORDER BY date DESC LIMIT 1", args).fetchone()
        return dict(row) if row else None


def get_documents(isin: str, as_of=None, kinds: Iterable[str] | None = None, limit: int | None = None,
                  conn=None) -> list[dict]:
    """Document links dated on or before ``as_of``, newest first."""
    where, args = ["isin = ?"], [isin]
    if (day := _day(as_of)) is not None:
        where.append("date <= ?")
        args.append(day)
    if kinds is not None:
        kinds = list(kinds)
        where.append(f"kind IN ({','.join('?' * len(kinds))})")
        args += kinds
    sql = f"SELECT * FROM documents WHERE {' AND '.join(where)} ORDER BY date DESC, kind, title"
    if limit:
        sql += f" LIMIT {int(limit)}"
    with _conn(conn) as c:
        return [dict(r) for r in c.execute(sql, args)]


def get_filings(isin: str, kind: str | None = None, conn=None) -> list[dict]:
    where, args = "isin = ?", [isin]
    if kind:
        where += " AND kind = ?"
        args.append(kind)
    with _conn(conn) as c:
        return [dict(r) for r in c.execute(f"SELECT * FROM filings WHERE {where} ORDER BY period_end, filed_at",
                                           args)]


def status(conn=None) -> dict:
    """Row counts, latest dates, recent failures and the commonest unknown tags."""
    with _conn(conn) as c:
        counts = {t: c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in (
            "securities", "prices_daily", "shares_outstanding", "corporate_actions", "filings",
            "financials", "shareholding", "documents", "ingest_log")}
        latest = {
            "prices": c.execute("SELECT MIN(date), MAX(date) FROM prices_daily").fetchone(),
            "corporate_actions": c.execute("SELECT MIN(ex_date), MAX(ex_date) FROM corporate_actions").fetchone(),
            "financials": c.execute("SELECT MIN(period_end), MAX(period_end) FROM financials").fetchone(),
            "filed": c.execute("SELECT MIN(filed_at), MAX(filed_at) FROM filings").fetchone(),
            "shareholding": c.execute("SELECT MIN(quarter_end), MAX(quarter_end) FROM shareholding").fetchone(),
            "documents": c.execute("SELECT MIN(date), MAX(date) FROM documents").fetchone(),
        }
        jobs = c.execute("""SELECT job, status, COUNT(*), MAX(fetched_at) FROM ingest_log
                            GROUP BY job, status ORDER BY job, status""").fetchall()
        failures = c.execute("""SELECT job, key, error, fetched_at FROM ingest_log WHERE status='failed'
                                ORDER BY fetched_at DESC LIMIT 20""").fetchall()
        unknown = c.execute("SELECT tag, format, count FROM xbrl_unknown_tags ORDER BY count DESC LIMIT 15").fetchall()
        companies = c.execute("SELECT COUNT(DISTINCT isin) FROM financials").fetchone()[0]
    return {"counts": counts, "latest": {k: tuple(v) for k, v in latest.items()},
            "jobs": [tuple(j) for j in jobs], "failures": [tuple(f) for f in failures],
            "unknown_tags": [tuple(u) for u in unknown], "companies_with_results": companies}


def trading_days(start: date, end: date) -> list[date]:
    """Weekdays from ``start`` to ``end``; holidays show up as missing files."""
    out, day = [], start
    while day <= end:
        if day.weekday() < 5:
            out.append(day)
        day += timedelta(days=1)
    return out
