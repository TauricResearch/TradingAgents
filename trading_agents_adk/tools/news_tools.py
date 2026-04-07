"""News and sentiment tools for News/Social Media analysts.

Plain Python functions that ADK wraps as FunctionTools.
"""

try:
    import yfinance as yf
except ImportError:
    yf = None


def get_news(ticker: str, start_date: str, end_date: str) -> str:
    """Retrieve recent news for a given ticker symbol.

    Args:
        ticker: Ticker symbol of the company
        start_date: Start date in yyyy-mm-dd format
        end_date: End date in yyyy-mm-dd format

    Returns:
        A formatted string containing recent news headlines and summaries.
    """
    if yf is None:
        return f"[Mock] News for {ticker}: 'Company reports strong Q4 earnings', 'New product launch announced'"

    try:
        stock = yf.Ticker(ticker)
        news = stock.news
        if not news:
            return f"No recent news found for {ticker}"

        lines = [f"Recent news for {ticker} ({start_date} to {end_date}):"]
        for item in news[:10]:
            content = item.get("content", {})
            title = content.get("title", "No title")
            summary = content.get("summary", "No summary available")
            provider = content.get("provider", {}).get("displayName", "Unknown")
            lines.append(f"\n  Title: {title}")
            lines.append(f"  Source: {provider}")
            lines.append(f"  Summary: {summary[:200]}")

        return "\n".join(lines)
    except Exception as e:
        return f"Error fetching news for {ticker}: {e}"


def get_global_news(curr_date: str, look_back_days: int = 7, limit: int = 5) -> str:
    """Retrieve global financial/market news.

    Args:
        curr_date: Current date in yyyy-mm-dd format
        look_back_days: Number of days to look back (default 7)
        limit: Maximum number of articles to return (default 5)

    Returns:
        A formatted string containing global market news.
    """
    if yf is None:
        return f"[Mock] Global news as of {curr_date}: 'Fed holds rates steady', 'Tech sector rallies'"

    try:
        spy = yf.Ticker("SPY")
        news = spy.news
        if not news:
            return "No global news found"

        lines = [f"Global market news (as of {curr_date}, last {look_back_days} days):"]
        for item in news[:limit]:
            content = item.get("content", {})
            title = content.get("title", "No title")
            summary = content.get("summary", "No summary")
            lines.append(f"\n  Title: {title}")
            lines.append(f"  Summary: {summary[:200]}")

        return "\n".join(lines)
    except Exception as e:
        return f"Error fetching global news: {e}"
