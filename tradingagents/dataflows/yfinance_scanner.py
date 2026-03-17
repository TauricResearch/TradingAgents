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
        # Map category to yfinance screener predefined screener
        screener_keys = {
            "day_gainers": "DAY_GAINERS",
            "day_losers": "DAY_LOSERS", 
            "most_actives": "MOST_ACTIVES"
        }
        
        if category not in screener_keys:
            return f"Invalid category '{category}'. Must be one of: {list(screener_keys.keys())}"
        
        # Use yfinance screener module's screen function
        data = yf.screener.screen(screener_keys[category], count=25)
        
        if not data or not isinstance(data, dict) or 'quotes' not in data:
            return f"No data found for {category}"
        
        quotes = data['quotes']
        
        if not quotes:
            return f"No quotes found for {category}"
        
        # Format the output
        header = f"# Market Movers: {category.replace('_', ' ').title()}\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        
        result_str = header
        result_str += "| Symbol | Name | Price | Change % | Volume | Market Cap |\n"
        result_str += "|--------|------|-------|----------|--------|------------|\n"
        
        for quote in quotes[:15]:  # Top 15
            symbol = quote.get('symbol', 'N/A')
            name = quote.get('shortName', quote.get('longName', 'N/A'))
            price = quote.get('regularMarketPrice', 'N/A')
            change_pct = quote.get('regularMarketChangePercent', 'N/A')
            volume = quote.get('regularMarketVolume', 'N/A')
            market_cap = quote.get('marketCap', 'N/A')
            
            # Format numbers
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
        # Major market indices
        indices = {
            "^GSPC": "S&P 500",
            "^DJI": "Dow Jones",
            "^IXIC": "NASDAQ",
            "^VIX": "VIX (Volatility Index)",
            "^RUT": "Russell 2000"
        }
        
        header = f"# Major Market Indices\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        
        result_str = header
        result_str += "| Index | Current Price | Change | Change % | 52W High | 52W Low |\n"
        result_str += "|-------|---------------|--------|----------|----------|----------|\n"
        
        # Batch-download 1-day history for all symbols in a single request
        symbols = list(indices.keys())
        indices_history = yf.download(symbols, period="2d", auto_adjust=True, progress=False, threads=True)

        for symbol, name in indices.items():
            try:
                ticker = yf.Ticker(symbol)
                # fast_info is a lightweight cached property (no extra HTTP call)
                fast = ticker.fast_info

                # Extract history for this symbol from the batch download
                try:
                    if len(symbols) > 1:
                        closes = indices_history["Close"][symbol].dropna()
                    else:
                        closes = indices_history["Close"].dropna()
                except KeyError:
                    closes = None

                if closes is None or len(closes) == 0:
                    result_str += f"| {name} | N/A | - | - | - | - |\n"
                    continue

                current_price = closes.iloc[-1]
                prev_close = closes.iloc[-2] if len(closes) >= 2 else fast.previous_close
                if prev_close is None or prev_close == 0:
                    prev_close = current_price

                change = current_price - prev_close
                change_pct = (change / prev_close * 100) if prev_close else 0

                high_52w = fast.year_high
                low_52w = fast.year_low

                # Format numbers
                current_str = f"{current_price:.2f}"
                change_str = f"{change:+.2f}"
                change_pct_str = f"{change_pct:+.2f}%"
                high_str = f"{high_52w:.2f}" if isinstance(high_52w, (int, float)) else str(high_52w)
                low_str = f"{low_52w:.2f}" if isinstance(low_52w, (int, float)) else str(low_52w)
                
                result_str += f"| {name} | {current_str} | {change_str} | {change_pct_str} | {high_str} | {low_str} |\n"
                
            except Exception as e:
                result_str += f"| {name} | Error: {str(e)} | - | - | - | - |\n"
        
        return result_str
        
    except Exception as e:
        return f"Error fetching market indices: {str(e)}"


