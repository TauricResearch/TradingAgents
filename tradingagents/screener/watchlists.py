"""Watchlists: named lists of Indian stocks, with notes and, optionally, holdings.

They live in the user database (``userdb``) beside the saved screens. A stock is
kept by ISIN, so a renamed symbol stays on the list, and must be one the India
database knows: it is resolved when added, and a symbol it cannot place is
reported back, never stored.

The table a watchlist shows is ``engine.run`` restricted to its stocks, over the
live metrics snapshot, with the columns and sort saved per watchlist. Prices are
the snapshot's: the latest bhavcopy close, never a live tick. A stock missing
from the snapshot (outside its universe) still shows, with blank figures.

Holdings mode lets each row carry a quantity and an average price (long holdings;
quantities are positive). The table then adds invested value, current value,
P&L and P&L % at that close, and a total row. ``portfolio`` turns the holdings
into the ``PortfolioContext`` the agents take: the same object ``load_portfolio``
reads from a portfolio JSON file, so the Analyze page sends it the way it sends
a file's.

CSV export writes ``symbol,name,note`` (plus ``quantity,avg_price`` in holdings
mode); import reads the same, or any file whose first column (or a column named
``symbol``) holds symbols, and reports each line it could not take and why.
"""

from __future__ import annotations

import csv
import io
import json
import math
import re
from datetime import datetime

from tradingagents.dataflows.vendors.india import store
from tradingagents.portfolio import PortfolioContext, Position
from tradingagents.screener import engine, screens, snapshot

MAX_WATCHLISTS = 100
MAX_ITEMS = 500
MAX_NAME = 60
MAX_NOTE = 500
MAX_CSV_BYTES = 1_000_000
DEFAULT_COLUMNS = ("name", "current_price", "return_1m", "return_1y", "pe", "market_cap", "dividend_yield",
                   "from_52w_high")
_SYMBOL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.&_-]{0,31}$")
_FORMULA_LEAD = ("=", "+", "-", "@", "\t", "\r")


class WatchlistError(ValueError):
    """A watchlist change that cannot be made as asked; the message says why."""


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def display_symbol(security: dict) -> str:
    """How the app names a stock: RELIANCE.NS, else 500325.BO for a BSE-only one."""
    if security.get("nse_symbol"):
        return f"{security['nse_symbol']}.NS"
    if security.get("bse_code"):
        return f"{security['bse_code']}.BO"
    return security["isin"]


# --- Watchlists -----------------------------------------------------------------------

def _summary(row, count: int) -> dict:
    return {"id": row["id"], "name": row["name"], "position": row["position"], "holdings": bool(row["holdings"]),
            "cash": row["cash"], "columns": json.loads(row["columns"] or "[]"),
            "sort": json.loads(row["sort"]) if row["sort"] else None, "count": count,
            "createdAt": row["created_at"], "updatedAt": row["updated_at"]}


def list_watchlists(conn) -> list[dict]:
    counts = dict(conn.execute("SELECT watchlist_id, COUNT(*) FROM watchlist_items GROUP BY watchlist_id"))
    return [_summary(r, counts.get(r["id"], 0))
            for r in conn.execute("SELECT * FROM watchlists ORDER BY position, id")]


def _row(conn, watchlist_id) -> dict:
    try:
        watchlist_id = int(watchlist_id)
    except (TypeError, ValueError):
        raise WatchlistError("No such watchlist.") from None
    row = conn.execute("SELECT * FROM watchlists WHERE id=?", (watchlist_id,)).fetchone()
    if row is None:
        raise WatchlistError("No such watchlist.")
    return row


def items(conn, watchlist_id: int) -> list[dict]:
    return [{"isin": r["isin"], "symbol": r["symbol"], "name": r["name"], "note": r["note"],
             "quantity": r["quantity"], "avgPrice": r["avg_price"], "addedAt": r["added_at"]}
            for r in conn.execute("SELECT * FROM watchlist_items WHERE watchlist_id=? ORDER BY added_at, rowid",
                                  (watchlist_id,))]


def get(conn, watchlist_id) -> dict:
    row = _row(conn, watchlist_id)
    mine = items(conn, row["id"])
    return {**_summary(row, len(mine)), "items": mine}


