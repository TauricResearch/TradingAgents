"""yfinance-based scanner data fetching functions for market-wide analysis."""

import yfinance as yf
from datetime import datetime
from typing import Annotated


def get_market_movers_yfinance(
    category: Annotated[str, "Category: 'day_gainers', 'day_losers', or 'most_actives'"]
) -> str:
    """
    Get market movers using yfinance Screener.

    Args:
        category: One of 'day_gainers', 'day_losers', or 'most_actives'

    Returns:
        Formatted string containing top market movers
    """
    try:
        screener_keys = {
            "day_gainers": "day_gainers",
            "day_losers": "day_losers",
            "most_actives": "most_actives"
        }

        if category not in screener_keys:
            return f"Invalid category '{category}'. Must be one of: {list(screener_keys.keys())}"

        screener = yf.Screener()
        data = screener.get_screeners([screener_keys[category]], count=25)

        if not data or screener_keys[category] not in data:
            return f"No data found for {category}"

        movers = data[screener_keys[category]]

        if not movers or 'quotes' not in movers:
            return f"No movers found for {category}"

        quotes = movers['quotes']

        if not quotes:
            return f"No quotes found for {category}"

        header = f"# Market Movers: {category.replace('_', ' ').title()}\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

        result_str = header
        result_str += "| Symbol | Name | Price | Change % | Volume | Market Cap |\n"
        result_str += "|--------|------|-------|----------|--------|------------|\n"

        for quote in quotes[:15]:
            symbol = quote.get('symbol', 'N/A')
            name = quote.get('shortName', quote.get('longName', 'N/A'))
            price = quote.get('regularMarketPrice', 'N/A')
            change_pct = quote.get('regularMarketChangePercent', 'N/A')
            volume = quote.get('regularMarketVolume', 'N/A')
            market_cap = quote.get('marketCap', 'N/A')

            if isinstance(price, (int, float)):
                price = f"${price:.2f}"
            if isinstance(change_pct, (int, float)):
                change_pct = f"{change_pct:.2f}%"
            if isinstance(volume, (int, float)):
                volume = f"{volume:,.0f}"
            if isinstance(market_cap, (int, float)):
                market_cap = f"${market_cap:,.0f}"

            result_str += f"| {symbol} | {name[:30]} | {price} | {change_pct} | {volume} | {market_cap} |\n"

        return result_str

    except Exception as e:
        return f"Error fetching market movers for {category}: {str(e)}"


def get_market_indices_yfinance() -> str:
    """
    Get major market indices data.

    Returns:
        Formatted string containing index values and daily changes
    """
    try:
        indices = {
            "^GSPC": "S&P 500",
            "^DJI": "Dow Jones",
            "^IXIC": "NASDAQ",
            "^VIX": "VIX (Volatility Index)",
            "^RUT": "Russell 2000"
        }

        header = "# Major Market Indices\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

        result_str = header
        result_str += "| Index | Current Price | Change | Change % | 52W High | 52W Low |\n"
        result_str += "|-------|---------------|--------|----------|----------|----------|\n"

        # Batch download historical price data to avoid N+1 calls.
        # yf.download() always returns multi-level columns when multiple symbols
        # are requested (group_by="ticker"), so we access hist_batch[symbol].
        symbols = list(indices.keys())
        hist_batch = yf.download(
            symbols,
            period="2d",
            group_by="ticker",
            progress=False,
            auto_adjust=True,
        )

        for symbol, name in indices.items():
            try:
                ticker = yf.Ticker(symbol)
                info = ticker.info

                # Extract per-symbol slice from the batched result.
                # With multiple symbols and group_by="ticker", the columns are
                # a MultiIndex keyed by symbol.
                try:
                    hist = hist_batch[symbol].dropna()
                except KeyError:
                    hist = ticker.history(period="1d")

                if hist.empty:
                    result_str += f"| {name} | No data | - | - | - | - |\n"
                    continue

                current_price = hist['Close'].iloc[-1]
                prev_close = info.get('previousClose', current_price)
                change = current_price - prev_close
                change_pct = (change / prev_close * 100) if prev_close else 0

                high_52w = info.get('fiftyTwoWeekHigh', 'N/A')
                low_52w = info.get('fiftyTwoWeekLow', 'N/A')

                current_str = f"{current_price:.2f}"
                change_str = f"{change:+.2f}"
                change_pct_str = f"{change_pct:+.2f}%"
                high_str = f"{high_52w:.2f}" if isinstance(high_52w, (int, float)) else str(high_52w)
                low_str = f"{low_52w:.2f}" if isinstance(low_52w, (int, float)) else str(low_52w)

                result_str += f"| {name} | {current_str} | {change_str} | {change_pct_str} | {high_str} | {low_str} |\n"

            except Exception as e:
                result_str += f"| {name} | Error: {str(e)[:40]} | - | - | - | - |\n"

        return result_str

    except Exception as e:
        return f"Error fetching market indices: {str(e)}"


