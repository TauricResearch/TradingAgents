"""LangChain @tool wrapper around compute_range_stats."""

from typing import Annotated

from langchain_core.tools import tool

from tradingagents.dataflows.range_stats import (
    RangeStatsUnavailable,
    compute_range_stats,
    format_range_stats_markdown,
)


@tool
def get_range_stats(
    symbol: Annotated[str, "ticker symbol of the company"],
    trade_date: Annotated[str, "current trading date in YYYY-MM-DD"],
) -> str:
    """Compute today's open / close / volume vs 52w / 6m / 3m / 1m high-low ranges
    (% above period low, % below period high, position-in-range %).

    Use this to anchor the price/volume context — e.g. assess whether the stock
    is at a 52-week high, near a one-month low, or where it sits in its recent
    range — before selecting indicators."""
    try:
        stats = compute_range_stats(symbol, trade_date)
    except RangeStatsUnavailable:
        return f"Range stats unavailable for {symbol} on {trade_date}."
    except Exception as e:  # noqa: BLE001 — defensive at boundary
        return f"Range stats error for {symbol}: {e}"
    return format_range_stats_markdown(stats)