def _name(value) -> str:
    name = " ".join(str(value or "").split())
    if not name:
        raise WatchlistError("Give the watchlist a name.")
    if len(name) > MAX_NAME:
        raise WatchlistError(f"Watchlist names are at most {MAX_NAME} characters.")
    return name


def _cash(value) -> float | None:
    if value in (None, ""):
        return None
    cash = _number(value, "Cash")
    if cash < 0:
        raise WatchlistError("Cash cannot be negative.")
    return cash


def save(conn, body: dict, ratios=None) -> dict:
    """Create a watchlist, or update the one ``body['id']`` names: its name, columns,
    sort, holdings mode and cash (only the fields ``body`` carries change)."""
    ratios = screens.list_ratios(conn) if ratios is None else ratios
    editing = body.get("id")
    now = _now()
    if editing in (None, ""):
        name = _name(body.get("name"))
        if conn.execute("SELECT COUNT(*) FROM watchlists").fetchone()[0] >= MAX_WATCHLISTS:
            raise WatchlistError(f"At most {MAX_WATCHLISTS} watchlists.")
        columns = screens.clean_columns(body.get("columns"), ratios) if "columns" in body else []
        sort = screens.clean_sort(body.get("sort"), ratios) if "sort" in body else None
        position = conn.execute("SELECT COALESCE(MAX(position), -1) + 1 FROM watchlists").fetchone()[0]
        with conn:
            cur = conn.execute("INSERT INTO watchlists (name, position, columns, sort, holdings, cash, created_at, "
                               "updated_at) VALUES (?,?,?,?,?,?,?,?)",
                               (name, position, json.dumps(columns), json.dumps(sort) if sort else None,
                                1 if body.get("holdings") else 0, _cash(body.get("cash")), now, now))
        return get(conn, cur.lastrowid)
    row = _row(conn, editing)
    fields: dict = {}
    if "name" in body:
        fields["name"] = _name(body["name"])
    if "columns" in body:
        fields["columns"] = json.dumps(screens.clean_columns(body["columns"], ratios))
    if "sort" in body:
        sort = screens.clean_sort(body["sort"], ratios)
        fields["sort"] = json.dumps(sort) if sort else None
    if "holdings" in body:
        fields["holdings"] = 1 if body["holdings"] else 0
    if "cash" in body:
        fields["cash"] = _cash(body["cash"])
    if fields:
        fields["updated_at"] = now
        with conn:
            conn.execute(f"UPDATE watchlists SET {', '.join(f'{k}=?' for k in fields)} WHERE id=?",  # keys above
                         [*fields.values(), row["id"]])
    return get(conn, row["id"])


def reorder(conn, ids: list) -> list[dict]:
    """Put the watchlists in the order ``ids`` gives; any it leaves out follow, as they were."""
    if not isinstance(ids, list):
        raise WatchlistError("Send the watchlists' ids in their new order.")
    known = [r["id"] for r in conn.execute("SELECT id FROM watchlists ORDER BY position, id")]
    try:
        wanted = [int(i) for i in ids]
    except (TypeError, ValueError):
        raise WatchlistError("Watchlist ids are numbers.") from None
    unknown = [i for i in wanted if i not in known]
    if unknown:
        raise WatchlistError(f"No such watchlist: {unknown[0]}.")
    order = list(dict.fromkeys([*wanted, *known]))
    with conn:
        conn.executemany("UPDATE watchlists SET position=? WHERE id=?", list(enumerate(order)))
    return list_watchlists(conn)


def delete(conn, watchlist_id) -> None:
    row = _row(conn, watchlist_id)
    with conn:
        conn.execute("DELETE FROM watchlist_items WHERE watchlist_id=?", (row["id"],))
        conn.execute("DELETE FROM watchlists WHERE id=?", (row["id"],))


# --- Stocks -------------------------------------------------------------------------------

