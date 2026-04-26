"""Jintel GraphQL data vendor.

Drop-in module mirroring the yfinance / alpha_vantage surface registered in
``interface.py``. All public functions return CSV / text strings so the
existing LangChain ``@tool`` wrappers in ``tradingagents/agents/utils/`` are
unchanged.

Phase 1 scaffolding. Several response field paths are marked with ``# verify``
comments and need confirmation against the live schema before this vendor is
promoted past opt-in. See the Notion plan
"TradingAgents -> Jintel Migration: Query Plan" for the open-question list.
Default config (``default_config.py``) keeps ``yfinance`` as primary; users opt
in by setting ``data_vendors`` to ``"jintel"`` per category.

Requires:
    pip install jintel
    export JINTEL_API_KEY=...
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Any

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
    FinancialStatementFilterInput,
    InsiderTradeFilterInput,
    NewsFilterInput,
    SortDirection,
)


class JintelRateLimitError(Exception):
    """Raised on rate-limit / quota errors so ``route_to_vendor`` falls back.

    Mirrors ``AlphaVantageRateLimitError`` semantics in
    ``alpha_vantage_common.py:38``.
    """


_client: JintelClient | None = None


def _get_client() -> JintelClient:
    global _client
    if _client is None:
        api_key = os.environ.get("JINTEL_API_KEY")
        if not api_key:
            raise ValueError("JINTEL_API_KEY environment variable is not set.")
        _client = JintelClient(api_key=api_key)
    return _client


def _is_rate_limit(error_msg: str) -> bool:
    msg = error_msg.lower()
    return "rate limit" in msg or "quota" in msg or "429" in msg


def _unwrap(result: Ok | Err, context: str) -> Any:
    if isinstance(result, Err):
        if _is_rate_limit(result.error):
            raise JintelRateLimitError(f"{context}: {result.error}")
        raise JintelError(f"{context}: {result.error}")
    return result.data


# ---- core_stock_apis ---------------------------------------------------

def get_stock(symbol: str, start_date: str, end_date: str) -> str:
    """Drop-in for yfinance ``get_YFin_data_online`` / alpha_vantage ``get_stock``.

    Returns CSV with ``Date,Open,High,Low,Close,Volume`` rows.
    """
    client = _get_client()
    res = client.price_history(
        tickers=[symbol],
        filter=ArrayFilterInput(
            since=start_date, until=end_date, sort=SortDirection.ASC
        ),
    )
    histories = _unwrap(res, f"price_history({symbol})")
    if not histories or not histories[0].history:
        return f"No data returned for {symbol} in {start_date}..{end_date}"
    rows = [
        {"Date": p.date, "Open": p.open, "High": p.high, "Low": p.low,
         "Close": p.close, "Volume": p.volume}
        for p in histories[0].history
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
    from stockstats import wrap

    end_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    start_dt = end_dt - timedelta(days=max(look_back_days * 5, 365))
    csv = get_stock(symbol, start_dt.strftime("%Y-%m-%d"),
                    end_dt.strftime("%Y-%m-%d"))
    df = pd.read_csv(pd.io.common.StringIO(csv))
    df.columns = [c.lower() for c in df.columns]
    df["date"] = pd.to_datetime(df["date"])
    series = wrap(df.set_index("date"))[indicator]
    window = series.tail(look_back_days)
    return window.to_string()


# ---- fundamental_data --------------------------------------------------

def get_fundamentals(ticker: str, curr_date: str | None = None) -> str:
    client = _get_client()
    res = client.enrich_entity(
        ticker, ["market", "analyst"],
        as_of=curr_date,
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


def _fetch_financials(ticker: str, freq: str, curr_date: str | None) -> Any:
    client = _get_client()
    period_types = ["3M"] if freq == "quarterly" else ["12M"]
    res = client.enrich_entity(
        ticker, ["financials"],
        options=EnrichOptions(
            financial_statements_filter=FinancialStatementFilterInput(
                period_types=period_types, limit=8,
            ),
        ),
        as_of=curr_date,
    )
    return _unwrap(res, f"enrich_entity({ticker}, financials)")


def get_balance_sheet(ticker: str, freq: str = "quarterly",
                      curr_date: str | None = None) -> str:
    entity = _fetch_financials(ticker, freq, curr_date)
    if not entity.financials:
        return ""
    # verify: exact attribute path on FinancialStatements model
    stmts = getattr(entity.financials, "balance_sheet", None) or []
    return _financials_to_csv(stmts, [
        "period_ending", "total_assets", "total_liabilities", "total_equity",
        "cash_and_equivalents", "long_term_debt",
    ])


def get_cashflow(ticker: str, freq: str = "quarterly",
                 curr_date: str | None = None) -> str:
    entity = _fetch_financials(ticker, freq, curr_date)
    if not entity.financials:
        return ""
    # verify: exact attribute path on FinancialStatements model
    stmts = getattr(entity.financials, "cash_flow", None) or []
    return _financials_to_csv(stmts, [
        "period_ending", "operating_cash_flow", "investing_cash_flow",
        "financing_cash_flow", "free_cash_flow",
    ])


def get_income_statement(ticker: str, freq: str = "quarterly",
                         curr_date: str | None = None) -> str:
    entity = _fetch_financials(ticker, freq, curr_date)
    if not entity.financials:
        return ""
    # verify: exact attribute path on FinancialStatements model
    stmts = getattr(entity.financials, "income_statement", None) or []
    return _financials_to_csv(stmts, [
        "period_ending", "total_revenue", "gross_profit",
        "operating_income", "net_income", "diluted_eps",
    ])


# ---- news_data ---------------------------------------------------------

def get_news(ticker: str, start_date: str, end_date: str) -> str:
    client = _get_client()
    res = client.enrich_entity(
        ticker, ["news"],
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
        ["SPY", "QQQ", "DIA"], ["news"],
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
                         "title": n.title, "link": n.link})
    rows.sort(key=lambda r: r["date"] or "", reverse=True)
    return pd.DataFrame(rows[: limit * 3]).to_csv(index=False)


def get_insider_transactions(ticker: str) -> str:
    client = _get_client()
    res = client.enrich_entity(
        ticker, ["insiderTrades"],
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