def get_sector_performance_yfinance() -> str:
    """
    Get sector-level performance overview using yfinance Sector data.

    Returns:
        Formatted string containing sector performance data
    """
    try:
        sector_keys = [
            "communication-services",
            "consumer-cyclical",
            "consumer-defensive",
            "energy",
            "financial-services",
            "healthcare",
            "industrials",
            "basic-materials",
            "real-estate",
            "technology",
            "utilities"
        ]

        header = "# Sector Performance Overview\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

        result_str = header
        result_str += "| Sector | 1-Day % | 1-Week % | 1-Month % | YTD % |\n"
        result_str += "|--------|---------|----------|-----------|-------|\n"

        for sector_key in sector_keys:
            try:
                sector = yf.Sector(sector_key)
                overview = sector.overview

                if overview is None or overview.empty:
                    continue

                sector_name = sector_key.replace("-", " ").title()
                day_return = overview.get('oneDay', {}).get('percentChange', 'N/A')
                week_return = overview.get('oneWeek', {}).get('percentChange', 'N/A')
                month_return = overview.get('oneMonth', {}).get('percentChange', 'N/A')
                ytd_return = overview.get('ytd', {}).get('percentChange', 'N/A')

                day_str = f"{day_return:.2f}%" if isinstance(day_return, (int, float)) else str(day_return)
                week_str = f"{week_return:.2f}%" if isinstance(week_return, (int, float)) else str(week_return)
                month_str = f"{month_return:.2f}%" if isinstance(month_return, (int, float)) else str(month_return)
                ytd_str = f"{ytd_return:.2f}%" if isinstance(ytd_return, (int, float)) else str(ytd_return)

                result_str += f"| {sector_name} | {day_str} | {week_str} | {month_str} | {ytd_str} |\n"

            except Exception as e:
                result_str += f"| {sector_key.replace('-', ' ').title()} | Error: {str(e)[:20]} | - | - | - |\n"

        return result_str

    except Exception as e:
        return f"Error fetching sector performance: {str(e)}"


def get_industry_performance_yfinance(
    sector_key: Annotated[str, "Sector key (e.g., 'technology', 'healthcare')"]
) -> str:
    """
    Get industry-level drill-down within a sector.

    Args:
        sector_key: Sector identifier (e.g., 'technology', 'healthcare')

    Returns:
        Formatted string containing industry performance data within the sector
    """
    try:
        sector_key = sector_key.lower().replace(" ", "-")

        sector = yf.Sector(sector_key)
        top_companies = sector.top_companies

        if top_companies is None or top_companies.empty:
            return f"No industry data found for sector '{sector_key}'"

        header = f"# Industry Performance: {sector_key.replace('-', ' ').title()}\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

        result_str = header
        result_str += "| Company | Symbol | Industry | Market Cap | Change % |\n"
        result_str += "|---------|--------|----------|------------|----------|\n"

        for idx, row in top_companies.head(20).iterrows():
            symbol = row.get('symbol', 'N/A')
            name = row.get('name', 'N/A')
            industry = row.get('industry', 'N/A')
            market_cap = row.get('marketCap', 'N/A')
            change_pct = row.get('regularMarketChangePercent', 'N/A')

            if isinstance(market_cap, (int, float)):
                market_cap = f"${market_cap:,.0f}"
            if isinstance(change_pct, (int, float)):
                change_pct = f"{change_pct:.2f}%"

            name_short = name[:30] if isinstance(name, str) else name
            industry_short = industry[:25] if isinstance(industry, str) else industry

            result_str += f"| {name_short} | {symbol} | {industry_short} | {market_cap} | {change_pct} |\n"

        return result_str

    except Exception as e:
        return f"Error fetching industry performance for sector '{sector_key}': {str(e)}"


def get_topic_news_yfinance(
    topic: Annotated[str, "Search topic/query (e.g., 'artificial intelligence', 'semiconductor')"],
    limit: Annotated[int, "Maximum number of articles to return"] = 10
) -> str:
    """
    Search news by arbitrary topic using yfinance Search.

    Args:
        topic: Search query/topic
        limit: Maximum number of articles to return

    Returns:
        Formatted string containing news articles for the topic
    """
    try:
        search = yf.Search(
            query=topic,
            news_count=limit,
            enable_fuzzy_query=True,
        )

        if not search.news:
            return f"No news found for topic '{topic}'"

        header = f"# News for Topic: {topic}\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

        result_str = header

        for article in search.news[:limit]:
            if "content" in article:
                content = article["content"]
                title = content.get("title", "No title")
                summary = content.get("summary", "")
                provider = content.get("provider", {})
                publisher = provider.get("displayName", "Unknown")

                url_obj = content.get("canonicalUrl") or content.get("clickThroughUrl") or {}
                link = url_obj.get("url", "")
            else:
                title = article.get("title", "No title")
                summary = article.get("summary", "")
                publisher = article.get("publisher", "Unknown")
                link = article.get("link", "")

            result_str += f"### {title} (source: {publisher})\n"
            if summary:
                result_str += f"{summary}\n"
            if link:
                result_str += f"Link: {link}\n"
            result_str += "\n"

        return result_str

    except Exception as e:
        return f"Error fetching news for topic '{topic}': {str(e)}"

