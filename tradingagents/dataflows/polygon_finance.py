"""Polygon REST implementations for the trading-agents data layer.

This module is the production-default replacement for the yfinance-based
fundamentals path. Polygon's ``/vX/reference/financials`` endpoint returns
as-reported SEC filings with both ``filing_date`` (when the filing became
public) and ``period_of_report_date`` (the fiscal period end), enabling
strict point-in-time semantics that yfinance's snapshot ``info`` cannot
provide.

Public surface intentionally mirrors :mod:`y_finance` so the vendor router
in :mod:`interface` can swap between providers without touching call sites:

* :func:`get_stock_data` — daily OHLCV bars over a date range (CSV string)
* :func:`get_fundamentals` — overview/snapshot fundamentals at ``curr_date``
* :func:`get_balance_sheet`, :func:`get_cashflow`, :func:`get_income_statement`
  — point-in-time financial statements filtered by both filing date and
  period end date
* :func:`get_indicators` — technical indicators computed off Polygon bars
  via ``stockstats``

Forward-looking analyst projections (Forward EPS / PE / PEG) have no
PIT-correct source on Polygon either; we omit them rather than fabricate.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from io import StringIO
from typing import Annotated, Any

import pandas as pd

from .polygon_common import (
    PolygonError,
    PolygonNotFoundError,
    _make_request,
    paginated_results,
)

# --- helpers ----------------------------------------------------------------

# When Polygon returns a financials row without a filing_date, fall back to
# this many days after period_of_report_date as a conservative upper bound on
# when the filing would have been public. SEC large-accelerated 10-Q deadline
# is 40 days, 10-K is 60 days; 90 gives a safety margin while still excluding
# rows whose period ended within the last quarter.
_FILING_LAG_FALLBACK_DAYS = 90


def _parse_date(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d")
    except ValueError:
        return None


def _is_pit_visible(entry: dict, curr_dt: datetime) -> bool:
    """Decide whether a Polygon financials entry was public at ``curr_dt``.

    Rule: filing_date strictly before curr_dt. If filing_date is missing,
    accept only when period_of_report_date + 90d <= curr_dt (conservative).
    Period-of-report alone is never sufficient — the filing happens later.
    """
    filing = _parse_date(entry.get("filing_date"))
    if filing is not None:
        return filing < curr_dt

    period = _parse_date(entry.get("end_date") or entry.get("period_of_report_date"))
    if period is None:
        return False
    return period + timedelta(days=_FILING_LAG_FALLBACK_DAYS) <= curr_dt


def _financials_facts(
    ticker: str,
    *,
    curr_date: str | None,
    timeframe: str,
    limit: int = 8,
) -> list[dict[str, Any]]:
    """Fetch and PIT-filter financials entries.

    timeframe: 'quarterly' or 'annual'
    """
    params: dict[str, Any] = {
        "ticker": ticker.upper(),
        "order": "desc",
        "limit": str(limit),
        "timeframe": timeframe,
    }
    if curr_date:
        params["period_of_report_date.lt"] = curr_date
        params["filing_date.lt"] = curr_date

    try:
        results = paginated_results("/vX/reference/financials", params, max_pages=2)
    except PolygonNotFoundError:
        return []

    if not curr_date:
        return results

    curr_dt = _parse_date(curr_date)
    if curr_dt is None:
        return results

    return [r for r in results if _is_pit_visible(r, curr_dt)]


def _statement_to_csv(entries: list[dict[str, Any]], section: str) -> str:
    """Convert a list of financials entries' ``section`` (e.g. 'balance_sheet')
    into a CSV string with periods as columns and concept labels as rows.
    """
    if not entries:
        return ""

    columns: list[str] = []
    by_concept: dict[str, dict[str, Any]] = {}

    for entry in entries:
        period_end = entry.get("end_date") or entry.get("period_of_report_date") or "unknown"
        timeframe = entry.get("timeframe", "")
        col_name = f"{period_end} ({timeframe})" if timeframe else period_end
        columns.append(col_name)

        section_data = (entry.get("financials") or {}).get(section) or {}
        for concept_key, concept_payload in section_data.items():
            if not isinstance(concept_payload, dict):
                continue
            label = concept_payload.get("label") or concept_key
            value = concept_payload.get("value")
            row = by_concept.setdefault(label, {})
            row[col_name] = value

    if not by_concept:
        return ""

    df = pd.DataFrame.from_dict(by_concept, orient="index", columns=columns)
    df.index.name = "concept"
    return df.to_csv()


def _format_money(value: Any) -> str:
    if value is None:
        return "n/a"
    try:
        v = float(value)
    except (TypeError, ValueError):
        return str(value)
    if abs(v) >= 1e12:
        return f"${v / 1e12:.2f}T"
    if abs(v) >= 1e9:
        return f"${v / 1e9:.2f}B"
    if abs(v) >= 1e6:
        return f"${v / 1e6:.2f}M"
    return f"${v:,.2f}"


def _ttm_sum(entries: list[dict[str, Any]], section: str, concept: str, n: int = 4) -> float | None:
    """Sum the most recent ``n`` quarterly values of ``concept`` in ``section``.
    Returns None if any value is missing (strict TTM)."""
    quarterly = [e for e in entries if e.get("timeframe") == "quarterly"]
    quarterly = quarterly[:n]
    if len(quarterly) < n:
        return None
    total = 0.0
    for e in quarterly:
        s = (e.get("financials") or {}).get(section) or {}
        v = (s.get(concept) or {}).get("value")
        if v is None:
            return None
        try:
            total += float(v)
        except (TypeError, ValueError):
            return None
    return total


def _latest_value(entries: list[dict[str, Any]], section: str, concept: str) -> float | None:
    """Return the value of ``concept`` from the most recent entry, if present."""
    for e in entries:
        s = (e.get("financials") or {}).get(section) or {}
        v = (s.get(concept) or {}).get("value")
        if v is not None:
            try:
                return float(v)
            except (TypeError, ValueError):
                continue
    return None


def _close_at(ticker: str, curr_date: str) -> float | None:
    """Daily close at or before ``curr_date`` (split-adjusted)."""
    curr_dt = _parse_date(curr_date)
    if curr_dt is None:
        return None
    start = (curr_dt - timedelta(days=14)).strftime("%Y-%m-%d")
    end = curr_date
    try:
        payload = _make_request(
            f"/v2/aggs/ticker/{ticker.upper()}/range/1/day/{start}/{end}",
            {"adjusted": "true", "sort": "desc", "limit": 30},
        )
    except PolygonError:
        return None
    bars = payload.get("results") or []
    if not bars:
        return None
    return float(bars[0].get("c"))


def _high_low_window(ticker: str, curr_date: str, days: int) -> tuple[float | None, float | None]:
    curr_dt = _parse_date(curr_date)
    if curr_dt is None:
        return None, None
    start = (curr_dt - timedelta(days=days)).strftime("%Y-%m-%d")
    end = curr_date
    try:
        payload = _make_request(
            f"/v2/aggs/ticker/{ticker.upper()}/range/1/day/{start}/{end}",
            {"adjusted": "true", "sort": "asc", "limit": 50000},
        )
    except PolygonError:
        return None, None
    bars = payload.get("results") or []
    if not bars:
        return None, None
    highs = [float(b.get("h")) for b in bars if b.get("h") is not None]
    lows = [float(b.get("l")) for b in bars if b.get("l") is not None]
    return (max(highs) if highs else None, min(lows) if lows else None)


def _moving_average(ticker: str, curr_date: str, window: int) -> float | None:
    curr_dt = _parse_date(curr_date)
    if curr_dt is None:
        return None
    # Pad backwards to cover non-trading days
    start = (curr_dt - timedelta(days=int(window * 1.6) + 14)).strftime("%Y-%m-%d")
    end = curr_date
    try:
        payload = _make_request(
            f"/v2/aggs/ticker/{ticker.upper()}/range/1/day/{start}/{end}",
            {"adjusted": "true", "sort": "desc", "limit": int(window * 2 + 60)},
        )
    except PolygonError:
        return None
    bars = payload.get("results") or []
    closes = [float(b.get("c")) for b in bars if b.get("c") is not None]
    if len(closes) < window:
        return None
    return sum(closes[:window]) / window


# --- public API -------------------------------------------------------------


def get_stock_data(
    symbol: Annotated[str, "ticker symbol of the company"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
) -> str:
    """Fetch daily OHLCV bars from Polygon and return as CSV (yfinance-shape).

    Bars are split-adjusted (``adjusted=true``) so historical highs/lows align
    with current share counts — necessary for moving-average and 52-week
    range calculations to be meaningful across split events.
    """
    datetime.strptime(start_date, "%Y-%m-%d")
    datetime.strptime(end_date, "%Y-%m-%d")

    try:
        payload = _make_request(
            f"/v2/aggs/ticker/{symbol.upper()}/range/1/day/{start_date}/{end_date}",
            {"adjusted": "true", "sort": "asc", "limit": 50000},
        )
    except PolygonNotFoundError:
        return f"No data found for symbol '{symbol}' between {start_date} and {end_date}"
    except PolygonError as exc:
        return f"Error retrieving data for {symbol}: {exc}"

    bars = payload.get("results") or []
    if not bars:
        return f"No data found for symbol '{symbol}' between {start_date} and {end_date}"

    rows = []
    for bar in bars:
        ts = bar.get("t")
        if ts is None:
            continue
        date = datetime.utcfromtimestamp(ts / 1000).strftime("%Y-%m-%d")
        rows.append({
            "Date": date,
            "Open": round(float(bar.get("o", 0)), 2),
            "High": round(float(bar.get("h", 0)), 2),
            "Low": round(float(bar.get("l", 0)), 2),
            "Close": round(float(bar.get("c", 0)), 2),
            "Adj Close": round(float(bar.get("c", 0)), 2),
            "Volume": int(bar.get("v", 0)),
        })

    df = pd.DataFrame(rows)
    df.set_index("Date", inplace=True)

    header = (
        f"# Stock data for {symbol.upper()} from {start_date} to {end_date}\n"
        f"# Total records: {len(df)}\n"
        f"# Source: Polygon (split-adjusted)\n"
        f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    )
    return header + df.to_csv()


def get_fundamentals(
    ticker: Annotated[str, "ticker symbol of the company"],
    curr_date: Annotated[
        str,
        "current date in YYYY-MM-DD format. Snapshot fields (Market Cap, P/E, "
        "TTM ratios, 52-week ranges, moving averages) are computed point-in-time "
        "from filings and bars available on or before this date.",
    ] = None,
) -> str:
    """Build an overview fundamentals report for ``ticker`` at ``curr_date``.

    Combines Polygon's ``/v3/reference/tickers`` (company metadata, shares,
    SIC code), the latest PIT-visible financials, daily bar history (52w
    range + moving averages), and derived TTM ratios. The market cap shown
    is the as-of value from Polygon's reference data, which uses the share
    count and price valid on ``curr_date`` — eliminating the split-adjustment
    pitfalls the yfinance-derived path had on tickers like NVDA.
    """
    if not curr_date:
        curr_date = datetime.utcnow().strftime("%Y-%m-%d")

    out_lines: list[str] = []
    derived_count = 0

    # Reference data (name, sector, market cap, shares at date)
    try:
        ref = _make_request(
            f"/v3/reference/tickers/{ticker.upper()}",
            {"date": curr_date},
        )
        results = ref.get("results") or {}
    except PolygonNotFoundError:
        return f"No fundamentals data found for symbol '{ticker}'"
    except PolygonError as exc:
        return f"Error retrieving fundamentals for {ticker}: {exc}"

    name = results.get("name")
    if name:
        out_lines.append(f"Name: {name}")
    sic_desc = results.get("sic_description")
    if sic_desc:
        out_lines.append(f"Sector / SIC: {sic_desc}")
    primary_exchange = results.get("primary_exchange")
    if primary_exchange:
        out_lines.append(f"Primary Exchange: {primary_exchange}")

    market_cap = results.get("market_cap")
    if market_cap:
        out_lines.append(f"Market Cap: {_format_money(market_cap)}")
        derived_count += 1
    shares = results.get("share_class_shares_outstanding") or results.get("weighted_shares_outstanding")
    if shares:
        out_lines.append(f"Shares Outstanding: {int(shares):,}")
        derived_count += 1

    # Price + 52-week range
    last_close = _close_at(ticker, curr_date)
    if last_close is not None:
        out_lines.append(f"Last Close (≤ {curr_date}): ${last_close:.2f}")
        derived_count += 1
    high52, low52 = _high_low_window(ticker, curr_date, 365)
    if high52 is not None and low52 is not None:
        out_lines.append(f"52-Week High: ${high52:.2f}")
        out_lines.append(f"52-Week Low: ${low52:.2f}")
        derived_count += 2
    sma50 = _moving_average(ticker, curr_date, 50)
    sma200 = _moving_average(ticker, curr_date, 200)
    if sma50 is not None:
        out_lines.append(f"50-Day Moving Average: ${sma50:.2f}")
        derived_count += 1
    if sma200 is not None:
        out_lines.append(f"200-Day Moving Average: ${sma200:.2f}")
        derived_count += 1

    # Quarterly financials (TTM)
    quarterlies = _financials_facts(ticker, curr_date=curr_date, timeframe="quarterly", limit=8)

    revenue_ttm = _ttm_sum(quarterlies, "income_statement", "revenues")
    net_income_ttm = _ttm_sum(quarterlies, "income_statement", "net_income_loss")
    op_income_ttm = _ttm_sum(quarterlies, "income_statement", "operating_income_loss")
    diluted_eps_ttm = _ttm_sum(quarterlies, "income_statement", "diluted_earnings_per_share")
    basic_eps_ttm = _ttm_sum(quarterlies, "income_statement", "basic_earnings_per_share")
    op_cash_ttm = _ttm_sum(quarterlies, "cash_flow_statement", "net_cash_flow_from_operating_activities")
    capex_ttm = _ttm_sum(quarterlies, "cash_flow_statement", "net_cash_flow_from_investing_activities_continuing")
    gross_profit_ttm = _ttm_sum(quarterlies, "income_statement", "gross_profit")

    if revenue_ttm is not None:
        out_lines.append(f"Revenue (TTM): {_format_money(revenue_ttm)}")
        derived_count += 1
    if gross_profit_ttm is not None:
        out_lines.append(f"Gross Profit (TTM): {_format_money(gross_profit_ttm)}")
        if revenue_ttm:
            out_lines.append(f"Gross Margin (TTM): {gross_profit_ttm / revenue_ttm * 100:.1f}%")
        derived_count += 1
    if op_income_ttm is not None:
        out_lines.append(f"Operating Income (TTM): {_format_money(op_income_ttm)}")
        if revenue_ttm:
            out_lines.append(f"Operating Margin (TTM): {op_income_ttm / revenue_ttm * 100:.1f}%")
        derived_count += 1
    if net_income_ttm is not None:
        out_lines.append(f"Net Income (TTM): {_format_money(net_income_ttm)}")
        if revenue_ttm:
            out_lines.append(f"Profit Margin (TTM): {net_income_ttm / revenue_ttm * 100:.1f}%")
        derived_count += 1

    # Diluted EPS TTM and PE
    eps_ttm = diluted_eps_ttm if diluted_eps_ttm is not None else basic_eps_ttm
    if eps_ttm is not None:
        out_lines.append(f"EPS (TTM): {eps_ttm:.2f}")
        derived_count += 1
        if last_close and eps_ttm > 0:
            out_lines.append(f"P/E (TTM): {last_close / eps_ttm:.2f}")
            derived_count += 1

    # Cash flow detail
    if op_cash_ttm is not None:
        out_lines.append(f"Operating Cash Flow (TTM): {_format_money(op_cash_ttm)}")
        derived_count += 1

    # Latest balance sheet snapshot (most recent quarterly)
    cash = _latest_value(quarterlies, "balance_sheet", "cash_and_equivalents") \
        or _latest_value(quarterlies, "balance_sheet", "cash")
    debt = _latest_value(quarterlies, "balance_sheet", "long_term_debt") \
        or _latest_value(quarterlies, "balance_sheet", "noncurrent_liabilities")
    total_equity = _latest_value(quarterlies, "balance_sheet", "equity") \
        or _latest_value(quarterlies, "balance_sheet", "stockholders_equity")
    total_assets = _latest_value(quarterlies, "balance_sheet", "assets")

    if cash is not None:
        out_lines.append(f"Cash & Equivalents (latest): {_format_money(cash)}")
        derived_count += 1
    if debt is not None:
        out_lines.append(f"Long-Term Debt (latest): {_format_money(debt)}")
        derived_count += 1
    if total_assets is not None:
        out_lines.append(f"Total Assets (latest): {_format_money(total_assets)}")
        derived_count += 1
    if total_equity is not None:
        out_lines.append(f"Stockholders' Equity (latest): {_format_money(total_equity)}")
        derived_count += 1
        if net_income_ttm is not None and total_equity > 0:
            out_lines.append(f"Return on Equity (TTM/avg equity ≈ latest): {net_income_ttm / total_equity * 100:.1f}%")
            derived_count += 1

    # Reporting period reference
    if quarterlies:
        latest = quarterlies[0]
        period_end = latest.get("end_date") or latest.get("period_of_report_date")
        filing_date = latest.get("filing_date")
        if filing_date:
            out_lines.append(
                f"Most recent fiscal period: {period_end} (filed {filing_date})"
            )
        else:
            out_lines.append(
                f"Most recent fiscal period: {period_end} "
                f"(filing date not reported by Polygon — visibility inferred from "
                f"period_of_report + 90-day filing-lag fallback)"
            )

    header = (
        f"# Company Fundamentals for {ticker.upper()}\n"
        f"# Source: Polygon (point-in-time as of {curr_date})\n"
        f"# {derived_count} fields derived from filings & bars available on or before {curr_date}\n"
        f"# Forward-looking analyst projections (Forward EPS / PE / PEG) intentionally omitted —\n"
        f"#   no PIT-correct source.\n"
        f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    )
    return header + "\n".join(out_lines)


def _statement_report(
    ticker: str,
    section: str,
    label: str,
    freq: str,
    curr_date: str | None,
) -> str:
    timeframe = "annual" if (freq or "").lower() == "annual" else "quarterly"
    entries = _financials_facts(ticker, curr_date=curr_date, timeframe=timeframe, limit=8)
    csv_string = _statement_to_csv(entries, section)
    if not csv_string:
        return f"No {label.lower()} data found for symbol '{ticker}'"
    header = (
        f"# {label} data for {ticker.upper()} ({timeframe})\n"
        f"# Source: Polygon (point-in-time, filings public on or before {curr_date or 'latest'})\n"
        f"# Periods returned: {len(entries)}\n"
        f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    )
    return header + csv_string


def get_balance_sheet(
    ticker: Annotated[str, "ticker symbol of the company"],
    freq: Annotated[str, "frequency of data: 'annual' or 'quarterly'"] = "quarterly",
    curr_date: Annotated[str, "current date in YYYY-MM-DD format"] = None,
) -> str:
    return _statement_report(ticker, "balance_sheet", "Balance Sheet", freq, curr_date)


def get_cashflow(
    ticker: Annotated[str, "ticker symbol of the company"],
    freq: Annotated[str, "frequency of data: 'annual' or 'quarterly'"] = "quarterly",
    curr_date: Annotated[str, "current date in YYYY-MM-DD format"] = None,
) -> str:
    return _statement_report(ticker, "cash_flow_statement", "Cash Flow", freq, curr_date)


def get_income_statement(
    ticker: Annotated[str, "ticker symbol of the company"],
    freq: Annotated[str, "frequency of data: 'annual' or 'quarterly'"] = "quarterly",
    curr_date: Annotated[str, "current date in YYYY-MM-DD format"] = None,
) -> str:
    return _statement_report(ticker, "income_statement", "Income Statement", freq, curr_date)


def get_indicators(
    symbol: Annotated[str, "ticker symbol"],
    indicator: Annotated[str, "technical indicator key"],
    curr_date: Annotated[str, "current trading date in YYYY-MM-DD"],
    look_back_days: Annotated[int, "how many days to look back"],
) -> str:
    """Compute indicators by reusing the stockstats path against Polygon bars.

    The stockstats indicator window report itself is vendor-agnostic — it
    delegates to :func:`stockstats_utils.load_ohlcv`, which we patched to
    dispatch on the configured vendor. So we just call the existing
    ``get_stock_stats_indicators_window`` helper; bars come from Polygon
    automatically when ``core_stock_apis = polygon``.
    """
    from .y_finance import get_stock_stats_indicators_window

    return get_stock_stats_indicators_window(
        symbol=symbol,
        indicator=indicator,
        curr_date=curr_date,
        look_back_days=look_back_days,
    )
