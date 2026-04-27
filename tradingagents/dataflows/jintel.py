"""Jintel GraphQL data vendor.

Drop-in module mirroring the yfinance / alpha_vantage surface registered in
``interface.py``. All public functions return CSV / text strings so the
existing LangChain ``@tool`` wrappers in ``tradingagents/agents/utils/`` are
unchanged.

Jintel is the **primary** vendor in ``default_config.py`` across all four
categories. The dispatcher in ``interface.py`` automatically falls through
to ``yfinance`` then ``alpha_vantage`` on:

  * ``JintelRateLimitError``   - 429 / quota exhausted
  * ``JintelNoDataError``      - hard "Jintel doesn't have it" responses,
                                 including a missing ``JINTEL_API_KEY`` env
                                 var (so bare clones still work via yfinance)

Override per-category in ``default_config.DEFAULT_CONFIG["data_vendors"]`` or
per-tool in ``tool_vendors``.

Requires:
    pip install jintel
    export JINTEL_API_KEY=...        # optional; missing key falls through
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Any

logger = logging.getLogger(__name__)

import pandas as pd
from jintel import (
    EnrichOptions,
    Err,
    JintelClient,
    JintelError,
    Ok,
)
from jintel.filters import (
    ArrayFilterInput,
    FilingsFilterInput,
    FinancialStatementFilterInput,
    InsiderTradeFilterInput,
    NewsFilterInput,
    SortDirection,
    TopHoldersFilterInput,
)


class JintelRateLimitError(Exception):
    """Raised on rate-limit / quota errors so ``route_to_vendor`` falls back.

    Mirrors ``AlphaVantageRateLimitError`` semantics in
    ``alpha_vantage_common.py:38``.
    """


class JintelNoDataError(Exception):
    """Raised when Jintel returns a successful response with empty coverage
    for the requested slice (e.g. OHLCV outside the index window, or a ticker
    with no financial statements). The dispatcher catches this and falls
    through to the next vendor in the chain (yfinance / alpha_vantage), which
    may have deeper history.

    Only raised for hard "Jintel doesn't have it" signals -- not for legitimate
    empty slices like "no news this week" or "no insider trades this month",
    where falling back wouldn't add value.
    """


_client: JintelClient | None = None


def _get_client() -> JintelClient:
    global _client
    if _client is None:
        api_key = os.environ.get("JINTEL_API_KEY")
        if not api_key:
            # Raise a fallback-eligible exception so route_to_vendor degrades
            # to yfinance for users who haven't configured Jintel yet, instead
            # of hard-crashing every analyst tool call.
            raise JintelNoDataError(
                "JINTEL_API_KEY not set; falling through to next vendor"
            )
        _client = JintelClient(api_key=api_key)
    return _client


def _is_rate_limit(error_msg: str) -> bool:
    msg = error_msg.lower()
    return "rate limit" in msg or "quota" in msg or "429" in msg


def _is_no_data(error_msg: str) -> bool:
    """Server-side messages that indicate Jintel doesn't have the entity or
    the requested slice -- the dispatcher should fall through to the next
    vendor instead of surfacing the error to the analyst."""
    msg = error_msg.lower()
    return (
        "not found" in msg
        or "no data" in msg
        or "no coverage" in msg
        or "unknown ticker" in msg
    )


def _unwrap(result: Ok | Err, context: str) -> Any:
    if isinstance(result, Err):
        if _is_rate_limit(result.error):
            raise JintelRateLimitError(f"{context}: {result.error}")
        if _is_no_data(result.error):
            raise JintelNoDataError(f"{context}: {result.error}")
        raise JintelError(f"{context}: {result.error}")
    return result.data


# ---- core_stock_apis ---------------------------------------------------

def get_stock(symbol: str, start_date: str, end_date: str) -> str:
    """Drop-in for yfinance ``get_YFin_data_online`` / alpha_vantage ``get_stock``.

    Returns CSV with ``Date,Open,High,Low,Close,Volume`` rows.

    ``client.price_history`` only accepts the preset ``range`` enum, so we use
    ``enrich_entity`` with the ``market`` sub-graph + ``ArrayFilterInput`` to
    get an arbitrary ``[start_date, end_date]`` window.
    """
    client = _get_client()
    # ArrayFilterInput defaults limit to 20; pass an explicit cap large enough
    # to cover any reasonable backtest window (~40 yrs of trading days).
    res = client.enrich_entity(
        symbol,
        fields=["market"],
        options=EnrichOptions(
            filter=ArrayFilterInput(
                since=start_date, until=end_date, limit=10000,
                sort=SortDirection.ASC,
            ),
        ),
    )
    entity = _unwrap(res, f"enrich_entity({symbol}, market)")
    history = (entity.market.history if entity.market else None) or []
    if not history:
        # Jintel's history index is roughly the trailing ~250 trading days; an
        # empty window means out-of-coverage, not "the market closed". Surface
        # as JintelNoDataError so route_to_vendor falls through to yfinance.
        raise JintelNoDataError(
            f"No OHLCV for {symbol} in {start_date}..{end_date}"
        )
    rows = [
        {"Date": p.date, "Open": p.open, "High": p.high, "Low": p.low,
         "Close": p.close, "Volume": p.volume}
        for p in history
    ]
    return pd.DataFrame(rows).set_index("Date").to_csv()


# ---- technical_indicators ----------------------------------------------

def get_indicator(symbol: str, indicator: str, curr_date: str,
                  look_back_days: int = 30) -> str:
    """Drop-in for yfinance ``get_stock_stats_indicators_window``.

    Jintel ``TechnicalIndicators`` returns scalar latest values, not a windowed
    series, so we fetch OHLCV via Jintel and compute the windowed indicator
    locally with ``stockstats`` -- same downstream as the yfinance path at
    ``y_finance.py:198``.
    """
    from io import StringIO

    from stockstats import wrap

    end_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    start_dt = end_dt - timedelta(days=max(look_back_days * 5, 365))
    # If get_stock raises JintelNoDataError the dispatcher falls through to
    # yfinance for get_indicators -- correct behavior, no need to catch here.
    csv = get_stock(symbol, start_dt.strftime("%Y-%m-%d"),
                    end_dt.strftime("%Y-%m-%d"))
    df = pd.read_csv(StringIO(csv))
    df.columns = [c.lower() for c in df.columns]
    df["date"] = pd.to_datetime(df["date"])
    series = wrap(df.set_index("date"))[indicator]
    window = series.tail(look_back_days)
    return window.to_string()


# ---- fundamental_data --------------------------------------------------

def get_fundamentals(ticker: str, curr_date: str | None = None) -> str:
    """``MarketData.quote`` and ``Entity.fundamentals`` are in
    ``UNSUPPORTED_AS_OF_FIELDS`` -- Jintel returns null for them in PIT mode.
    We deliberately omit ``as_of`` here so callers get a populated live
    snapshot. Look-ahead bias for fundamentals is documented as a known
    limitation; backtest reproducibility for fundamentals must rely on
    ``get_balance_sheet`` / ``get_cashflow`` / ``get_income_statement``,
    which do honor ``as_of``.
    """
    client = _get_client()
    res = client.enrich_entity(
        ticker,
        fields=["market", "analyst"],
    )
    entity = _unwrap(res, f"enrich_entity({ticker}, fundamentals)")
    lines = [f"# Fundamentals for {ticker} (as_of={curr_date or 'live'})"]
    if entity.market and entity.market.quote:
        q = entity.market.quote
        lines.append(f"price: {q.price}")
        lines.append(f"market_cap: {q.market_cap}")
    if entity.market and entity.market.fundamentals:
        for k, v in entity.market.fundamentals.model_dump().items():
            if v is not None:
                lines.append(f"{k}: {v}")
    if entity.analyst is not None:
        for k, v in entity.analyst.model_dump().items():
            if v is not None:
                lines.append(f"analyst_{k}: {v}")
    return "\n".join(lines)


def _financials_to_csv(stmts: list[Any], cols: list[str]) -> str:
    if not stmts:
        return ""
    rows = []
    for s in stmts:
        d = s.model_dump()
        rows.append({c: d.get(c) for c in cols})
    return pd.DataFrame(rows).to_csv(index=False)


@lru_cache(maxsize=128)
def _fetch_financials_cached(ticker: str, curr_date: str | None) -> Any:
    """Per-process memo of one ``enrich_entity(ticker, ["financials"])`` call.

    Keyed on ``(ticker, curr_date)`` so that when an analyst fans out
    ``get_balance_sheet`` + ``get_cashflow`` + ``get_income_statement`` for
    the same ticker on the same date in one turn (typical of
    ``fundamentals_analyst.py``), Jintel sees a single round-trip instead of
    three identical ones.
    """
    client = _get_client()
    res = client.enrich_entity(
        ticker,
        fields=["financials"],
        options=EnrichOptions(
            financial_statements_filter=FinancialStatementFilterInput(
                until=curr_date, limit=8, sort=SortDirection.DESC,
            ),
        ),
    )
    return _unwrap(res, f"enrich_entity({ticker}, financials)")


def _fetch_financials(ticker: str, freq: str, curr_date: str | None) -> Any:
    """Jintel's ``period_types`` enum coverage varies by ticker (not every
    ticker has a ``3M`` series), so we drop the period filter and take
    whatever's available. Look-ahead bias is enforced via
    ``FinancialStatementFilterInput.until`` rather than ``as_of`` mode --
    in practice ``as_of`` returns null financials despite ``Entity.financials``
    not being in ``UNSUPPORTED_AS_OF_FIELDS``.

    The actual fetch is delegated to ``_fetch_financials_cached`` so the
    three financial-statement getters share one round-trip per
    ``(ticker, curr_date)``.
    """
    if freq and freq.lower() != "annual":
        logger.info(
            "jintel: %s freq=%r requested but Jintel coverage is annual-only "
            "for many tickers; returning all available periods (let the "
            "consumer slice).",
            ticker, freq,
        )
    return _fetch_financials_cached(ticker, curr_date)


def _require_financials(ticker: str, entity: Any) -> Any:
    """Raise JintelNoDataError when Jintel has no financial statements at all
    for the ticker, so the dispatcher falls through to yfinance. A populated
    entity.financials with one or more empty sub-lists is a sparser-coverage
    issue (returned as-is, possibly empty CSV) rather than a hard miss."""
    if entity.financials is None:
        raise JintelNoDataError(f"No financial statements for {ticker}")
    return entity.financials


def get_balance_sheet(ticker: str, freq: str = "quarterly",
                      curr_date: str | None = None) -> str:
    entity = _fetch_financials(ticker, freq, curr_date)
    fins = _require_financials(ticker, entity)
    return _financials_to_csv(fins.balance_sheet or [], [
        "period_ending", "total_assets", "total_liabilities", "total_equity",
        "cash_and_equivalents", "long_term_debt",
    ])


def get_cashflow(ticker: str, freq: str = "quarterly",
                 curr_date: str | None = None) -> str:
    entity = _fetch_financials(ticker, freq, curr_date)
    fins = _require_financials(ticker, entity)
    return _financials_to_csv(fins.cash_flow or [], [
        "period_ending", "operating_cash_flow", "investing_cash_flow",
        "financing_cash_flow", "free_cash_flow",
    ])


def get_income_statement(ticker: str, freq: str = "quarterly",
                         curr_date: str | None = None) -> str:
    entity = _fetch_financials(ticker, freq, curr_date)
    fins = _require_financials(ticker, entity)
    # FinancialStatements.income holds the income statement series.
    return _financials_to_csv(fins.income or [], [
        "period_ending", "total_revenue", "gross_profit",
        "operating_income", "net_income", "diluted_eps",
    ])


# ---- news_data ---------------------------------------------------------

def get_news(ticker: str, start_date: str, end_date: str) -> str:
    client = _get_client()
    res = client.enrich_entity(
        ticker,
        fields=["news"],
        options=EnrichOptions(
            news_filter=NewsFilterInput(
                since=start_date, until=end_date, limit=50,
                sort=SortDirection.DESC,
            ),
        ),
    )
    entity = _unwrap(res, f"enrich_entity({ticker}, news)")
    if not entity.news:
        return ""
    rows = [
        {"date": n.date, "source": n.source, "title": n.title,
         "sentiment": n.sentiment_score, "link": n.link}
        for n in entity.news
    ]
    return pd.DataFrame(rows).to_csv(index=False)


def get_global_news(curr_date: str, look_back_days: int = 7,
                    limit: int = 5) -> str:
    """Bellwether-basket fan-out (Jintel has no documented top-level
    ``globalNews`` field). Phase 1: query news for SPY / QQQ / DIA, dedupe.
    """
    since = (datetime.strptime(curr_date, "%Y-%m-%d")
             - timedelta(days=look_back_days)).strftime("%Y-%m-%d")
    client = _get_client()
    res = client.batch_enrich(
        ["SPY", "QQQ", "DIA"],
        fields=["news"],
        options=EnrichOptions(
            news_filter=NewsFilterInput(
                since=since, until=curr_date, limit=limit,
                sort=SortDirection.DESC,
            ),
        ),
    )
    entities = _unwrap(res, "batch_enrich(global_news)")
    seen: set[str] = set()
    rows = []
    for entity in entities:
        for n in (entity.news or []):
            if n.link in seen:
                continue
            seen.add(n.link)
            rows.append({"date": n.date, "source": n.source,
                         "title": n.title, "sentiment": n.sentiment_score,
                         "link": n.link})
    rows.sort(key=lambda r: r["date"] or "", reverse=True)
    return pd.DataFrame(rows[: limit * 3]).to_csv(index=False)


def get_insider_transactions(ticker: str) -> str:
    client = _get_client()
    res = client.enrich_entity(
        ticker,
        fields=["insiderTrades"],
        options=EnrichOptions(
            insider_trades_filter=InsiderTradeFilterInput(
                limit=100, sort=SortDirection.DESC,
            ),
        ),
    )
    entity = _unwrap(res, f"enrich_entity({ticker}, insider_trades)")
    if not entity.insider_trades:
        return ""
    rows = [
        {"date": t.transaction_date, "insider": t.reporter_name,
         "title": t.officer_title, "transaction": t.transaction_code,
         "direction": t.acquired_disposed, "shares": t.shares,
         "price": t.price_per_share, "value": t.transaction_value}
        for t in entity.insider_trades
    ]
    return pd.DataFrame(rows).to_csv(index=False)


# ---- Phase 4: NEW capabilities (jintel-only; no yfinance fallback) -----

def get_filings(ticker: str, curr_date: str | None = None) -> str:
    """Recent SEC periodic filings (10-K / 10-Q / 8-K) for ``ticker``.

    Each row carries form / filing_date / report_date / filing_url. ``curr_date``
    enforces no-lookahead at the filter layer.
    """
    client = _get_client()
    res = client.enrich_entity(
        ticker,
        fields=["periodicFilings"],
        options=EnrichOptions(
            filings_filter=FilingsFilterInput(
                until=curr_date,
                types=["FILING_10K", "FILING_10Q", "FILING_8K"],
                limit=8, sort=SortDirection.DESC,
            ),
        ),
    )
    entity = _unwrap(res, f"enrich_entity({ticker}, periodicFilings)")
    if not entity.periodic_filings:
        raise JintelNoDataError(f"No periodic filings for {ticker}")
    rows = [
        {"form": f.form, "filing_date": f.filing_date,
         "report_date": f.report_date, "filing_url": f.filing_url}
        for f in entity.periodic_filings
    ]
    return pd.DataFrame(rows).to_csv(index=False)


def get_macro_series(series_id: str, curr_date: str | None = None,
                     look_back_days: int = 365) -> str:
    """FRED-style US macro time series (e.g. ``UNRATE``, ``CPIAUCSL``,
    ``GDPC1``, ``FEDFUNDS``). Returns CSV with ``date,value`` rows.
    """
    since = None
    if curr_date:
        since = (datetime.strptime(curr_date, "%Y-%m-%d")
                 - timedelta(days=look_back_days)).strftime("%Y-%m-%d")
    client = _get_client()
    res = client.macro_series(
        series_id,
        filter=ArrayFilterInput(
            since=since, until=curr_date, limit=10000, sort=SortDirection.ASC,
        ),
    )
    series = _unwrap(res, f"macro_series({series_id})")
    if not series or not series.observations:
        raise JintelNoDataError(f"No macro series {series_id}")
    rows = [{"date": pt.date, "value": pt.value} for pt in series.observations]
    return pd.DataFrame(rows).to_csv(index=False)


def get_top_holders(ticker: str) -> str:
    """13F institutional top holders for ``ticker``. CSV: filer / value / shares
    / report_date / filing_date.
    """
    client = _get_client()
    res = client.enrich_entity(
        ticker,
        fields=["topHolders"],
        options=EnrichOptions(
            top_holders_filter=TopHoldersFilterInput(
                limit=20, sort=SortDirection.DESC,
            ),
        ),
    )
    entity = _unwrap(res, f"enrich_entity({ticker}, topHolders)")
    if not entity.top_holders:
        raise JintelNoDataError(f"No top holders for {ticker}")
    rows = [
        {"filer": h.filer_name, "cik": h.cik, "value": h.value,
         "shares": h.shares, "report_date": h.report_date,
         "filing_date": h.filing_date}
        for h in entity.top_holders
    ]
    return pd.DataFrame(rows).to_csv(index=False)
