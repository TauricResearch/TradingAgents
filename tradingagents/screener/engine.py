"""Running screens: validate a query, run it over a snapshot, page and sort the result.

A run reports, beside the matching rows, how many stocks the condition left out
only because a value it needs is missing (``excluded``), the median of each
column over the matches, and which snapshot it read. Queries run under a time
limit enforced inside SQLite.
"""

from __future__ import annotations

import statistics
import time
from datetime import date

from tradingagents.dataflows.vendors.india import store
from tradingagents.screener import catalog, screens, snapshot
from tradingagents.screener.compiler import Compiler, column
from tradingagents.screener.query import NUMBER_TYPE, QueryError, Ref, parse, references

TIME_LIMIT_SECONDS = 2.0
PAGE_SIZE = 50
MAX_PAGE_SIZE = 200
DEFAULT_SORT = {"key": "market_cap", "dir": "desc"}
BASE_COLUMNS = ("name", "current_price")


class ScreenerUnavailable(Exception):
    """No India database, or no snapshot to read; the message says what to run."""


class ScreenTimeout(Exception):
    pass


def open_india():
    """The India database, read-only, or ScreenerUnavailable."""
    conn = store.open_existing()
    if conn is None:
        raise ScreenerUnavailable(f"There is no India database yet at {store.db_path()}. Fill it, then build the "
                                  "metrics snapshot: python -m cli.main india sync-all")
    return conn


def _names_and_ratios(user_conn):
    ratios = screens.list_ratios(user_conn) if user_conn is not None else []
    names = screens.name_table(ratios)
    return ratios, names, screens.parse_ratios(ratios, names)


def validate(query: str, user_conn=None) -> dict:
    """``{"ok": True, "metrics": [...]}`` or ``{"ok": False, "errors": [{message, start, end, line, col}]}``."""
    ratios, names, asts = _names_and_ratios(user_conn)
    try:
        node = parse(query or "", names)
        Compiler(asts, query).compile(node)
    except QueryError as exc:
        return {"ok": False, "errors": [exc.to_dict()]}
    used = [_column_id(n) for n in references(node)]
    warnings = []
    banks = [catalog.METRICS[n.key].name for n in references(node)
             if n.kind == "metric" and catalog.METRICS[n.key].applies == catalog.NON_FINANCIAL]
    if banks:
        warnings.append(f"{', '.join(banks)} {'does' if len(banks) == 1 else 'do'} not apply to banks and NBFCs, "
                        "so they are left out wherever it is used.")
    return {"ok": True, "errors": [], "columns": used, "warnings": warnings}


def _column_id(name) -> str:
    return name.key if name.kind == "metric" else screens.RATIO_PREFIX + name.key


def describe_column(column_id: str, ratios: dict[str, screens.Ratio]) -> dict:
    if column_id.startswith(screens.RATIO_PREFIX):
        r = ratios[column_id.removeprefix(screens.RATIO_PREFIX)]
        return {"id": column_id, "name": r.name, "unit": "", "kind": "number", "decimals": 2,
                "category": "Custom ratios", "description": f"{r.name} = {r.expression}", "custom": True}
    m = catalog.METRICS[column_id]
    return {"id": column_id, "name": m.name, "unit": m.unit, "kind": m.kind, "decimals": m.decimals,
            "category": m.category, "description": m.description, "custom": False}


def metrics_payload(user_conn=None, india_conn=None) -> dict:
    """The catalog for autocomplete and docs, the custom ratios, and the snapshots built."""
    ratios = screens.list_ratios(user_conn) if user_conn is not None else []
    snaps = snapshot.list_snapshots(india_conn) if india_conn is not None else []
    return {
        "categories": list(catalog.CATEGORIES),
        "metrics": catalog.catalog(),
        "ratios": [r.describe() for r in ratios],
        "snapshots": snaps,
        "limits": {"queryLength": 4000, "timeSeconds": TIME_LIMIT_SECONDS, "pageSize": PAGE_SIZE},
    }


def _deadline(conn, seconds: float):
    stop = time.monotonic() + seconds
    conn.set_progress_handler(lambda: 1 if time.monotonic() > stop else 0, 2000)


def _median(values: list) -> float | None:
    numbers = [v for v in values if isinstance(v, (int, float))]
    return statistics.median(numbers) if numbers else None


