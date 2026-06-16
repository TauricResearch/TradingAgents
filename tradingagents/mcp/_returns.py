"""Realized-return / alpha computation for the MCP ``get_realized_return`` tool.

This mirrors the pure-data math in
:meth:`tradingagents.graph.trading_graph.TradingAgentsGraph._fetch_returns`
and ``_resolve_benchmark`` but lives here as standalone functions because the
graph versions are methods on a class whose construction creates LLM clients
(and would therefore need API keys). The MCP server needs none of that — this
is yfinance arithmetic only — so the logic is reproduced rather than imported.
Kept in sync with the graph by reusing the same ``benchmark_map`` from config.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

import yfinance as yf

from tradingagents.dataflows.config import get_config
from tradingagents.dataflows.symbol_utils import normalize_symbol

logger = logging.getLogger(__name__)


def resolve_benchmark(ticker: str) -> str:
    """Pick the alpha-baseline benchmark for ``ticker`` from config.

    ``benchmark_ticker`` (when set) overrides everything; otherwise the
    exchange-suffix map is consulted (e.g. ``.T`` -> Nikkei). US tickers with
    no recognised suffix fall through to the empty-suffix entry (SPY). Mirrors
    :meth:`TradingAgentsGraph._resolve_benchmark`.
    """
    config = get_config()
    explicit = config.get("benchmark_ticker")
    if explicit:
        return explicit
    benchmark_map = config.get("benchmark_map", {})
    ticker_upper = ticker.upper()
    for suffix, benchmark in benchmark_map.items():
        if suffix and ticker_upper.endswith(suffix.upper()):
            return benchmark
    return benchmark_map.get("", "SPY")


def fetch_realized_return(
    ticker: str,
    trade_date: str,
    holding_days: int = 5,
    benchmark: str | None = None,
) -> dict:
    """Return realized raw/alpha return for ``ticker`` over a holding window.

    ``benchmark`` defaults to the config-resolved index for the ticker's
    market. Returns a dict with ``available`` False when price data is not yet
    available (too recent, delisted, or a network error) so the caller can
    report cleanly instead of failing. Mirrors ``_fetch_returns``.
    """
    if benchmark is None:
        benchmark = resolve_benchmark(ticker)

    try:
        start = datetime.strptime(trade_date, "%Y-%m-%d")
        end = start + timedelta(days=holding_days + 7)  # buffer for weekends/holidays
        end_str = end.strftime("%Y-%m-%d")

        stock = yf.Ticker(normalize_symbol(ticker)).history(start=trade_date, end=end_str)
        bench = yf.Ticker(benchmark).history(start=trade_date, end=end_str)

        if len(stock) < 2 or len(bench) < 2:
            return {
                "ticker": ticker,
                "trade_date": trade_date,
                "benchmark": benchmark,
                "available": False,
                "reason": "Price data not yet available (too recent, delisted, or no data).",
            }

        actual_days = min(holding_days, len(stock) - 1, len(bench) - 1)
        raw = float(
            (stock["Close"].iloc[actual_days] - stock["Close"].iloc[0])
            / stock["Close"].iloc[0]
        )
        bench_ret = float(
            (bench["Close"].iloc[actual_days] - bench["Close"].iloc[0])
            / bench["Close"].iloc[0]
        )
        alpha = raw - bench_ret
        return {
            "ticker": ticker,
            "trade_date": trade_date,
            "benchmark": benchmark,
            "available": True,
            "holding_days": actual_days,
            "raw_return": raw,
            "benchmark_return": bench_ret,
            "alpha_return": alpha,
        }
    except Exception as e:  # noqa: BLE001 — fail open, this feeds best-effort reflection
        logger.warning(
            "Could not resolve realized return for %s on %s vs %s: %s",
            ticker, trade_date, benchmark, e,
        )
        return {
            "ticker": ticker,
            "trade_date": trade_date,
            "benchmark": benchmark,
            "available": False,
            "reason": f"Lookup failed: {e}",
        }
