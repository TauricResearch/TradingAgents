"""Finnhub-based scanner data for market-wide analysis.

Provides market movers, index levels, sector performance, and topic news
using the Finnhub REST API.  The public function names match the Alpha Vantage
scanner equivalents (with ``_finnhub`` suffix) so they slot cleanly into the
vendor routing layer in ``interface.py``.

Notes on Finnhub free-tier limitations:
- There is no dedicated TOP_GAINERS / TOP_LOSERS endpoint on the free tier.
  ``get_market_movers_finnhub`` fetches quotes for a curated basket of large-cap
  S&P 500 stocks and sorts by daily change percentage.
- The /news endpoint maps topic strings to the four available Finnhub categories
  (general, forex, crypto, merger).
"""

from datetime import datetime
from typing import Annotated

from .finnhub_common import (
    FinnhubError,
    RateLimitError,
    ThirdPartyError,
    ThirdPartyParseError,
    ThirdPartyTimeoutError,
    _make_api_request,
    _now_str,
    _rate_limited_request,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Representative S&P 500 large-caps used as the movers basket.
# Sorted roughly by market-cap weight — first 50 cover the bulk of the index.
_SP500_SAMPLE: list[str] = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "BRK.B", "UNH", "LLY",
    "JPM", "XOM", "V", "AVGO", "PG", "MA", "JNJ", "HD", "MRK", "ABBV",
    "CVX", "COST", "CRM", "AMD", "NFLX", "WMT", "BAC", "KO", "PEP", "ADBE",
    "TMO", "ACN", "MCD", "CSCO", "ABT", "GE", "DHR", "TXN", "NKE", "PFE",
    "NEE", "WFC", "ORCL", "COP", "CAT", "DIS", "MS", "LIN", "BMY", "HON",
]

# SPDR ETFs used as sector proxies (11 GICS sectors)
_SECTOR_ETFS: dict[str, str] = {
    "Technology": "XLK",
    "Healthcare": "XLV",
    "Financials": "XLF",
    "Energy": "XLE",
    "Consumer Discretionary": "XLY",
    "Consumer Staples": "XLP",
    "Industrials": "XLI",
    "Materials": "XLB",
    "Real Estate": "XLRE",
    "Utilities": "XLU",
    "Communication Services": "XLC",
}

# Index ETF proxies
_INDEX_PROXIES: list[tuple[str, str]] = [
    ("S&P 500 (SPY)", "SPY"),
    ("Dow Jones (DIA)", "DIA"),
    ("NASDAQ (QQQ)", "QQQ"),
    ("Russell 2000 (IWM)", "IWM"),
    ("VIX (^VIX)", "^VIX"),
]

# Mapping from human topic strings → Finnhub /news category
_TOPIC_TO_CATEGORY: dict[str, str] = {
    "market": "general",
    "general": "general",
    "economy": "general",
    "macro": "general",
    "technology": "general",
    "tech": "general",
    "finance": "general",
    "financial": "general",
    "earnings": "general",
    "ipo": "general",
    "mergers": "merger",
    "m&a": "merger",
    "merger": "merger",
    "acquisition": "merger",
    "forex": "forex",
    "fx": "forex",
    "currency": "forex",
    "crypto": "crypto",
    "cryptocurrency": "crypto",
    "blockchain": "crypto",
    "bitcoin": "crypto",
    "ethereum": "crypto",
}

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _fetch_quote(symbol: str) -> dict:
    """Fetch a single Finnhub quote for a symbol using the rate limiter.

    Args:
        symbol: Ticker symbol.

    Returns:
        Normalised quote dict with keys: symbol, current_price, change,
        change_percent, high, low, open, prev_close.

    Raises:
        FinnhubError: On API or parse errors.
    """
    data = _rate_limited_request("quote", {"symbol": symbol})

    current_price: float = data.get("c", 0.0)
    prev_close: float = data.get("pc", 0.0)
    change: float = data.get("d") or 0.0
    change_pct: float = data.get("dp") or 0.0

    return {
        "symbol": symbol,
        "current_price": current_price,
        "change": change,
        "change_percent": change_pct,
        "high": data.get("h", 0.0),
        "low": data.get("l", 0.0),
        "open": data.get("o", 0.0),
        "prev_close": prev_close,
    }