def resolve(symbols, india_conn) -> tuple[list[tuple[str, dict]], list[dict]]:
    """``(typed, security)`` for each symbol the India database knows, and
    ``{"symbol", "reason"}`` for each it does not."""
    found, rejected = [], []
    for raw in symbols:
        text = str(raw or "").strip()
        if not text:
            continue
        if not _SYMBOL.match(text):
            rejected.append({"symbol": text[:40], "reason": "not a symbol (letters, digits and . & _ - only)"})
            continue
        security = store.resolve(text, india_conn) if india_conn is not None else None
        if security is None:
            rejected.append({"symbol": text, "reason": "not in the India database"})
            continue
        found.append((text, security))
    return found, rejected


def add(conn, watchlist_id, symbols: list, india_conn, *, details: dict | None = None) -> dict:
    """Add stocks by symbol (or ISIN). ``details`` maps a typed symbol to its
    note, quantity and average price (CSV import). Returns what was added, what was
    already there (updated from ``details``) and what was rejected, with reasons."""
    row = _row(conn, watchlist_id)
    if not isinstance(symbols, list):
        raise WatchlistError("Send the symbols as a list.")
    found, rejected = resolve(symbols, india_conn)
    have = {r[0] for r in conn.execute("SELECT isin FROM watchlist_items WHERE watchlist_id=?", (row["id"],))}
    added, already, now = [], [], _now()
    with conn:
        for typed, security in found:
            isin, symbol = security["isin"], display_symbol(security)
            extra = (details or {}).get(typed, {})
            if isin in have:
                if extra and symbol not in already:
                    _set_item(conn, row["id"], isin, extra)
                already.append(symbol)
                continue
            if len(have) >= MAX_ITEMS:
                rejected.append({"symbol": typed, "reason": f"the watchlist is full ({MAX_ITEMS} stocks)"})
                continue
            conn.execute("INSERT INTO watchlist_items (watchlist_id, isin, symbol, name, note, added_at) "
                         "VALUES (?,?,?,?,?,?)", (row["id"], isin, symbol, security.get("name"), "", now))
            if extra:
                _set_item(conn, row["id"], isin, extra)
            have.add(isin)
            added.append(symbol)
        conn.execute("UPDATE watchlists SET updated_at=? WHERE id=?", (now, row["id"]))
    return {"added": added, "already": list(dict.fromkeys(already)), "rejected": rejected}


def _match(conn, watchlist_id: int, key: str) -> str | None:
    """The ISIN of the item ``key`` names: its ISIN or its symbol, either case."""
    text = str(key or "").strip().upper()
    for r in conn.execute("SELECT isin, symbol FROM watchlist_items WHERE watchlist_id=?", (watchlist_id,)):
        if text in (r["isin"].upper(), r["symbol"].upper(), r["symbol"].upper().rsplit(".", 1)[0]):
            return r["isin"]
    return None


def remove(conn, watchlist_id, keys: list) -> int:
    row = _row(conn, watchlist_id)
    if not isinstance(keys, list):
        raise WatchlistError("Send the stocks to remove as a list.")
    isins = {i for k in keys if (i := _match(conn, row["id"], k))}
    with conn:
        conn.executemany("DELETE FROM watchlist_items WHERE watchlist_id=? AND isin=?",
                         [(row["id"], i) for i in isins])
        conn.execute("UPDATE watchlists SET updated_at=? WHERE id=?", (_now(), row["id"]))
    return len(isins)


def _number(value, label: str) -> float:
    try:
        number = float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        raise WatchlistError(f"{label} must be a number.") from None
    if not math.isfinite(number):
        raise WatchlistError(f"{label} must be a number.")
    return number


def _clean_item(fields: dict) -> dict:
    out = {}
    if "note" in fields:
        note = str(fields["note"] or "").strip()
        if len(note) > MAX_NOTE:
            raise WatchlistError(f"Notes are at most {MAX_NOTE} characters.")
        out["note"] = note
    if "quantity" in fields:
        q = None if fields["quantity"] in (None, "") else _number(fields["quantity"], "Quantity")
        if q is not None and q <= 0:
            raise WatchlistError("Quantity must be more than 0 (holdings are long positions).")
        out["quantity"] = q
    for key in ("avgPrice", "avg_price"):
        if key in fields:
            p = None if fields[key] in (None, "") else _number(fields[key], "Average price")
            if p is not None and p < 0:
                raise WatchlistError("Average price cannot be negative.")
            out["avg_price"] = p
    return out


