"""yfinance-based news data fetching functions."""

from typing import Optional

import yfinance as yf
from datetime import datetime
from dateutil.relativedelta import relativedelta

from .config import get_config
from .snapshots import GLOBAL_SCOPE, replay_formatted, write_snapshot
from .stockstats_utils import yf_retry


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
        pub_date_str = content.get("pubDate", "")
        pub_date = None
        if pub_date_str:
            try:
                pub_date = datetime.fromisoformat(pub_date_str.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                pass

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
            "pub_date": None,
        }


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
    # T0.3 — replay path. The scope/date pair anchors the cache.  The trade
    # date is end_date because the function is called from analyst nodes
    # whose temporal anchor is "as of end_date".  start_date is in the
    # snapshot params for full reproducibility but does not enter the key.
    cached, hit = replay_formatted(
        kind="news", source="yfinance", scope=ticker, date=end_date,
    )
    if hit:
        return cached

    article_limit = get_config()["news_article_limit"]
    try:
        stock = yf.Ticker(ticker)
        news = yf_retry(lambda: stock.get_news(count=article_limit))

        if not news:
            output = f"No news found for {ticker}"
            write_snapshot(
                kind="news", source="yfinance", scope=ticker, date=end_date,
                params={"ticker": ticker, "start_date": start_date, "end_date": end_date,
                        "article_limit": article_limit},
                raw_response=[],
                formatted_output=output,
            )
            return output

        # Parse date range for filtering
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")

        news_str = ""
        filtered_count = 0

        for article in news:
            data = _extract_article_data(article)

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
            output = f"No news found for {ticker} between {start_date} and {end_date}"
        else:
            output = f"## {ticker} News, from {start_date} to {end_date}:\n\n{news_str}"

        # T0.3 — persist the raw upstream payload alongside the formatted
        # string so a future audit can re-format under different rules
        # without re-fetching, and an immediate replay sees byte-identical
        # context.
        write_snapshot(
            kind="news", source="yfinance", scope=ticker, date=end_date,
            params={"ticker": ticker, "start_date": start_date, "end_date": end_date,
                    "article_limit": article_limit},
            raw_response=news,
            formatted_output=output,
        )
        return output

    except Exception as e:
        # Errors are not snapshotted — re-running an error case must
        # re-attempt the fetch, not replay a stale failure.
        return f"Error fetching news for {ticker}: {str(e)}"


def get_global_news_yfinance(
    curr_date: str,
    look_back_days: Optional[int] = None,
    limit: Optional[int] = None,
) -> str:
    """
    Retrieve global/macro economic news using yfinance Search.

    Args:
        curr_date: Current date in yyyy-mm-dd format
        look_back_days: Number of days to look back. ``None`` falls back to
            ``global_news_lookback_days`` from the active config.
        limit: Maximum number of articles to return. ``None`` falls back to
            ``global_news_article_limit`` from the active config.

    Returns:
        Formatted string containing global news articles
    """
    # T0.3 — replay path for the global-news scope. Global news isn't
    # tied to a ticker, so the cache key uses the reserved GLOBAL_SCOPE
    # constant.
    cached, hit = replay_formatted(
        kind="globalnews", source="yfinance",
        scope=GLOBAL_SCOPE, date=curr_date,
    )
    if hit:
        return cached

    config = get_config()
    if look_back_days is None:
        look_back_days = config["global_news_lookback_days"]
    if limit is None:
        limit = config["global_news_article_limit"]
    search_queries = config["global_news_queries"]

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
            output = f"No global news found for {curr_date}"
            write_snapshot(
                kind="globalnews", source="yfinance",
                scope=GLOBAL_SCOPE, date=curr_date,
                params={"curr_date": curr_date, "look_back_days": look_back_days,
                        "limit": limit, "queries": list(search_queries)},
                raw_response=[],
                formatted_output=output,
            )
            return output

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

        output = f"## Global Market News, from {start_date} to {curr_date}:\n\n{news_str}"
        write_snapshot(
            kind="globalnews", source="yfinance",
            scope=GLOBAL_SCOPE, date=curr_date,
            params={"curr_date": curr_date, "look_back_days": look_back_days,
                    "limit": limit, "queries": list(search_queries)},
            raw_response=all_news[:limit],
            formatted_output=output,
        )
        return output

    except Exception as e:
        return f"Error fetching global news: {str(e)}"
