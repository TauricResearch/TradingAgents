"""Scanner tools for market-wide analysis."""

import logging
from typing import Annotated

from langchain_core.tools import tool

from tradingagents.dataflows.interface import route_to_vendor

logger = logging.getLogger(__name__)


@tool
def get_market_movers(
    category: Annotated[str, "Category: 'day_gainers', 'day_losers', or 'most_actives'"],
) -> str:
    """
    Get top market movers (gainers, losers, or most active stocks).
    Uses the configured scanner_data vendor.
    
    Args:
        category (str): Category of market movers - 'day_gainers', 'day_losers', or 'most_actives'
        
    Returns:
        str: Formatted table of top market movers with symbol, price, change %, volume, market cap
    """
    return route_to_vendor("get_market_movers", category)


@tool
def get_market_indices() -> str:
    """
    Get major market indices data (S&P 500, Dow Jones, NASDAQ, VIX, Russell 2000).
    Uses the configured scanner_data vendor.
    
    Returns:
        str: Formatted table of index values with current price, daily change, 52W high/low
    """
    return route_to_vendor("get_market_indices")


@tool
def get_gatekeeper_universe() -> str:
    """
    Get the bounded stock universe used for downstream discovery.
    Uses the configured scanner_data vendor and currently relies on yfinance's
    equity screener with the following hardcoded constraints:
    - US-listed stocks
    - market cap >= $2B
    - positive net margin
    - average daily volume > 2M
    - price > $5

    Returns:
        str: Formatted table of gatekeeper-universe candidates
    """
    return route_to_vendor("get_gatekeeper_universe")


@tool
def get_gap_candidates() -> str:
    """
    Get the Finviz gap-up subset of the gatekeeper universe.
    Hardcoded to the exact gatekeeper filter plus Gap Up 5%, so the model
    cannot hallucinate Finviz filter names or options.

    Returns:
        str: Formatted list of Finviz gap candidates
    """
    return _run_finviz_screen(
        {
            "Market Cap.": "+Mid (over $2bln)",
            "Net Profit Margin": "Positive (>0%)",
            "Average Volume": "Over 2M",
            "Price": "Over $5",
            "Gap": "Up 5%",
        },
        label="gatekeeper_gap",
    )


@tool
def get_sector_performance() -> str:
    """
    Get sector-level performance overview for all 11 GICS sectors.
    Uses the configured scanner_data vendor.
    
    Returns:
        str: Formatted table of sector performance with 1-day, 1-week, 1-month, and YTD returns
    """
    return route_to_vendor("get_sector_performance")


@tool
def get_industry_performance(
    sector_key: Annotated[str, "Sector key (e.g., 'technology', 'healthcare', 'financial-services')"],
) -> str:
    """
    Get industry-level drill-down within a specific sector.
    Shows top companies with rating, market weight, and recent price performance
    (1-day, 1-week, 1-month returns).
    Uses the configured scanner_data vendor.
    
    Args:
        sector_key (str): Sector identifier. Must be one of:
            'technology', 'healthcare', 'financial-services', 'energy',
            'consumer-cyclical', 'consumer-defensive', 'industrials',
            'basic-materials', 'real-estate', 'utilities', 'communication-services'
        
    Returns:
        str: Formatted table of top companies/industries in the sector with performance data
    """
    return route_to_vendor("get_industry_performance", sector_key)


@tool
def get_topic_news(
    topic: Annotated[str, "Search topic/query (e.g., 'artificial intelligence', 'semiconductor', 'renewable energy')"],
    limit: Annotated[int, "Maximum number of articles to return"] = 10,
) -> str:
    """
    Search news by arbitrary topic for market-wide analysis.
    Uses the configured scanner_data vendor.

    Args:
        topic (str): Search query/topic for news
        limit (int): Maximum number of articles to return (default 10)

    Returns:
        str: Formatted list of news articles for the topic with title, summary, source, and link
    """
    return route_to_vendor("get_topic_news", topic, limit)


@tool
def get_earnings_calendar(
    from_date: Annotated[str, "Start date in YYYY-MM-DD format"],
    to_date: Annotated[str, "End date in YYYY-MM-DD format"],
) -> str:
    """
    Retrieve upcoming earnings release calendar.
    Shows companies reporting earnings, EPS estimates, and prior-year actuals.
    Unique Finnhub capability not available in Alpha Vantage.
    """
    return route_to_vendor("get_earnings_calendar", from_date, to_date)


@tool
def get_economic_calendar(
    from_date: Annotated[str, "Start date in YYYY-MM-DD format"],
    to_date: Annotated[str, "End date in YYYY-MM-DD format"],
) -> str:
    """
    Retrieve macro economic event calendar (FOMC, CPI, NFP, GDP, PPI).
    Shows market-moving macro events with estimates and prior readings.
    Unique Finnhub capability not available in Alpha Vantage.
    """
    return route_to_vendor("get_economic_calendar", from_date, to_date)


# ---------------------------------------------------------------------------
# Finviz smart-money screener tools
# Each tool has NO parameters — filters are hardcoded to prevent LLM
# hallucinating invalid Finviz filter strings.
# ---------------------------------------------------------------------------


def _run_finviz_screen(filters_dict: dict, label: str) -> str:
    """Shared helper — runs a Finviz Overview screener with hardcoded filters."""
    try:
        from finvizfinance.screener.overview import Overview  # lazy import

        foverview = Overview()
        foverview.set_filter(filters_dict=filters_dict)
        df = foverview.screener_view()

        if df is None or df.empty:
            return f"No stocks matched the {label} criteria today."

        if "Volume" in df.columns:
            df = df.sort_values(by="Volume", ascending=False)

        cols = [c for c in ["Ticker", "Sector", "Price", "Volume"] if c in df.columns]
        top_results = df.head(5)[cols].to_dict("records")

        report = f"Top 5 stocks for {label}:\n"
        for row in top_results:
            report += f"- {row.get('Ticker', 'N/A')} ({row.get('Sector', 'N/A')}) @ ${row.get('Price', 'N/A')}\n"
        return report

    except Exception as e:
        logger.error("Finviz screener error (%s): %s", label, e)
        return f"Smart money scan unavailable (Finviz error): {e}"


@tool
def get_insider_buying_stocks() -> str:
    """
    Finds Mid/Large cap stocks with positive insider purchases and volume > 1M today.
    Insider open-market buys are a strong smart money signal — insiders know their
    company's prospects better than the market.
    """
    return _run_finviz_screen(
        {
            "InsiderTransactions": "Positive (>0%)",
            "Market Cap.": "+Mid (over $2bln)",
            "Current Volume": "Over 1M",
        },
        label="insider_buying",
    )


@tool
def get_unusual_volume_stocks() -> str:
    """
    Finds stocks trading at 2x+ their normal volume today, priced above $10.
    Unusual volume is a footprint of institutional accumulation or distribution.
    """
    return _run_finviz_screen(
        {
            "Relative Volume": "Over 2",
            "Price": "Over $10",
        },
        label="unusual_volume",
    )


@tool
def get_breakout_accumulation_stocks() -> str:
    """
    Finds stocks hitting 52-week highs on 2x+ normal volume, priced above $10.
    This is the classic institutional accumulation-before-breakout pattern
    (O'Neil CAN SLIM). Price strength combined with volume confirms institutional buying.
    """
    return _run_finviz_screen(
        {
            "52-Week High/Low": "New High",
            "Relative Volume": "Over 2",
            "Price": "Over $10",
        },
        label="breakout_accumulation",
    )