# ---------------------------------------------------------------------------
# Public scanner functions
# ---------------------------------------------------------------------------


def get_market_movers_finnhub(
    category: Annotated[str, "Category: 'gainers', 'losers', or 'active'"],
) -> str:
    """Get market movers by fetching quotes for a basket of large-cap S&P 500 stocks.

    Finnhub's free tier does not expose a TOP_GAINERS_LOSERS endpoint.  This
    function fetches /quote for a pre-defined sample of 50 large-cap tickers
    and sorts by daily change percentage to approximate gainer/loser lists.

    The 'active' category uses absolute change percentage (highest volatility).

    Args:
        category: One of ``'gainers'``, ``'losers'``, or ``'active'``.

    Returns:
        Markdown table with Symbol, Price, Change, Change %, ranked by category.

    Raises:
        ValueError: When an unsupported category is requested.
        FinnhubError: When all quote fetches fail.
    """
    valid_categories = {"gainers", "losers", "active"}
    if category not in valid_categories:
        raise ValueError(
            f"Invalid category '{category}'. Must be one of: {sorted(valid_categories)}"
        )

    rows: list[dict] = []
    errors: list[str] = []

    for symbol in _SP500_SAMPLE:
        try:
            quote = _fetch_quote(symbol)
            # Skip symbols where the market is closed / data unavailable
            if quote["current_price"] == 0 and quote["prev_close"] == 0:
                continue
            rows.append(quote)
        except (FinnhubError, RateLimitError, ThirdPartyError,
                ThirdPartyTimeoutError, ThirdPartyParseError) as exc:
            errors.append(f"{symbol}: {exc!s:.60}")

    if not rows:
        raise FinnhubError(
            f"All {len(_SP500_SAMPLE)} quote fetches failed for market movers. "
            f"Sample error: {errors[0] if errors else 'unknown'}"
        )

    # Sort according to category
    if category == "gainers":
        rows.sort(key=lambda r: r["change_percent"], reverse=True)
        label = "Top Gainers"
    elif category == "losers":
        rows.sort(key=lambda r: r["change_percent"])
        label = "Top Losers"
    else:  # active — sort by absolute change %
        rows.sort(key=lambda r: abs(r["change_percent"]), reverse=True)
        label = "Most Active (by Change %)"

    header = (
        f"# Market Movers: {label} (Finnhub — S&P 500 Sample)\n"
        f"# Data retrieved on: {_now_str()}\n\n"
    )
    result = header
    result += "| Symbol | Price | Change | Change % |\n"
    result += "|--------|-------|--------|----------|\n"

    for row in rows[:15]:
        symbol = row["symbol"]
        price_str = f"${row['current_price']:.2f}"
        change_str = f"{row['change']:+.2f}"
        change_pct_str = f"{row['change_percent']:+.2f}%"
        result += f"| {symbol} | {price_str} | {change_str} | {change_pct_str} |\n"

    if errors:
        result += f"\n_Note: {len(errors)} symbols failed to fetch._\n"

    return result


def get_market_indices_finnhub() -> str:
    """Get major market index levels via Finnhub /quote for ETF proxies and VIX.

    Fetches quotes for: SPY (S&P 500), DIA (Dow Jones), QQQ (NASDAQ),
    IWM (Russell 2000), and ^VIX (Volatility Index).

    Returns:
        Markdown table with Index, Price, Change, Change %.

    Raises:
        FinnhubError: When all index fetches fail.
    """
    header = (
        f"# Major Market Indices (Finnhub)\n"
        f"# Data retrieved on: {_now_str()}\n\n"
    )
    result = header
    result += "| Index | Price | Change | Change % |\n"
    result += "|-------|-------|--------|----------|\n"

    success_count = 0

    for display_name, symbol in _INDEX_PROXIES:
        try:
            quote = _fetch_quote(symbol)
            price = quote["current_price"]
            change = quote["change"]
            change_pct = quote["change_percent"]

            # VIX has no dollar sign
            is_vix = "VIX" in display_name
            price_str = f"{price:.2f}" if is_vix else f"${price:.2f}"
            change_str = f"{change:+.2f}"
            change_pct_str = f"{change_pct:+.2f}%"

            result += f"| {display_name} | {price_str} | {change_str} | {change_pct_str} |\n"
            success_count += 1

        except (FinnhubError, RateLimitError, ThirdPartyError,
                ThirdPartyTimeoutError, ThirdPartyParseError) as exc:
            result += f"| {display_name} | Error | - | {exc!s:.40} |\n"

    if success_count == 0:
        raise FinnhubError("All market index fetches failed.")

    return result


