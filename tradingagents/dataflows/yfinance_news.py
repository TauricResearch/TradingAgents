"""yfinance-based news data fetching functions."""

from datetime import datetime, timezone

from dateutil.relativedelta import relativedelta
import yfinance as yf

from .stockstats_utils import yf_retry


_TICKER_NEWS_FETCH_COUNTS = (20, 50, 100)
_MAX_FILTERED_TICKER_ARTICLES = 25


def _parse_pub_date(raw_value) -> datetime | None:
    """Normalize yfinance pub date values into a timezone-aware datetime."""
    if raw_value in (None, ""):
        return None

    if isinstance(raw_value, datetime):
        return raw_value

    if isinstance(raw_value, (int, float)):
        try:
            return datetime.fromtimestamp(raw_value, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None

    if isinstance(raw_value, str):
        normalized = raw_value.strip()
        if not normalized:
            return None
        try:
            return datetime.fromisoformat(normalized.replace("Z", "+00:00"))
        except ValueError:
            try:
                return datetime.fromtimestamp(float(normalized), tz=timezone.utc)
            except (OverflowError, OSError, ValueError):
                return None

    return None


def _extract_article_data(article: dict) -> dict:
    """Extract article data from yfinance news format (handles nested 'content' structure)."""
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
        pub_date = _parse_pub_date(content.get("pubDate", ""))

        return {
            "title": title,
            "summary": summary,
            "publisher": publisher,
            "link": link,
            "pub_date": pub_date,
        }
    else:
        # Fallback for flat structure
        return {
            "title": article.get("title", "No title"),
            "summary": article.get("summary", ""),
            "publisher": article.get("publisher", "Unknown"),
            "link": article.get("link", ""),
            "pub_date": _parse_pub_date(article.get("providerPublishTime")),
        }


def _article_identity(article: dict) -> str:
    """Return a stable identity key for deduplicating news articles."""
    link = article.get("link", "").strip()
    if link:
        return link

    title = article.get("title", "").strip()
    publisher = article.get("publisher", "").strip()
    pub_date = article.get("pub_date")
    stamp = pub_date.isoformat() if isinstance(pub_date, datetime) else ""
    return f"{publisher}::{title}::{stamp}"


def _collect_ticker_news(
    ticker: str,
    start_dt: datetime,
) -> tuple[list[dict], datetime | None, datetime | None]:
    """Fetch increasingly larger ticker feeds until the requested window is covered."""
    collected: list[dict] = []
    seen: set[str] = set()
    oldest_pub_date = None
    newest_pub_date = None

    for count in _TICKER_NEWS_FETCH_COUNTS:
        news = yf_retry(lambda batch_size=count: yf.Ticker(ticker).get_news(count=batch_size))
        if not news:
            continue

        for article in news:
            data = _extract_article_data(article)
            identity = _article_identity(data)
            if identity in seen:
                continue
            seen.add(identity)
            collected.append(data)

            pub_date = data.get("pub_date")
            if pub_date:
                if newest_pub_date is None or pub_date > newest_pub_date:
                    newest_pub_date = pub_date
                if oldest_pub_date is None or pub_date < oldest_pub_date:
                    oldest_pub_date = pub_date

        if oldest_pub_date and oldest_pub_date.replace(tzinfo=None) <= start_dt:
            break
        if len(news) < count:
            break

    collected.sort(
        key=lambda article: article["pub_date"].timestamp() if article.get("pub_date") else float("-inf"),
        reverse=True,
    )
    return collected, oldest_pub_date, newest_pub_date


def _format_coverage_note(oldest_pub_date: datetime | None, newest_pub_date: datetime | None) -> str:
    """Describe the yfinance coverage window when no article matches the requested range."""
    if oldest_pub_date and newest_pub_date:
        return (
            "; the current yfinance ticker feed only covered "
            f"{oldest_pub_date.strftime('%Y-%m-%d')} to {newest_pub_date.strftime('%Y-%m-%d')} at query time"
        )
    if oldest_pub_date:
        return f"; the current yfinance ticker feed only reached back to {oldest_pub_date.strftime('%Y-%m-%d')}"
    if newest_pub_date:
        return f"; the current yfinance ticker feed only returned articles up to {newest_pub_date.strftime('%Y-%m-%d')}"
    return ""


def get_news_yfinance(
    ticker: str,
    start_date: str,
    end_date: str,
) -> str:
    """
    Retrieve news for a specific stock ticker using yfinance.

    Args:
        ticker: Stock ticker symbol (e.g., "AAPL")
        start_date: Start date in yyyy-mm-dd format
        end_date: End date in yyyy-mm-dd format

    Returns:
        Formatted string containing news articles
    """
    try:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        articles, oldest_pub_date, newest_pub_date = _collect_ticker_news(ticker, start_dt)

        if not articles:
            return f"No news found for {ticker}"

        news_str = ""
        filtered_count = 0

        for data in articles:
            # Filter by date if publish time is available
            if data["pub_date"]:
                pub_date_naive = data["pub_date"].replace(tzinfo=None)
                if not (start_dt <= pub_date_naive <= end_dt + relativedelta(days=1)):
                    continue

            date_prefix = ""
            if data["pub_date"]:
                date_prefix = f"[{data['pub_date'].strftime('%Y-%m-%d')}] "

            news_str += f"### {date_prefix}{data['title']} (source: {data['publisher']})\n"
            if data["summary"]:
                news_str += f"{data['summary']}\n"
            if data["link"]:
                news_str += f"Link: {data['link']}\n"
            news_str += "\n"
            filtered_count += 1
            if filtered_count >= _MAX_FILTERED_TICKER_ARTICLES:
                break

        if filtered_count == 0:
            coverage_note = _format_coverage_note(oldest_pub_date, newest_pub_date)
            return f"No news found for {ticker} between {start_date} and {end_date}{coverage_note}"

        return f"## {ticker} News, from {start_date} to {end_date}:\n\n{news_str}"

    except Exception as e:
        return f"Error fetching news for {ticker}: {str(e)}"


def get_global_news_yfinance(
    curr_date: str,
    look_back_days: int = 7,
    limit: int = 10,
) -> str:
    """
    Retrieve global/macro economic news using yfinance Search.

    Args:
        curr_date: Current date in yyyy-mm-dd format
        look_back_days: Number of days to look back
        limit: Maximum number of articles to return

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
            search = yf_retry(lambda q=query: yf.Search(
                query=q,
                news_count=limit,
                enable_fuzzy_query=True,
            ))

            if search.news:
                for article in search.news:
                    # Handle both flat and nested structures
                    if "content" in article:
                        data = _extract_article_data(article)
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
                data = _extract_article_data(article)
                # Skip articles published after curr_date (look-ahead guard)
                if data.get("pub_date"):
                    pub_naive = data["pub_date"].replace(tzinfo=None) if hasattr(data["pub_date"], "replace") else data["pub_date"]
                    if pub_naive > curr_dt + relativedelta(days=1):
                        continue
                title = data["title"]
                publisher = data["publisher"]
                link = data["link"]
                summary = data["summary"]
            else:
                title = article.get("title", "No title")
                publisher = article.get("publisher", "Unknown")
                link = article.get("link", "")
                summary = ""

            news_str += f"### {title} (source: {publisher})\n"
            if summary:
                news_str += f"{summary}\n"
            if link:
                news_str += f"Link: {link}\n"
            news_str += "\n"

        return f"## Global Market News, from {start_date} to {curr_date}:\n\n{news_str}"

    except Exception as e:
        return f"Error fetching global news: {str(e)}"
