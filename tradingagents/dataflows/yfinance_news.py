"""yfinance-based news data fetching functions."""

import yfinance as yf
import requests
from datetime import datetime
from dateutil.relativedelta import relativedelta
from .finnhub_common import ThirdPartyTimeoutError


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
            return f"No news found for {ticker} between {start_date} and {end_date}"

        return f"## {ticker} News, from {start_date} to {end_date}:\n\n{news_str}"

    except requests.exceptions.Timeout:
        raise ThirdPartyTimeoutError(f"Request timed out fetching news for {ticker}")
    except ThirdPartyTimeoutError:
        raise
    except Exception as e:
        return f"Error fetching news for {ticker}: {str(e)}"


def get_social_sentiment_yfinance(
    ticker: str,
    start_date: str,
    end_date: str,
) -> str:
    """
    Retrieve headline-level sentiment signals for a stock ticker using yfinance.

    Extracts article titles, publishers, and publish timestamps, then scores each
    headline with a simple keyword-based polarity score.  Aggregates into overall
    sentiment distribution, publisher breakdown, and a first-half vs second-half
    sentiment trend for the requested period.

    Args:
        ticker: Stock ticker symbol (e.g., "AAPL")
        start_date: Start date in yyyy-mm-dd format
        end_date: End date in yyyy-mm-dd format

    Returns:
        Formatted string with headline list, sentiment scores, aggregate stats,
        publisher distribution, and sentiment trend.
    """
    POSITIVE_KEYWORDS = {
        "surge", "jump", "beat", "strong", "growth", "upgrade", "rally",
        "gain", "profit", "breakthrough", "record", "soar", "boom",
        "outperform", "bullish",
    }
    NEGATIVE_KEYWORDS = {
        "fall", "drop", "miss", "weak", "decline", "downgrade", "crash",
        "loss", "risk", "warning", "cut", "plunge", "slump",
        "underperform", "bearish",
    }

    def _score_headline(title: str) -> int:
        words = title.lower().split()
        pos = sum(1 for w in words if w.strip(".,!?;:\"'") in POSITIVE_KEYWORDS)
        neg = sum(1 for w in words if w.strip(".,!?;:\"'") in NEGATIVE_KEYWORDS)
        return pos - neg

    try:
        stock = yf.Ticker(ticker)
        news = stock.get_news(count=20)

        if not news:
            return f"No social sentiment data available for {ticker}"

        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")

        articles = []
        for article in news:
            data = _extract_article_data(article)

            # Filter by date if available
            if data["pub_date"]:
                pub_date_naive = data["pub_date"].replace(tzinfo=None)
                if not (start_dt <= pub_date_naive <= end_dt + relativedelta(days=1)):
                    continue

            score = _score_headline(data["title"])
            articles.append({
                "title": data["title"],
                "publisher": data["publisher"],
                "pub_date": data["pub_date"],
                "score": score,
            })

        if not articles:
            return f"No social sentiment data available for {ticker} between {start_date} and {end_date}"

        # ── Headline list ──────────────────────────────────────────────────────
        headline_lines = []
        for a in articles:
            date_str = a["pub_date"].strftime("%Y-%m-%d") if a["pub_date"] else "unknown date"
            polarity = "+" if a["score"] > 0 else ("-" if a["score"] < 0 else "~")
            headline_lines.append(
                f"  [{polarity}{abs(a['score'])}] {a['title']}  |  {a['publisher']}  |  {date_str}"
            )

        # ── Aggregate sentiment distribution ──────────────────────────────────
        positive = sum(1 for a in articles if a["score"] > 0)
        negative = sum(1 for a in articles if a["score"] < 0)
        neutral = len(articles) - positive - negative
        total = len(articles)
        pct_pos = round(100 * positive / total)
        pct_neg = round(100 * negative / total)
        pct_neu = round(100 * neutral / total)

        # ── Publisher distribution ─────────────────────────────────────────────
        publisher_counts: dict = {}
        for a in articles:
            publisher_counts[a["publisher"]] = publisher_counts.get(a["publisher"], 0) + 1
        publisher_lines = [
            f"  {pub}: {cnt} article{'s' if cnt > 1 else ''}"
            for pub, cnt in sorted(publisher_counts.items(), key=lambda x: -x[1])
        ]

        # ── Sentiment trend: first half vs second half ────────────────────────
        mid = len(articles) // 2
        first_half = articles[:mid] if mid else articles
        second_half = articles[mid:] if mid else articles
        avg_first = sum(a["score"] for a in first_half) / len(first_half) if first_half else 0
        avg_second = sum(a["score"] for a in second_half) / len(second_half) if second_half else 0
        trend_direction = (
            "improving" if avg_second > avg_first
            else "deteriorating" if avg_second < avg_first
            else "stable"
        )

        output = (
            f"## {ticker} Social Sentiment Signals, {start_date} to {end_date}\n\n"
            f"### Headlines & Polarity Scores  (+ positive / - negative / ~ neutral)\n"
            + "\n".join(headline_lines)
            + f"\n\n### Aggregate Sentiment Distribution  ({total} articles)\n"
            f"  Positive: {pct_pos}%  |  Negative: {pct_neg}%  |  Neutral: {pct_neu}%\n"
            f"\n### Publisher Distribution\n"
            + "\n".join(publisher_lines)
            + f"\n\n### Sentiment Trend (first half vs second half of period)\n"
            f"  First-half avg score:  {avg_first:.2f}\n"
            f"  Second-half avg score: {avg_second:.2f}\n"
            f"  Trend: {trend_direction}\n"
        )
        return output

    except requests.exceptions.Timeout:
        raise ThirdPartyTimeoutError(f"Request timed out fetching sentiment data for {ticker}")
    except ThirdPartyTimeoutError:
        raise
    except Exception as e:
        return f"No social sentiment data available for {ticker}: {str(e)}"


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
            search = yf.Search(
                query=query,
                news_count=limit,
                enable_fuzzy_query=True,
            )

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

    except requests.exceptions.Timeout:
        raise ThirdPartyTimeoutError(f"Request timed out fetching global news")
    except ThirdPartyTimeoutError:
        raise
    except Exception as e:
        return f"Error fetching global news: {str(e)}"