def get_sector_performance_finnhub() -> str:
    """Get daily change % for the 11 GICS sectors via SPDR ETF quotes.

    Fetches one /quote call per SPDR ETF (XLK, XLV, XLF, XLE, XLI, XLY,
    XLP, XLRE, XLU, XLB, XLC) and presents daily performance.

    Returns:
        Markdown table with Sector, ETF, Price, Day Change %.

    Raises:
        FinnhubError: When all sector fetches fail.
    """
    header = (
        f"# Sector Performance (Finnhub — SPDR ETF Proxies)\n"
        f"# Data retrieved on: {_now_str()}\n\n"
    )
    result = header
    result += "| Sector | ETF | Price | Day Change % |\n"
    result += "|--------|-----|-------|---------------|\n"

    success_count = 0
    last_error: Exception | None = None

    for sector_name, etf in _SECTOR_ETFS.items():
        try:
            quote = _fetch_quote(etf)
            price_str = f"${quote['current_price']:.2f}"
            change_pct_str = f"{quote['change_percent']:+.2f}%"
            result += f"| {sector_name} | {etf} | {price_str} | {change_pct_str} |\n"
            success_count += 1

        except (FinnhubError, RateLimitError, ThirdPartyError,
                ThirdPartyTimeoutError, ThirdPartyParseError) as exc:
            last_error = exc
            result += f"| {sector_name} | {etf} | Error | {exc!s:.30} |\n"

    # If ALL sectors failed, raise so route_to_vendor can fall back
    if success_count == 0 and last_error is not None:
        raise FinnhubError(
            f"All {len(_SECTOR_ETFS)} sector queries failed. Last error: {last_error}"
        )

    return result


def get_topic_news_finnhub(
    topic: Annotated[str, "News topic (e.g., 'market', 'crypto', 'mergers')"],
    limit: Annotated[int, "Maximum number of articles to return"] = 20,
) -> str:
    """Fetch topic-based market news via Finnhub /news.

    Maps the ``topic`` string to one of the four Finnhub news categories
    (general, forex, crypto, merger) and returns a formatted markdown list of
    recent articles.

    Args:
        topic: A topic string. Known topics are mapped to Finnhub categories;
               unknown topics default to ``'general'``.
        limit: Maximum number of articles to return (default 20).

    Returns:
        Markdown-formatted news feed.

    Raises:
        FinnhubError: On API-level errors.
    """
    finnhub_category = _TOPIC_TO_CATEGORY.get(topic.lower(), "general")

    articles: list[dict] = _rate_limited_request("news", {"category": finnhub_category})

    header = (
        f"# News for Topic: {topic} (Finnhub — category: {finnhub_category})\n"
        f"# Data retrieved on: {_now_str()}\n\n"
    )
    result = header

    if not articles:
        result += f"_No articles found for topic '{topic}'._\n"
        return result

    for article in articles[:limit]:
        headline = article.get("headline", "No headline")
        source = article.get("source", "Unknown")
        summary = article.get("summary", "")
        url = article.get("url", "")
        datetime_unix: int = article.get("datetime", 0)

        # Format publish timestamp
        if datetime_unix:
            try:
                published = datetime.fromtimestamp(int(datetime_unix)).strftime("%Y-%m-%d %H:%M")
            except (OSError, OverflowError, ValueError):
                published = str(datetime_unix)
        else:
            published = ""

        result += f"### {headline}\n"
        meta = f"**Source:** {source}"
        if published:
            meta += f" | **Published:** {published}"
        result += meta + "\n"
        if summary:
            result += f"{summary}\n"
        if url:
            result += f"**Link:** {url}\n"
        result += "\n"

    return result