def _set_item(conn, watchlist_id: int, isin: str, fields: dict) -> None:
    clean = _clean_item(fields)
    if clean:
        conn.execute(f"UPDATE watchlist_items SET {', '.join(f'{k}=?' for k in clean)} "  # keys from _clean_item
                     "WHERE watchlist_id=? AND isin=?", [*clean.values(), watchlist_id, isin])


def update_item(conn, watchlist_id, key: str, fields: dict) -> dict:
    """Set one stock's note, quantity or average price (only the fields given)."""
    row = _row(conn, watchlist_id)
    isin = _match(conn, row["id"], key)
    if isin is None:
        raise WatchlistError(f"{key} is not on this watchlist.")
    with conn:
        _set_item(conn, row["id"], isin, fields)
        conn.execute("UPDATE watchlists SET updated_at=? WHERE id=?", (_now(), row["id"]))
    return next(i for i in items(conn, row["id"]) if i["isin"] == isin)


# --- CSV ----------------------------------------------------------------------------------

def csv_rows(conn, watchlist_id) -> tuple[list[str], list[list]]:
    """The header and rows the symbols CSV holds."""
    w = get(conn, watchlist_id)
    header = ["symbol", "name", "note"] + (["quantity", "avg_price"] if w["holdings"] else [])
    rows = [[i["symbol"], i["name"] or "", i["note"]] + ([i["quantity"], i["avgPrice"]] if w["holdings"] else [])
            for i in w["items"]]
    return header, rows


def _unescape(cell: str) -> str:
    """Undo the export's formula guard: ``'=x`` was written for ``=x``."""
    return cell[1:] if cell.startswith("'") and cell[1:2] in _FORMULA_LEAD else cell


def import_csv(conn, watchlist_id, text: str, india_conn) -> dict:
    """Add the stocks a CSV lists. Lines that cannot be read are rejected, with the
    line number, and the rest go in."""
    _row(conn, watchlist_id)
    if not isinstance(text, str) or not text.strip():
        raise WatchlistError("The CSV is empty.")
    if len(text.encode("utf-8")) > MAX_CSV_BYTES:
        raise WatchlistError("The CSV is too large (1 MB at most).")
    lines = list(csv.reader(io.StringIO(text.lstrip("﻿"))))
    lines = [[_unescape(c.strip()) for c in line] for line in lines]
    lines = [(n, line) for n, line in enumerate(lines, 1) if any(line)]
    if not lines:
        raise WatchlistError("The CSV is empty.")
    first = [c.lower().replace(" ", "_") for c in lines[0][1]]
    header = "symbol" in first or "ticker" in first
    col = {name: i for i, name in enumerate(first)} if header else {"symbol": 0}
    sym = col.get("symbol", col.get("ticker", 0))
    rows = lines[1:] if header else lines
    if len(rows) > MAX_ITEMS:
        raise WatchlistError(f"The CSV lists {len(rows)} stocks; a watchlist holds at most {MAX_ITEMS}.")
    symbols, details, rejected = [], {}, []
    for n, line in rows:
        typed = line[sym] if sym < len(line) else ""
        if not typed:
            rejected.append({"line": n, "symbol": "", "reason": "no symbol"})
            continue
        extra = {}
        for name, key in (("note", "note"), ("quantity", "quantity"), ("avg_price", "avg_price")):
            i = col.get(name)
            if i is not None and i < len(line) and line[i] != "":
                extra[key] = line[i]
        try:
            _clean_item(extra)
        except WatchlistError as exc:
            rejected.append({"line": n, "symbol": typed, "reason": str(exc)})
            continue
        symbols.append(typed)
        if extra:
            details[typed] = extra
    result = add(conn, watchlist_id, symbols, india_conn, details=details)
    lines_of = {}
    for n, line in rows:
        if sym < len(line):
            lines_of.setdefault(line[sym], n)
    for r in result["rejected"]:
        r.setdefault("line", lines_of.get(r["symbol"]))
    result["rejected"] = sorted(rejected + result["rejected"], key=lambda r: r.get("line") or 0)
    return result


