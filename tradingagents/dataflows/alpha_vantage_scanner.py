"""Alpha Vantage-based scanner data fetching for market-wide analysis."""

import json
from datetime import datetime, date
from typing import Annotated

from .alpha_vantage_common import (
    _rate_limited_request,
    AlphaVantageError,
    RateLimitError,
    ThirdPartyParseError,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_CATEGORY_KEY_MAP = {
    "day_gainers": "top_gainers",
    "day_losers": "top_losers",
    "most_actives": "most_actively_traded",
}

# ETF proxies for the 11 GICS sectors
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

# Representative large-cap tickers per sector (normalized keys: lowercase + dashes)
_SECTOR_TICKERS: dict[str, list[str]] = {
    "technology": ["AAPL", "MSFT", "NVDA", "GOOGL", "META", "AVGO", "ADBE", "CRM", "AMD", "INTC"],
    "healthcare": ["UNH", "JNJ", "LLY", "PFE", "ABT", "MRK", "TMO", "ABBV", "DHR", "AMGN"],
    "financials": ["JPM", "BAC", "WFC", "GS", "MS", "BLK", "SCHW", "AXP", "C", "USB"],
    "energy": ["XOM", "CVX", "COP", "SLB", "EOG", "MPC", "PSX", "VLO", "OXY", "HES"],
    "consumer-discretionary": ["AMZN", "TSLA", "HD", "MCD", "NKE", "SBUX", "LOW", "TJX", "BKNG", "CMG"],
    "consumer-staples": ["PG", "KO", "PEP", "COST", "WMT", "PM", "MDLZ", "CL", "KHC", "GIS"],
    "industrials": ["CAT", "HON", "UNP", "UPS", "BA", "RTX", "DE", "LMT", "GE", "MMM"],
    "materials": ["LIN", "APD", "SHW", "ECL", "FCX", "NEM", "NUE", "DOW", "DD", "PPG"],
    "real-estate": ["PLD", "AMT", "CCI", "EQIX", "SPG", "PSA", "O", "WELL", "DLR", "AVB"],
    "utilities": ["NEE", "DUK", "SO", "D", "AEP", "SRE", "EXC", "XEL", "WEC", "ED"],
    "communication-services": ["META", "GOOGL", "NFLX", "DIS", "CMCSA", "T", "VZ", "CHTR", "TMUS", "EA"],
}

_TOPIC_MAP: dict[str, str] = {
    "market": "financial_markets",
    "technology": "technology",
    "tech": "technology",
    "finance": "finance",
    "financial": "finance",
    "earnings": "earnings",
    "ipo": "ipo",
    "mergers": "mergers_and_acquisitions",
    "m&a": "mergers_and_acquisitions",
    "economy": "economy_macro",
    "macro": "economy_macro",
    "energy": "energy_transportation",
    "real estate": "real_estate",
    "realestate": "real_estate",
    "healthcare": "life_sciences",
    "pharma": "life_sciences",
    "manufacturing": "manufacturing",
    "crypto": "blockchain",
    "blockchain": "blockchain",
    "retail": "retail_wholesale",
    "fiscal": "economy_fiscal",
    "monetary": "economy_monetary",
}

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_json(text: str, context: str) -> dict:
    """Parse a JSON string, raising ThirdPartyParseError on failure.

    Args:
        text: Raw response text from the API.
        context: Human-readable label for error messages (e.g. function + symbol).

    Returns:
        Parsed JSON as a dict.

    Raises:
        ThirdPartyParseError: When the text is not valid JSON.
    """
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ThirdPartyParseError(
            f"Failed to parse JSON response for {context}: {exc}"
        ) from exc


def _fetch_global_quote(symbol: str) -> dict:
    """Fetch a single GLOBAL_QUOTE entry for a symbol.

    Args:
        symbol: Ticker symbol (e.g. "SPY").

    Returns:
        The inner "Global Quote" dict from the API response.

    Raises:
        AlphaVantageError: On API-level errors.
        ThirdPartyParseError: On malformed JSON.
        KeyError: When the expected "Global Quote" key is absent.
    """
    text = _rate_limited_request("GLOBAL_QUOTE", {"symbol": symbol})
    data = _parse_json(text, f"GLOBAL_QUOTE/{symbol}")
    if "Global Quote" not in data:
        raise AlphaVantageError(
            f"GLOBAL_QUOTE response for {symbol} missing 'Global Quote' key. "
            f"Keys present: {list(data.keys())}"
        )
    return data["Global Quote"]


def _fetch_daily_closes(symbol: str) -> list[tuple[date, float]]:
    """Fetch up to 100 days of daily close prices for a symbol.

    Args:
        symbol: Ticker symbol (e.g. "XLK").

    Returns:
        List of (date, close_price) tuples, sorted ascending by date.

    Raises:
        AlphaVantageError: On API-level errors or missing data key.
        ThirdPartyParseError: On malformed JSON.
    """
    text = _rate_limited_request(
        "TIME_SERIES_DAILY",
        {"symbol": symbol, "outputsize": "compact"},
    )
    data = _parse_json(text, f"TIME_SERIES_DAILY/{symbol}")

    ts_key = "Time Series (Daily)"
    if ts_key not in data:
        raise AlphaVantageError(
            f"TIME_SERIES_DAILY response for {symbol} missing '{ts_key}' key. "
            f"Keys present: {list(data.keys())}"
        )

    entries: list[tuple[date, float]] = []
    for date_str, ohlcv in data[ts_key].items():
        try:
            close = float(ohlcv["4. close"])
            day = datetime.strptime(date_str, "%Y-%m-%d").date()
            entries.append((day, close))
        except (KeyError, ValueError):
            # Skip malformed individual entries rather than failing entirely
            continue

    entries.sort(key=lambda x: x[0])  # ascending
    return entries


def _pct_change(closes: list[tuple[date, float]], days_back: int) -> float | None:
    """Compute percentage change from `days_back` trading days ago to today.

    Args:
        closes: Ascending list of (date, close) pairs.
        days_back: How many entries back to use as the base.

    Returns:
        Percentage change as a float, or None when there is insufficient data.
    """
    if len(closes) < days_back + 1:
        return None
    base = closes[-(days_back + 1)][1]
    current = closes[-1][1]
    if base == 0:
        return None
    return (current - base) / base * 100


def _ytd_pct_change(closes: list[tuple[date, float]]) -> float | None:
    """Compute year-to-date percentage change.

    Args:
        closes: Ascending list of (date, close) pairs.

    Returns:
        YTD percentage change, or None when the prior year-end close is not
        available in the provided data.
    """
    if not closes:
        return None

    current_year = closes[-1][0].year
    # Find the last close from the prior calendar year
    prior_year_closes = [c for c in closes if c[0].year < current_year]
    if not prior_year_closes:
        return None

    base = prior_year_closes[-1][1]
    current = closes[-1][1]
    if base == 0:
        return None
    return (current - base) / base * 100


def _fmt_pct(value: float | None) -> str:
    """Format an optional float as a percentage string.

    Args:
        value: The percentage value, or None.

    Returns:
        String like "+1.23%" or "N/A".
    """
    if value is None:
        return "N/A"
    return f"{value:+.2f}%"


def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------------------------
# Public scanner functions
# ---------------------------------------------------------------------------

def get_market_movers_alpha_vantage(
    category: Annotated[str, "Category: 'day_gainers', 'day_losers', or 'most_actives'"],
) -> str:
    """Get market movers using the Alpha Vantage TOP_GAINERS_LOSERS endpoint.

    Args:
        category: One of 'day_gainers', 'day_losers', or 'most_actives'.

    Returns:
        Markdown table of the top 15 movers with Symbol, Price, Change %, Volume.

    Raises:
        ValueError: When an unsupported category is requested.
        AlphaVantageError: On API-level errors.
        ThirdPartyParseError: On malformed JSON.
    """
    if category not in _CATEGORY_KEY_MAP:
        raise ValueError(
            f"Invalid category '{category}'. "
            f"Must be one of: {list(_CATEGORY_KEY_MAP.keys())}"
        )

    text = _rate_limited_request("TOP_GAINERS_LOSERS", {})
    data = _parse_json(text, "TOP_GAINERS_LOSERS")

    response_key = _CATEGORY_KEY_MAP[category]
    if response_key not in data:
        raise AlphaVantageError(
            f"TOP_GAINERS_LOSERS response missing expected key '{response_key}'. "
            f"Keys present: {list(data.keys())}"
        )

    movers: list[dict] = data[response_key]
    # A 200 response with an empty list is a valid (genuinely empty) market state
    # — we report it as-is rather than raising.

    header = (
        f"# Market Movers: {category.replace('_', ' ').title()} (Alpha Vantage)\n"
        f"# Data retrieved on: {_now_str()}\n\n"
    )
    result = header
    result += "| Symbol | Price | Change % | Volume |\n"
    result += "|--------|-------|----------|--------|\n"

    for mover in movers[:15]:
        symbol = mover.get("ticker", "N/A")

        raw_price = mover.get("price", "N/A")
        try:
            price = f"${float(raw_price):.2f}"
        except (ValueError, TypeError):
            price = str(raw_price)

        raw_change = mover.get("change_percentage", "N/A")
        # AV returns values like "3.45%" — normalise to a consistent display
        try:
            change_pct = f"{float(str(raw_change).rstrip('%')):.2f}%"
        except (ValueError, TypeError):
            change_pct = str(raw_change)

        raw_volume = mover.get("volume", "N/A")
        try:
            volume = f"{int(raw_volume):,}"
        except (ValueError, TypeError):
            volume = str(raw_volume)

        result += f"| {symbol} | {price} | {change_pct} | {volume} |\n"

    return result


def get_market_indices_alpha_vantage() -> str:
    """Get major market index levels via ETF proxies and the VIX index.

    Uses GLOBAL_QUOTE for each proxy: SPY (S&P 500), DIA (Dow Jones),
    QQQ (NASDAQ), IWM (Russell 2000), and VIX (CBOE Volatility Index).

    Returns:
        Markdown table with Index, Price, Change, Change %.

    Raises:
        AlphaVantageError: On API-level errors.
        ThirdPartyParseError: On malformed JSON.
    """
    # ETF proxies — keyed by display name
    proxies: list[tuple[str, str]] = [
        ("S&P 500 (SPY)", "SPY"),
        ("Dow Jones (DIA)", "DIA"),
        ("NASDAQ (QQQ)", "QQQ"),
        ("Russell 2000 (IWM)", "IWM"),
    ]

    header = (
        f"# Major Market Indices (Alpha Vantage)\n"
        f"# Data retrieved on: {_now_str()}\n\n"
    )
    result = header
    result += "| Index | Price | Change | Change % |\n"
    result += "|-------|-------|--------|----------|\n"

    for display_name, symbol in proxies:
        try:
            quote = _fetch_global_quote(symbol)
            price = quote.get("05. price", "N/A")
            change = quote.get("09. change", "N/A")
            change_pct = quote.get("10. change percent", "N/A")

            try:
                price = f"${float(price):.2f}"
            except (ValueError, TypeError):
                pass

            try:
                change = f"{float(change):+.2f}"
            except (ValueError, TypeError):
                pass

            # AV returns "change percent" as "1.23%" — keep as-is if it has the sign,
            # otherwise add a + prefix for positive values.
            change_pct = str(change_pct).strip()

            result += f"| {display_name} | {price} | {change} | {change_pct} |\n"

        except (AlphaVantageError, ThirdPartyParseError, RateLimitError) as exc:
            result += f"| {display_name} | Error | - | {exc!s:.40} |\n"

    # VIX — try "VIX" first, fall back to "^VIX"
    vix_symbol = None
    vix_quote: dict | None = None
    for candidate in ("VIX", "^VIX"):
        try:
            vix_quote = _fetch_global_quote(candidate)
            vix_symbol = candidate
            break
        except (AlphaVantageError, ThirdPartyParseError, RateLimitError):
            continue

    if vix_quote is not None:
        price = vix_quote.get("05. price", "N/A")
        change = vix_quote.get("09. change", "N/A")
        change_pct = vix_quote.get("10. change percent", "N/A")
        try:
            price = f"{float(price):.2f}"
        except (ValueError, TypeError):
            pass
        try:
            change = f"{float(change):+.2f}"
        except (ValueError, TypeError):
            pass
        result += f"| VIX ({vix_symbol}) | {price} | {change} | {change_pct} |\n"
    else:
        result += "| VIX | Unavailable | - | - |\n"

    return result


def get_sector_performance_alpha_vantage() -> str:
    """Get daily and multi-period performance for the 11 GICS sectors via SPDR ETFs.

    Makes one GLOBAL_QUOTE call and one TIME_SERIES_DAILY call per ETF (22+ total).
    Uses _rate_limited_request throughout to stay within the 75 calls/min limit.

    Returns:
        Markdown table with Sector, 1-Day %, 1-Week %, 1-Month %, YTD %.

    Raises:
        AlphaVantageError: On API-level errors.
        ThirdPartyParseError: On malformed JSON.
    """
    header = (
        f"# Sector Performance Overview (Alpha Vantage)\n"
        f"# Data retrieved on: {_now_str()}\n\n"
    )
    result = header
    result += "| Sector | 1-Day % | 1-Week % | 1-Month % | YTD % |\n"
    result += "|--------|---------|----------|-----------|-------|\n"

    success_count = 0
    last_error = None

    for sector_name, etf in _SECTOR_ETFS.items():
        try:
            # Daily change from GLOBAL_QUOTE (most recent data)
            quote = _fetch_global_quote(etf)
            raw_day_pct = quote.get("10. change percent", "N/A")
            try:
                # AV returns "1.23%" — strip % and reformat with sign
                day_pct_str = f"{float(str(raw_day_pct).rstrip('%')):+.2f}%"
            except (ValueError, TypeError):
                day_pct_str = str(raw_day_pct)

            # Multi-period returns from daily close series
            closes = _fetch_daily_closes(etf)
            week_pct_str = _fmt_pct(_pct_change(closes, 5))
            month_pct_str = _fmt_pct(_pct_change(closes, 21))
            ytd_pct_str = _fmt_pct(_ytd_pct_change(closes))
            success_count += 1

        except (AlphaVantageError, ThirdPartyParseError, RateLimitError) as exc:
            last_error = exc
            day_pct_str = week_pct_str = month_pct_str = ytd_pct_str = (
                f"Error: {exc!s:.30}"
            )

        result += (
            f"| {sector_name} | {day_pct_str} | {week_pct_str} | "
            f"{month_pct_str} | {ytd_pct_str} |\n"
        )

    # If ALL sectors failed, raise so route_to_vendor can fall back
    if success_count == 0 and last_error is not None:
        raise AlphaVantageError(
            f"All {len(_SECTOR_ETFS)} sector queries failed. Last error: {last_error}"
        )

    return result


def get_industry_performance_alpha_vantage(
    sector_key: Annotated[str, "Sector key (e.g., 'technology', 'healthcare')"],
) -> str:
    """Get price and daily change % for representative tickers in a sector.

    Args:
        sector_key: Sector identifier — case-insensitive, spaces converted to dashes
                    (e.g., 'Technology', 'consumer-discretionary').

    Returns:
        Markdown table with Symbol, Price, Change %, sorted by Change % descending.

    Raises:
        ValueError: When the normalised sector_key is not recognised.
        AlphaVantageError: On API-level errors.
        ThirdPartyParseError: On malformed JSON.
    """
    normalised = sector_key.lower().replace(" ", "-")
    if normalised not in _SECTOR_TICKERS:
        raise ValueError(
            f"Unknown sector '{sector_key}'. "
            f"Valid keys: {list(_SECTOR_TICKERS.keys())}"
        )

    tickers = _SECTOR_TICKERS[normalised]

    rows: list[tuple[str, str, float | None, str]] = []  # (symbol, price_str, raw_change_float, change_str)
    errors: list[str] = []

    for symbol in tickers:
        try:
            quote = _fetch_global_quote(symbol)
            raw_price = quote.get("05. price", "N/A")
            raw_change = quote.get("10. change percent", "N/A")

            try:
                price_str = f"${float(raw_price):.2f}"
            except (ValueError, TypeError):
                price_str = str(raw_price)

            try:
                raw_change_float = float(str(raw_change).rstrip("%"))
                change_str = f"{raw_change_float:+.2f}%"
            except (ValueError, TypeError):
                raw_change_float = None
                change_str = str(raw_change)

            rows.append((symbol, price_str, raw_change_float, change_str))

        except (AlphaVantageError, ThirdPartyParseError, RateLimitError) as exc:
            errors.append(f"{symbol}: {exc!s:.60}")

    # Sort by change % descending; put rows without a numeric value last
    rows.sort(key=lambda r: r[2] if r[2] is not None else float("-inf"), reverse=True)

    sector_title = normalised.replace("-", " ").title()
    header = (
        f"# Industry Performance: {sector_title} (Alpha Vantage)\n"
        f"# Data retrieved on: {_now_str()}\n\n"
    )
    result = header
    result += "| Symbol | Price | Change % |\n"
    result += "|--------|-------|----------|\n"

    for symbol, price_str, _, change_str in rows:
        result += f"| {symbol} | {price_str} | {change_str} |\n"

    # If ALL tickers failed, raise so route_to_vendor can fall back
    if not rows and errors:
        raise AlphaVantageError(
            f"All {len(tickers)} ticker queries failed for sector '{sector_key}'. "
            f"Last error: {errors[-1]}"
        )

    if errors:
        result += "\n**Fetch errors:**\n"
        for err in errors:
            result += f"- {err}\n"

    return result


def get_topic_news_alpha_vantage(
    topic: Annotated[str, "News topic (e.g., 'earnings', 'technology', 'market')"],
    limit: Annotated[int, "Maximum number of articles to return"] = 10,
) -> str:
    """Fetch topic-based news and sentiment via Alpha Vantage NEWS_SENTIMENT.

    Args:
        topic: A topic string. Known topics are mapped to AV topic values;
               unknown topics are passed through as-is.
        limit: Maximum number of articles to return (default 10).

    Returns:
        Markdown list of articles with title, summary, source, link, and
        overall sentiment score.

    Raises:
        AlphaVantageError: On API-level errors.
        ThirdPartyParseError: On malformed JSON.
    """
    av_topic = _TOPIC_MAP.get(topic.lower(), topic)

    params = {
        "topics": av_topic,
        "limit": str(limit),
        "sort": "LATEST",
    }

    text = _rate_limited_request("NEWS_SENTIMENT", params)
    data = _parse_json(text, f"NEWS_SENTIMENT/{topic}")

    if "feed" not in data:
        raise AlphaVantageError(
            f"NEWS_SENTIMENT response missing 'feed' key for topic '{topic}'. "
            f"Keys present: {list(data.keys())}"
        )

    articles: list[dict] = data["feed"]

    header = (
        f"# News for Topic: {topic} (Alpha Vantage)\n"
        f"# Data retrieved on: {_now_str()}\n\n"
    )
    result = header

    if not articles:
        result += "_No articles found for this topic._\n"
        return result

    for article in articles[:limit]:
        title = article.get("title", "No title")
        summary = article.get("summary", "")
        source = article.get("source", "Unknown")
        url = article.get("url", "")
        sentiment_score = article.get("overall_sentiment_score")
        published = article.get("time_published", "")

        # Format publication timestamp: "20240315T130000" → "2024-03-15 13:00"
        if published and len(published) >= 13:
            try:
                dt = datetime.strptime(published[:15], "%Y%m%dT%H%M%S")
                published = dt.strftime("%Y-%m-%d %H:%M")
            except ValueError:
                pass  # keep raw value if unparseable

        sentiment_str = (
            f"{sentiment_score:.4f}" if isinstance(sentiment_score, float) else "N/A"
        )

        result += f"### {title}\n"
        result += f"**Source:** {source}"
        if published:
            result += f" | **Published:** {published}"
        result += f" | **Sentiment:** {sentiment_str}\n"
        if summary:
            result += f"{summary}\n"
        if url:
            result += f"**Link:** {url}\n"
        result += "\n"

    return result
