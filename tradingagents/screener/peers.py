"""Peers and industries: a company beside the others NSE files under its industry.

Both read the live metrics snapshot through ``engine.run`` with a query on the
Industry metric, ``Industry = 'Capital Goods'``, which is also the screen the
industry page opens on /screens. NSE gives one level of classification, from
its index lists, so only index members (about 750 stocks) carry an industry; a
company without one has no peers here, and the page says how to refresh it.

Peers are the ``PEER_COUNT`` companies of the industry nearest the company in
market capitalisation, the company included. Nearness is by ratio (the
distance of the logarithms), so a company of 1,000 Cr finds one of 500 Cr as
near as one of 2,000 Cr. Companies without a market cap are never peers, and
when the company has none itself the industry's largest are shown.

Default columns follow the catalog's applicability flag: a metric that does not
apply to banks and NBFCs (``catalog.NON_FINANCIAL``) is swapped for its lender
counterpart, or dropped, when the company is a lender. A company is taken for a
lender when its filings are in the banking or NBFC format (the snapshot's
``financial`` flag) or, with no filings imported, when NSE's industry is
Financial Services.
"""

from __future__ import annotations

import difflib
import math

from tradingagents.dataflows.vendors.india import store
from tradingagents.screener import catalog, engine, snapshot

PEER_COUNT = 10
SCAN_LIMIT = 5000  # industry members read to choose peers from
DEFAULT_COLUMNS = ("name", "current_price", "pe", "market_cap", "dividend_yield", "net_profit_q",
                   "profit_growth_yoy_q", "sales_q", "sales_growth_yoy_q", "roce")
LENDER_SWAPS = {"roce": "roe"}  # a non-financial metric -> what a lender's table shows instead
LENDER_EXTRAS = ("pb", "roa")
FINANCIAL_INDUSTRIES = {"financial services"}
SETUP = "python -m cli.main india sync-all"


class PeersUnavailable(Exception):
    """No peers to show; the message says why and what to run."""


class IndustryNotFound(ValueError):
    pass


def industry_query(name: str) -> str:
    """The screen of one industry, its quotes escaped as the query language reads them."""
    return "Industry = '" + str(name).replace("'", "''") + "'"


def is_lender(financial, industry: str | None) -> bool:
    return bool(financial) or (industry or "").strip().casefold() in FINANCIAL_INDUSTRIES


def default_columns(lender: bool) -> list[str]:
    """The peer table's columns; for a lender, metrics that do not apply to banks
    and NBFCs give way to ``LENDER_SWAPS``, and ``LENDER_EXTRAS`` join."""
    if not lender:
        return list(DEFAULT_COLUMNS)
    out = []
    for key in DEFAULT_COLUMNS:
        if catalog.METRICS[key].applies == catalog.NON_FINANCIAL:
            key = LENDER_SWAPS.get(key)
        if key:
            out.append(key)
    return list(dict.fromkeys([*out, *LENDER_EXTRAS]))


def nearest(members: list[tuple[str, float | None]], isin: str, cap: float | None,
            count: int = PEER_COUNT) -> list[str]:
    """``isin`` and the ``count - 1`` members nearest it in market cap (by ratio);
    the largest when ``cap`` is unknown. Ties go to the larger company."""
    others = [(i, c) for i, c in members if i != isin and c is not None and c > 0]
    if cap is None or cap <= 0:
        ranked = sorted(others, key=lambda m: -m[1])
    else:
        ranked = sorted(others, key=lambda m: (abs(math.log(m[1] / cap)), -m[1]))
    return [isin, *(i for i, _ in ranked[:max(0, count - 1)])]


def _open(india_conn):
    if india_conn is not None:
        return india_conn, False
    try:
        return engine.open_india(), True
    except engine.ScreenerUnavailable as exc:
        raise PeersUnavailable(str(exc)) from None


def _live_row(conn, security: dict) -> dict | None:
    row = conn.execute("SELECT isin, name, industry, market_cap, financial FROM metrics_snapshot "
                       "WHERE as_of_date = ? AND isin = ?", (snapshot.LIVE, security["isin"])).fetchone()
    return dict(row) if row else None