# --- The table and the holdings ---------------------------------------------------------

def position_values(quantity, avg_price, price) -> dict:
    """One holding at ``price``: invested, current value, P&L and P&L % (None where
    an input is missing)."""
    invested = quantity * avg_price if quantity is not None and avg_price is not None else None
    current = quantity * price if quantity is not None and price is not None else None
    pnl = current - invested if current is not None and invested is not None else None
    pnl_pct = pnl / invested * 100 if pnl is not None and invested else None
    return {"invested": invested, "current": current, "pnl": pnl, "pnlPct": pnl_pct}


def totals(positions: list[dict]) -> dict:
    """The total row: sums over the holdings that have every input, so a holding
    with no price does not distort the P&L %."""
    full = [p for p in positions if p["pnl"] is not None]
    invested = sum(p["invested"] for p in full)
    pnl = sum(p["pnl"] for p in full)
    return {"invested": invested if full else None, "current": sum(p["current"] for p in full) if full else None,
            "pnl": pnl if full else None, "pnlPct": pnl / invested * 100 if full and invested else None,
            "counted": len(full), "positions": len(positions)}


def table(conn, watchlist_id, india_conn=None, *, columns=None, sort=None, page_size=None) -> dict:
    """The watchlist with its stocks' snapshot rows, as ``engine.run`` lays them out;
    the stocks the snapshot lacks follow with blank figures. ``note`` says why the
    figures are missing when there is no snapshot at all."""
    w = get(conn, watchlist_id)
    mine = {i["isin"]: i for i in w["items"]}
    ratios = screens.list_ratios(conn)
    chosen = screens.clean_columns(columns, ratios) if columns else (w["columns"] or list(DEFAULT_COLUMNS))
    result, note = None, None
    if mine:
        try:
            result = engine.run("", isins=list(mine), columns=chosen, show_used=False,
                                sort=sort or w["sort"], page_size=page_size or len(mine),
                                max_page_size=engine.MAX_ISINS, user_conn=conn, india_conn=india_conn)
        except (engine.ScreenerUnavailable, snapshot.SnapshotError) as exc:
            note = str(exc)
    if result is None:
        result = {"columns": [engine.describe_column(c, {r.key: r for r in ratios})
                              for c in dict.fromkeys([*engine.BASE_COLUMNS, *chosen])],
                  "rows": [], "median": {}, "sort": sort or w["sort"], "snapshot": None, "total": 0}
    rows = []
    for r in result["rows"]:
        rows.append({**r, "item": mine.pop(r["isin"])})
    for isin, item in mine.items():  # in the watchlist, not in the snapshot
        rows.append({"isin": isin, "symbol": item["symbol"], "nseSymbol": item["symbol"].removesuffix(".NS"),
                     "priceDate": None, "financial": False, "values": {"name": item["name"]}, "item": item,
                     "missing": True})
    holdings = None
    if w["holdings"]:
        positions = []
        for r in rows:
            q, a = r["item"]["quantity"], r["item"]["avgPrice"]
            if q is None:
                continue
            r["position"] = position_values(q, a, r["values"].get("current_price"))
            positions.append(r["position"])
        holdings = totals(positions)
    out = {**result, "rows": rows, "watchlist": {k: v for k, v in w.items() if k != "items"},
           "holdings": holdings, "note": note, "count": len(rows),
           "defaultColumns": list(DEFAULT_COLUMNS)}
    out["total"] = len(rows)
    return out


def portfolio(conn, watchlist_id) -> PortfolioContext:
    """The holdings as the agents' portfolio: each stock with a quantity, at its
    average price, in rupees, with the watchlist's cash."""
    w = get(conn, watchlist_id)
    if not w["holdings"]:
        raise WatchlistError("Turn on holdings mode and enter quantities first.")
    positions = [Position(ticker=i["symbol"], quantity=i["quantity"], average_price=i["avgPrice"])
                 for i in w["items"] if i["quantity"] is not None]
    if not positions:
        raise WatchlistError("No stock on this watchlist has a quantity yet.")
    return PortfolioContext(cash=w["cash"], currency="INR", positions=positions)
