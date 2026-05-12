"""Cross-vendor ETF top-holdings drill-down.

Given an ETF ticker, resolve its top-N constituents via the configured
``etf_data`` vendor, then call the existing fundamentals / news routes
for each constituent so the analyst can reason about the underlying
names instead of just aggregate weights.

This module orchestrates other dispatch calls; it doesn't talk to
upstream vendors directly. Constituent fundamentals + news flow
through the normal ``route_to_vendor`` chain, so a US holding gets
US-vendor data and a HK holding gets HK-vendor data without any
special casing here.
"""

from __future__ import annotations

from .etf_utils import is_etf_ticker

# Per-section character caps. The drill-down already costs ``2 * top_n``
# upstream calls; trimming each section keeps the LLM's context window
# from being dominated by a single noisy news source.
_FUNDAMENTALS_CHAR_LIMIT = 1500
_NEWS_CHAR_LIMIT = 1200


def _truncate(value: object, limit: int) -> str:
    """Render ``value`` as a string and cap to ``limit`` characters with
    an explicit truncation marker so the LLM doesn't assume the body is
    complete."""
    text = value if isinstance(value, str) else str(value)
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + f"\n…(truncated, full length {len(text)})"


def get_etf_top_holdings_drilldown(
    ticker: str,
    start_date: str,
    end_date: str,
    top_n: int = 3,
) -> str:
    """Drill into an ETF's top-N constituents and emit a per-name report.

    Each constituent costs one fundamentals call plus one news call, so
    the default ``top_n=3`` keeps token + latency budgets sane. Callers
    should generally cap at 5.

    Returns a markdown report with one section per constituent, separated
    by horizontal rules. Per-constituent errors are caught and rendered
    inline so one bad ticker can't kill the whole drill-down.
    """
    # Local imports defer the route_to_vendor binding so this module
    # doesn't create an import cycle with interface.py.
    from .interface import route_to_vendor

    if not is_etf_ticker(ticker):
        return (
            f"Drill-down only applies to ETF tickers; {ticker} appears to be a "
            "regular stock. Use get_fundamentals and get_news directly."
        )

    try:
        holdings = route_to_vendor("get_top_holding_tickers", ticker, top_n)
    except Exception as exc:  # noqa: BLE001 — degrade rather than abort
        return f"Could not resolve top holdings for {ticker}: {exc}"

    if not holdings:
        return f"No top holdings could be resolved for {ticker}."

    sections: list[str] = [
        f"# Top-{len(holdings)} holdings drill-down for ETF {ticker}",
        f"# Fundamentals + news fetched per constituent at {start_date}..{end_date}",
        "",
    ]
    for h_ticker, h_name, weight in holdings:
        block = [f"## {h_name} ({h_ticker}) — weight: {weight:.2f}%"]
        try:
            fundamentals = route_to_vendor("get_fundamentals", h_ticker, end_date)
            block.append("### Fundamentals")
            block.append(_truncate(fundamentals, _FUNDAMENTALS_CHAR_LIMIT))
        except Exception as exc:  # noqa: BLE001
            block.append(f"### Fundamentals\n_unavailable: {exc}_")
        try:
            news = route_to_vendor("get_news", h_ticker, start_date, end_date)
            block.append("### Recent News")
            block.append(_truncate(news, _NEWS_CHAR_LIMIT))
        except Exception as exc:  # noqa: BLE001
            block.append(f"### Recent News\n_unavailable: {exc}_")
        sections.append("\n\n".join(block))

    return "\n\n---\n\n".join(sections)