def peers(symbol: str, *, columns: list[str] | None = None, sort: dict | None = None, count: int = PEER_COUNT,
          user_conn=None, india_conn=None, page_size: int | None = None) -> dict:
    """The company's peer table, as ``engine.run`` lays out a screen's results, plus
    the company and industry. Raises PeersUnavailable with what to run."""
    conn, own = _open(india_conn)
    try:
        try:
            info = snapshot.snapshot_info(conn, None)
        except snapshot.SnapshotError as exc:
            raise PeersUnavailable(f"Peers come from the live metrics snapshot. {exc}") from None
        security = store.resolve(symbol, conn)
        if security is None:
            raise PeersUnavailable(f"{symbol.upper()} is not in the India database. Refresh NSE's equity list "
                                   "with: python -m cli.main india sync-securities")
        row = _live_row(conn, security)
        if row is None:
            raise PeersUnavailable(f"{security.get('nse_symbol') or symbol.upper()} is not in the live snapshot, "
                                   f"which covers the {info['universe']} universe. Rebuild it with: "
                                   "python -m cli.main india build-snapshot --universe listed")
        industry = row["industry"]
        if not industry:
            raise PeersUnavailable("NSE gives no industry for this company: only members of its indices carry "
                                   "one. Refresh the industries with: python -m cli.main india sync-securities")
        lender = is_lender(row["financial"], industry)
        query = industry_query(industry)
        members = engine.run(query, columns=["market_cap"], show_used=False, page_size=SCAN_LIMIT,
                             max_page_size=SCAN_LIMIT, user_conn=user_conn, india_conn=conn)
        caps = [(r["isin"], r["values"].get("market_cap")) for r in members["rows"]]
        chosen = nearest(caps, row["isin"], row["market_cap"], count)
        shown = columns or default_columns(lender)
        result = engine.run("", isins=chosen, columns=shown, show_used=False,
                            sort=sort or {"key": "market_cap", "dir": "desc"},
                            page_size=page_size or len(chosen), max_page_size=engine.MAX_ISINS,
                            user_conn=user_conn, india_conn=conn)
    finally:
        if own:
            conn.close()
    return {**result, "available": True, "isin": row["isin"], "company": row["name"], "industry": industry,
            "lender": lender, "industryCount": members["total"], "query": query,
            "defaultColumns": default_columns(lender)}


def industries(india_conn=None) -> list[dict]:
    """Every industry in the live snapshot with its number of stocks, largest first."""
    conn, own = _open(india_conn)
    try:
        snapshot.snapshot_info(conn, None)
        rows = conn.execute("SELECT industry, COUNT(*), SUM(market_cap) FROM metrics_snapshot "
                            "WHERE as_of_date = ? AND industry IS NOT NULL GROUP BY industry "
                            "ORDER BY COUNT(*) DESC, industry", (snapshot.LIVE,)).fetchall()
    finally:
        if own:
            conn.close()
    return [{"name": r[0], "count": r[1], "marketCap": r[2]} for r in rows]


def industry(name: str, *, columns: list[str] | None = None, sort: dict | None = None, page: int = 1,
             page_size: int = engine.PAGE_SIZE, max_page_size: int = engine.MAX_PAGE_SIZE,
             user_conn=None, india_conn=None) -> dict:
    """Every stock of one industry on the live snapshot, with the industry's medians."""
    conn, own = _open(india_conn)
    try:
        known = {i["name"].casefold(): i["name"] for i in industries(conn)}
        canonical = known.get(" ".join(str(name or "").split()).casefold())
        if canonical is None:
            close = difflib.get_close_matches(str(name or ""), list(known.values()), n=3, cutoff=0.5)
            hint = f" Did you mean {' or '.join(repr(c) for c in close)}?" if close else ""
            raise IndustryNotFound(f"No industry called {name!r} in the live snapshot.{hint}")
        lender = is_lender(False, canonical)
        query = industry_query(canonical)
        result = engine.run(query, columns=columns or default_columns(lender), show_used=False, sort=sort,
                            page=page, page_size=page_size, max_page_size=max_page_size,
                            user_conn=user_conn, india_conn=conn)
    finally:
        if own:
            conn.close()
    return {**result, "industry": canonical, "lender": lender, "defaultColumns": default_columns(lender)}