def get_earnings_calendar_finnhub(from_date: str, to_date: str) -> str:
    """Fetch upcoming earnings releases via Finnhub /calendar/earnings.

    Returns a formatted markdown table of companies reporting earnings between
    from_date and to_date, including EPS estimates and prior-year actuals.
    Unique capability not available in Alpha Vantage at any tier.

    Args:
        from_date: Start date in YYYY-MM-DD format.
        to_date: End date in YYYY-MM-DD format.

    Returns:
        Markdown-formatted table with Symbol, Date, EPS Estimate, EPS Prior.

    Raises:
        FinnhubError: On API-level errors or empty response.
    """
    data = _rate_limited_request("calendar/earnings", {"from": from_date, "to": to_date})
    earnings_list = data.get("earningsCalendar", [])
    header = (
        f"# Earnings Calendar: {from_date} to {to_date} — Finnhub\n"
        f"# Data retrieved on: {_now_str()}\n\n"
    )
    if not earnings_list:
        return header + "_No earnings events found in this date range._\n"

    lines = [
        header,
        "| Symbol | Company | Date | EPS Estimate | EPS Prior | Revenue Estimate |",
        "|--------|---------|------|--------------|-----------|-----------------|",
    ]
    for item in sorted(earnings_list, key=lambda x: x.get("date", "")):
        symbol = item.get("symbol", "N/A")
        company = item.get("company", "N/A")[:30]
        date = item.get("date", "N/A")
        eps_est = item.get("epsEstimate", None)
        eps_prior = item.get("epsPrior", None)
        rev_est = item.get("revenueEstimate", None)
        eps_est_s = f"${eps_est:.2f}" if eps_est is not None else "N/A"
        eps_prior_s = f"${eps_prior:.2f}" if eps_prior is not None else "N/A"
        rev_est_s = f"${float(rev_est)/1e9:.2f}B" if rev_est is not None else "N/A"
        lines.append(f"| {symbol} | {company} | {date} | {eps_est_s} | {eps_prior_s} | {rev_est_s} |")
    return "\n".join(lines)


def get_economic_calendar_finnhub(from_date: str, to_date: str) -> str:
    """Fetch macro economic events via Finnhub /calendar/economic.

    Returns FOMC meetings, CPI releases, NFP (Non-Farm Payroll), PPI,
    GDP announcements, and other market-moving macro events. Unique
    capability not available in Alpha Vantage at any tier.

    Args:
        from_date: Start date in YYYY-MM-DD format.
        to_date: End date in YYYY-MM-DD format.

    Returns:
        Markdown-formatted table with Date, Event, Country, Impact, Estimate, Prior.

    Raises:
        FinnhubError: On API-level errors or empty response.
    """
    data = _rate_limited_request("calendar/economic", {"from": from_date, "to": to_date})
    events = data.get("economicCalendar", [])
    header = (
        f"# Economic Calendar: {from_date} to {to_date} — Finnhub\n"
        f"# Data retrieved on: {_now_str()}\n\n"
    )
    if not events:
        return header + "_No economic events found in this date range._\n"

    lines = [
        header,
        "| Date | Time | Event | Country | Impact | Estimate | Prior |",
        "|------|------|-------|---------|--------|----------|-------|",
    ]
    for ev in sorted(events, key=lambda x: (x.get("time", ""), x.get("event", ""))):
        date = ev.get("time", "N/A")[:10] if ev.get("time") else "N/A"
        time_str = (
            ev.get("time", "N/A")[11:16]
            if ev.get("time") and len(ev.get("time", "")) > 10
            else "N/A"
        )
        event = ev.get("event", "N/A")[:40]
        country = ev.get("country", "N/A")
        impact = ev.get("impact", "N/A")
        estimate = str(ev.get("estimate", "N/A"))
        prior = str(ev.get("prev", "N/A"))
        lines.append(f"| {date} | {time_str} | {event} | {country} | {impact} | {estimate} | {prior} |")
    return "\n".join(lines)
