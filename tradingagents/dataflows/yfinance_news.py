"""yfinance-based news data fetching functions."""

import yfinance as yf
from datetime import datetime
from dateutil.relativedelta import relativedelta


def _extract_article_data(article: dict, max_summary_chars: int = 500) -> dict:
    """Extract article data from yfinance news format (handles nested 'content' structure).
    
    Args:
        article: Raw article dict from yfinance
        max_summary_chars: Maximum characters for summary (default 500). Set to 0 for full text.
    """
    # Handle nested content structure
    if "content" in article:
        content = article["content"]
        title = content.get("title", "No title")
        summary = content.get("summary", "")
        provider = content.get("provider", {})
        publisher = provider.get("displayName", "Unknown")

        # Get URL from canonicalUrl or clickThroughUrl
        url_obj = content.get("canonicalUrl") or content.get("clickThroughUrl") or {}
        link = url_obj.get("url", "")

        # Get publish date
        pub_date_str = content.get("pubDate", "")
        pub_date = None
        if pub_date_str:
            try:
                pub_date = datetime.fromisoformat(pub_date_str.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                pass
    else:
        # Fallback for flat structure
        title = article.get("title", "No title")
        summary = article.get("summary", "")
        publisher = article.get("publisher", "Unknown")
        link = article.get("link", "")
        pub_date = None

    # Truncate summary if limit is set (keep first paragraph or max_chars)
    if max_summary_chars > 0 and summary and len(summary) > max_summary_chars:
        # Try to cut at first paragraph break
        first_para = summary.split('\n\n')[0]
        if len(first_para) <= max_summary_chars:
            summary = first_para
        else:
            summary = summary[:max_summary_chars].rsplit(' ', 1)[0] + "..."

    return {
        "title": title,
        "summary": summary,
        "publisher": publisher,
        "link": link,
        "pub_date": pub_date,
    }


def get_news_yfinance(
    ticker: str,
    start_date: str,
    end_date: str,
    max_summary_chars: int = 500,
) -> str:
    """
    Retrieve news for a specific stock ticker using yfinance.

    Args:
        ticker: Stock ticker symbol (e.g., "AAPL")
        start_date: Start date in yyyy-mm-dd format
        end_date: End date in yyyy-mm-dd format
        max_summary_chars: Maximum characters per article summary (default 500).
                          Set to 0 for full text. Reduces token usage significantly.

    Returns:
        Formatted string containing news articles
    """
    try:
        stock = yf.Ticker(ticker)
        news = stock.get_news(count=20)

        if not news:
            return f"No news found for {ticker}"

        # Parse date range for filtering
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")

        news_str = ""
        filtered_count = 0

        for article in news:
            data = _extract_article_data(article, max_summary_chars=max_summary_chars)

            # Filter by date if publish time is available
            if data["pub_date"]:
                pub_date_naive = data["pub_date"].replace(tzinfo=None)
                if not (start_dt <= pub_date_naive <= end_dt + relativedelta(days=1)):
                    continue

            news_str += f"### {data['title']} (source: {data['publisher']})\n"
            if data["summary"]:
                news_str += f"{data['summary']}\n"
            if data["link"]:
                news_str += f"Link: {data['link']}\n"
            news_str += "\n"
            filtered_count += 1

        if filtered_count == 0:
            return f"No news found for {ticker} between {start_date} and {end_date}"

        return f"## {ticker} News, from {start_date} to {end_date}:\n\n{news_str}"

    except Exception as e:
        return f"Error fetching news for {ticker}: {str(e)}"


def get_global_news_yfinance(
    curr_date: str,
    look_back_days: int = 7,
    limit: int = 10,
    max_summary_chars: int = 500,
) -> str:
    """
    Retrieve global/macro economic news using yfinance Search.

    Args:
        curr_date: Current date in yyyy-mm-dd format
        look_back_days: Number of days to look back
        limit: Maximum number of articles to return
        max_summary_chars: Maximum characters per article summary (default 500).
                          Set to 0 for full text. Reduces token usage significantly.

    Returns:
        Formatted string containing global news articles
    """
    # Search queries for macro/global news
    search_queries = [
        "stock market economy",
        "Federal Reserve interest rates",
        "inflation economic outlook",
        "global markets trading",
    ]

    all_news = []
    seen_titles = set()

    try:
        for query in search_queries:
            search = yf.Search(
                query=query,
                news_count=limit,
                enable_fuzzy_query=True,
            )

            if search.news:
                for article in search.news:
                    # Handle both flat and nested structures
                    if "content" in article:
                        data = _extract_article_data(article, max_summary_chars=max_summary_chars)
                        title = data["title"]
                    else:
                        title = article.get("title", "")

                    # Deduplicate by title
                    if title and title not in seen_titles:
                        seen_titles.add(title)
                        all_news.append(article)

            if len(all_news) >= limit:
                break

        if not all_news:
            return f"No global news found for {curr_date}"

        # Calculate date range
        curr_dt = datetime.strptime(curr_date, "%Y-%m-%d")
        start_dt = curr_dt - relativedelta(days=look_back_days)
        start_date = start_dt.strftime("%Y-%m-%d")

        news_str = ""
        for article in all_news[:limit]:
            # Handle both flat and nested structures
            if "content" in article:
                data = _extract_article_data(article, max_summary_chars=max_summary_chars)
                title = data["title"]
                publisher = data["publisher"]
                link = data["link"]
                summary = data["summary"]
            else:
                title = article.get("title", "No title")
                publisher = article.get("publisher", "Unknown")
                link = article.get("link", "")
                summary = ""
                if max_summary_chars > 0 and summary and len(summary) > max_summary_chars:
                    summary = summary[:max_summary_chars].rsplit(' ', 1)[0] + "..."

            news_str += f"### {title} (source: {publisher})\n"
            if summary:
                news_str += f"{summary}\n"
            if link:
                news_str += f"Link: {link}\n"
            news_str += "\n"

        return f"## Global Market News, from {start_date} to {curr_date}:\n\n{news_str}"

    except Exception as e:
        return f"Error fetching global news: {str(e)}"
