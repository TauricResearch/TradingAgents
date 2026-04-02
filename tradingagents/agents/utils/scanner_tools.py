"""Scanner tools for market-wide analysis."""

import logging
import os
from time import sleep
from typing import Annotated

from langchain_core.tools import tool

from tradingagents.dataflows.sovereign_cds import get_todays_sovereign_cds_snapshot
from tradingagents.dataflows.interface import route_to_vendor

logger = logging.getLogger(__name__)


def _fetch_finviz_soup(url: str, params: dict, timeout_sec: float):
    from bs4 import BeautifulSoup
    from finvizfinance.util import headers, proxy_dict, session

    response = session.get(
        url,
        params=params,
        headers=headers,
        timeout=timeout_sec,
        proxies=proxy_dict,
    )
    response.raise_for_status()
    return BeautifulSoup(response.text, "lxml")


def _screener_view_with_timeout(
    foverview,
    *,
    timeout_sec: float,
    order: str = "Volume",
    ascend: bool = False,
    limit: int = 50,
    columns=None,
):
    from finvizfinance.constants import order_dict

    if order not in order_dict:
        order_keys = list(order_dict.keys())
        raise ValueError(f"Invalid order '{order}'. Possible order: {order_keys}")

    try:
        foverview.request_params["o"] = ("" if ascend else "-") + order_dict[order]
        foverview._parse_columns(columns)

        soup = _fetch_finviz_soup(foverview.url, foverview.request_params, timeout_sec)
        page = foverview._get_page(soup)
        if page == 0:
            return None

        df = foverview._parse_table(None, soup, limit)
        remaining = limit - foverview.size
        for page_index in range(1, page):
            if remaining <= 0:
                break
            sleep(0)
            foverview.request_params["r"] = page_index * foverview.size + 1
            soup = _fetch_finviz_soup(foverview.url, foverview.request_params, timeout_sec)
            df = foverview._parse_table(df, soup, remaining)
            remaining -= foverview.size
        return df
    finally:
        foverview.reset()


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
def get_todays_sovereign_cds() -> str:
    """
    Get today's sovereign CDS snapshot from World Government Bonds.

    Returns:
        str: Markdown table of major-country 5Y CDS levels, or a skip message
        when the source has not updated for today yet.
    """
    return get_todays_sovereign_cds_snapshot()


@tool
def get_gold_price() -> str:
    """
    Get the latest gold futures price snapshot.

    Returns:
        str: Markdown table containing gold price and daily move.
    """
    return route_to_vendor("get_gold_price")


@tool
def get_oil_prices() -> str:
    """
    Get the latest WTI and Brent crude oil price snapshot.

    Returns:
        str: Markdown table containing oil prices and daily moves.
    """
    return route_to_vendor("get_oil_prices")


@tool
def get_bitcoin_price() -> str:
    """
    Get the latest bitcoin spot price snapshot.

    Returns:
        str: Markdown table containing bitcoin price and daily move.
    """
    return route_to_vendor("get_bitcoin_price")


@tool
def get_eur_usd_rate() -> str:
    """
    Get the latest EUR/USD exchange rate snapshot.

    Returns:
        str: Markdown table containing EUR/USD rate and daily move.
    """
    return route_to_vendor("get_eur_usd_rate")


@tool
def get_jpy_usd_rate() -> str:
    """
    Get the latest JPY/USD exchange rate snapshot.

    Returns:
        str: Markdown table containing JPY/USD rate and daily move.
    """
    return route_to_vendor("get_jpy_usd_rate")


@tool
def get_cny_usd_rate() -> str:
    """
    Get the latest CNY/USD exchange rate (Yuan/USD) snapshot.

    Returns:
        str: Markdown table containing CNY/USD rate and daily move.
    """
    return route_to_vendor("get_cny_usd_rate")


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
    Get gap-up candidates from the gatekeeper universe.
    Primary: Finviz native Gap Up 5% filter (exact, requires finvizfinance).
    Fallback: yfinance OHLC approximation (open-vs-prev-close, less precise
    but always available).

    Returns:
        str: Formatted table of gap candidates with price and volume data
    """
    return route_to_vendor("get_gap_candidates")


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
    timeout_sec = float(os.getenv("TRADINGAGENTS_FINVIZ_TIMEOUT_SEC", "20"))
    try:
        from finvizfinance.screener.overview import Overview  # lazy import

        foverview = Overview()
        foverview.set_filter(filters_dict=filters_dict)
        # We only surface top 5 rows in reports; avoid full-site pagination.
        # finvizfinance defaults to limit=100000 and may crawl dozens of pages.
        df = _screener_view_with_timeout(
            foverview,
            timeout_sec=timeout_sec,
            order="Volume",
            ascend=False,
            limit=50,
        )

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