def run(query: str, *, columns: list[str] | None = None, sort: dict | None = None, page: int = 1,
        page_size: int = PAGE_SIZE, as_of: str | None = None, user_conn=None, india_conn=None,
        time_limit: float = TIME_LIMIT_SECONDS) -> dict:
    """Run ``query`` over the snapshot for ``as_of`` (the live one by default)."""
    began = time.monotonic()
    ratios, names, asts = _names_and_ratios(user_conn)
    by_key = {r.key: r for r in ratios}
    node = parse(query or "", names)
    compiler = Compiler(asts, query)
    where = compiler.compile(node)

    if as_of not in (None, "", snapshot.LIVE):
        try:
            as_of = date.fromisoformat(str(as_of)).isoformat()
        except ValueError:
            raise snapshot.SnapshotError(f"as_of must be a date (YYYY-MM-DD) or 'live', not {as_of!r}") from None
    else:
        as_of = None
    own = india_conn is None
    conn = open_india() if own else india_conn
    try:
        info = snapshot.snapshot_info(conn, as_of)
        key = info["as_of"]

        used = [_column_id(n) for n in references(node)]
        extras = screens.clean_columns(columns, ratios) if columns else []
        shown = list(dict.fromkeys([*BASE_COLUMNS, *used, *extras]))  # the query's metrics always show
        sort = screens.clean_sort(sort, ratios) or (
            DEFAULT_SORT if "market_cap" in shown or not used else {"key": used[0], "dir": "desc"})
        if sort["key"] not in shown:
            shown.append(sort["key"])

        def expr(column_id: str) -> tuple[str, list]:
            if column_id.startswith(screens.RATIO_PREFIX):
                r = by_key[column_id.removeprefix(screens.RATIO_PREFIX)]
                c = compiler.compile(Ref(0, 0, NUMBER_TYPE, screens.ratio_name(r)))
                return c.sql, c.params
            return column(column_id), []

        compiled = [expr(c) for c in shown]
        selected = [sql for sql, _ in compiled]
        select_params = [p for _, params in compiled for p in params]
        sort_sql, sort_params = expr(sort["key"])
        direction = "ASC" if sort["dir"] == "asc" else "DESC"
        page_size = max(1, min(int(page_size or PAGE_SIZE), MAX_PAGE_SIZE))

        _deadline(conn, time_limit)
        try:
            total, matched, excluded, excluded_financial = conn.execute(
                f"SELECT COUNT(*), COALESCE(SUM(CASE WHEN {where.sql} THEN 1 ELSE 0 END), 0), "
                f"COALESCE(SUM(CASE WHEN ({where.sql}) IS NULL THEN 1 ELSE 0 END), 0), "
                f"COALESCE(SUM(CASE WHEN ({where.sql}) IS NULL AND financial = 1 THEN 1 ELSE 0 END), 0) "
                "FROM metrics_snapshot WHERE as_of_date = ?",
                [*where.params, *where.params, *where.params, key]).fetchone()
            pages = max(1, -(-matched // page_size))
            page = max(1, min(int(page or 1), pages))
            rows = conn.execute(
                f"SELECT isin, nse_symbol, bse_code, price_date, financial, {', '.join(selected)} "
                f"FROM metrics_snapshot WHERE as_of_date = ? AND {where.sql} "
                f"ORDER BY {sort_sql} {direction} NULLS LAST, name COLLATE NOCASE LIMIT ? OFFSET ?",
                [*select_params, key, *where.params, *sort_params, page_size, (page - 1) * page_size]).fetchall()
            numeric = [i for i, c in enumerate(shown) if describe_column(c, by_key)["kind"] == "number"]
            medians = {}
            if matched and numeric:
                every = conn.execute(
                    f"SELECT {', '.join(selected[i] for i in numeric)} FROM metrics_snapshot "
                    f"WHERE as_of_date = ? AND {where.sql}",
                    [*[p for i in numeric for p in compiled[i][1]], key, *where.params]).fetchall()
                medians = {shown[i]: _median([r[j] for r in every]) for j, i in enumerate(numeric)}
        except Exception as exc:
            if "interrupted" in str(exc):
                raise ScreenTimeout(f"The screen took longer than {time_limit:g} s and was stopped; "
                                    "simplify the condition.") from None
            raise
        finally:
            conn.set_progress_handler(None, 0)
    finally:
        if own:
            conn.close()

    out_rows = []
    for r in rows:
        values = dict(zip(shown, r[5:], strict=True))
        symbol = f"{r[1]}.NS" if r[1] else (f"{r[2]}.BO" if r[2] else r[0])
        out_rows.append({"isin": r[0], "symbol": symbol, "nseSymbol": r[1], "priceDate": r[3],
                         "financial": bool(r[4]), "values": values})
    return {
        "query": query,
        "columns": [describe_column(c, by_key) for c in shown],
        "rows": out_rows,
        "total": matched,
        "excluded": excluded,
        "excludedFinancial": excluded_financial,
        "universe": total,
        "median": medians,
        "page": page, "pages": pages, "pageSize": page_size,
        "sort": sort,
        "used": used,
        "snapshot": info,
        "elapsedMs": round((time.monotonic() - began) * 1000, 1),
    }