def get_sector_performance_yfinance() -> str:
    """
    Get sector-level performance overview using SPDR sector ETFs.

    yfinance Sector.overview lacks performance data, so we use
    sector ETFs (XLK, XLV, etc.) with yf.download() to compute
    1-day, 1-week, 1-month, and YTD returns.

    Returns:
        Formatted string containing sector performance data
    """
    # Map GICS sectors to SPDR ETF tickers
    sector_etfs = {
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

    try:
        symbols = list(sector_etfs.values())
        # Download ~6 months of data to cover YTD, 1-month, 1-week
        hist = yf.download(symbols, period="6mo", auto_adjust=True, progress=False, threads=True)

        header = f"# Sector Performance Overview\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

        result_str = header
        result_str += "| Sector | 1-Day % | 1-Week % | 1-Month % | YTD % |\n"
        result_str += "|--------|---------|----------|-----------|-------|\n"

        for sector_name, etf in sector_etfs.items():
            try:
                # Extract close prices for this ETF
                if len(symbols) > 1:
                    closes = hist["Close"][etf].dropna()
                else:
                    closes = hist["Close"].dropna()

                if closes.empty or len(closes) < 2:
                    result_str += f"| {sector_name} | N/A | N/A | N/A | N/A |\n"
                    continue

                current = closes.iloc[-1]
                prev = closes.iloc[-2]

                # 1-day
                day_pct = (current - prev) / prev * 100 if prev else 0

                # 1-week (~5 trading days)
                week_pct = _safe_pct(closes, 5)
                # 1-month (~21 trading days)
                month_pct = _safe_pct(closes, 21)
                # YTD: first close of current year vs now
                current_year = closes.index[-1].year
                year_closes = closes[closes.index.year == current_year]
                if len(year_closes) > 0 and year_closes.iloc[0] != 0:
                    ytd_pct = (current - year_closes.iloc[0]) / year_closes.iloc[0] * 100
                else:
                    ytd_pct = None

                day_str = f"{day_pct:+.2f}%"
                week_str = f"{week_pct:+.2f}%" if week_pct is not None else "N/A"
                month_str = f"{month_pct:+.2f}%" if month_pct is not None else "N/A"
                ytd_str = f"{ytd_pct:+.2f}%" if ytd_pct is not None else "N/A"

                result_str += f"| {sector_name} | {day_str} | {week_str} | {month_str} | {ytd_str} |\n"

            except Exception as e:
                result_str += f"| {sector_name} | Error: {str(e)[:30]} | - | - | - |\n"

        return result_str

    except Exception as e:
        return f"Error fetching sector performance: {str(e)}"


def _safe_pct(closes, days_back: int) -> float | None:
    """Compute percentage change from days_back trading days ago."""
    if len(closes) < days_back + 1:
        return None
    base = closes.iloc[-(days_back + 1)]
    current = closes.iloc[-1]
    if base == 0:
        return None
    return (current - base) / base * 100


def get_industry_performance_yfinance(
    sector_key: Annotated[str, "Sector key (e.g., 'technology', 'healthcare')"]
) -> str:
    """
    Get industry-level drill-down within a sector.

    Returns top companies with metadata (rating, market weight) **plus**
    recent price performance (1-day, 1-week, 1-month returns) obtained
    via a single batched ``yf.download()`` call for the top 10 tickers.
    
    Args:
        sector_key: Sector identifier (e.g., 'technology', 'healthcare')
        
    Returns:
        Formatted string containing industry performance data within the sector
    """
    try:
        # Normalize sector key to yfinance format
        sector_key = sector_key.lower().replace(" ", "-")
        
        sector = yf.Sector(sector_key)
        top_companies = sector.top_companies
        
        if top_companies is None or top_companies.empty:
            return f"No industry data found for sector '{sector_key}'"

        # --- Batch-download price history for the top 10 tickers ----------
        tickers = list(top_companies.head(10).index)
        price_returns: dict[str, dict[str, float | None]] = {}
        try:
            hist = yf.download(
                tickers, period="1mo", auto_adjust=True, progress=False, threads=True,
            )
            for tkr in tickers:
                try:
                    if len(tickers) > 1:
                        closes = hist["Close"][tkr].dropna()
                    else:
                        closes = hist["Close"].dropna()
                    if closes.empty or len(closes) < 2:
                        continue
                    price_returns[tkr] = {
                        "1d": _safe_pct(closes, 1),
                        "1w": _safe_pct(closes, 5),
                        "1m": _safe_pct(closes, len(closes) - 1),
                    }
                except Exception:
                    continue
        except Exception:
            pass  # Fall through — table will show N/A for returns
        # ------------------------------------------------------------------

        header = f"# Industry Performance: {sector_key.replace('-', ' ').title()}\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        
        result_str = header
        result_str += "| Company | Symbol | Rating | Market Weight | 1-Day % | 1-Week % | 1-Month % |\n"
        result_str += "|---------|--------|--------|---------------|---------|----------|-----------|\n"
        
        # top_companies has ticker as the DataFrame index (index.name == 'symbol')
        # Columns: name, rating, market weight
        # Display only the tickers we downloaded prices for to avoid N/A gaps
        for symbol, row in top_companies.head(10).iterrows():
            name = row.get('name', 'N/A')
            rating = row.get('rating', 'N/A')
            market_weight = row.get('market weight', None)

            name_short = name[:30] if isinstance(name, str) else str(name)
            weight_str = f"{market_weight:.2%}" if isinstance(market_weight, (int, float)) else "N/A"

            ret = price_returns.get(symbol, {})
            day_str = f"{ret['1d']:+.2f}%" if ret.get('1d') is not None else "N/A"
            week_str = f"{ret['1w']:+.2f}%" if ret.get('1w') is not None else "N/A"
            month_str = f"{ret['1m']:+.2f}%" if ret.get('1m') is not None else "N/A"

            result_str += (
                f"| {name_short} | {symbol} | {rating} | {weight_str}"
                f" | {day_str} | {week_str} | {month_str} |\n"
            )
        
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
            # Handle nested content structure
            if "content" in article:
                content = article["content"]
                title = content.get("title", "No title")
                summary = content.get("summary", "")
                provider = content.get("provider", {})
                publisher = provider.get("displayName", "Unknown")
                
                # Get URL
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
