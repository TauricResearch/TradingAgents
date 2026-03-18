"""Vietnam news provider using vnstock and VnExpress RSS."""

import feedparser
import requests
from datetime import datetime
from dateutil.relativedelta import relativedelta

from . import config as vn_config

_RSS_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
}


def _parse_rss_articles(feed_url: str, limit: int = 20) -> list:
    """Parse articles from an RSS feed URL using requests for proper headers."""
    articles = []
    try:
        resp = requests.get(feed_url, headers=_RSS_HEADERS, timeout=10)
        if resp.status_code != 200:
            return articles

        feed = feedparser.parse(resp.text)
        for entry in feed.entries[:limit]:
            pub_date = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                try:
                    pub_date = datetime(*entry.published_parsed[:6])
                except Exception:
                    pass

            articles.append({
                "title": entry.get("title", "No title"),
                "summary": entry.get("summary", ""),
                "link": entry.get("link", ""),
                "publisher": feed.feed.get("title", "VnExpress"),
                "pub_date": pub_date,
            })
    except Exception as e:
        print(f"Warning: Could not parse RSS feed {feed_url}: {e}")

    return articles


def _get_vnstock_news(ticker: str, source: str = "VCI") -> list:
    """Fetch news from vnstock company.news() API."""
    articles = []
    try:
        from vnstock import Vnstock
        stock = Vnstock().stock(symbol=ticker.upper(), source=source)
        news_df = stock.company.news()

        if news_df is not None and not news_df.empty:
            for _, row in news_df.iterrows():
                pub_date = None
                date_str = row.get("public_date") or row.get("created_at")
                if date_str:
                    try:
                        pub_date = datetime.fromisoformat(str(date_str).replace("Z", "+00:00"))
                        pub_date = pub_date.replace(tzinfo=None)
                    except (ValueError, AttributeError):
                        pass

                articles.append({
                    "title": row.get("news_title", "No title"),
                    "summary": row.get("news_short_content", ""),
                    "link": row.get("news_source_link", ""),
                    "publisher": "vnstock",
                    "pub_date": pub_date,
                })
    except Exception as e:
        print(f"Warning: vnstock news fetch failed for {ticker}: {e}")

    return articles


def _filter_by_date(articles: list, start_dt: datetime, end_dt: datetime) -> list:
    """Filter articles by date range."""
    filtered = []
    for article in articles:
        if article["pub_date"]:
            pub = article["pub_date"]
            if isinstance(pub, datetime) and not (start_dt <= pub <= end_dt + relativedelta(days=1)):
                continue
        filtered.append(article)
    return filtered


def _strip_html(text: str) -> str:
    """Strip HTML tags from text."""
    try:
        from parsel import Selector
        sel = Selector(text=text)
        clean = sel.css("::text").getall()
        return " ".join(clean) if clean else text
    except ImportError:
        import re
        return re.sub(r"<[^>]+>", "", text)


def _format_articles(articles: list, header: str) -> str:
    """Format articles into the standard output string."""
    if not articles:
        return header + "No articles found.\n"

    news_str = ""
    seen_titles = set()
    for article in articles:
        title = article["title"]
        if title in seen_titles:
            continue
        seen_titles.add(title)

        news_str += f"### {title} (source: {article['publisher']})\n"
        if article.get("summary"):
            summary = _strip_html(article["summary"])
            news_str += f"{summary}\n"
        if article.get("link"):
            news_str += f"Link: {article['link']}\n"
        news_str += "\n"

    return header + news_str


def get_news_vn(
    ticker: str,
    start_date: str,
    end_date: str,
    source: str = "VCI",
) -> str:
    """
    Retrieve news for a VN stock ticker.

    Priority chain:
    1. vnstock company.news() API
    2. VnExpress RSS filtered by ticker keyword
    """
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    all_articles = []

    # 1. Try vnstock built-in news
    vnstock_articles = _get_vnstock_news(ticker, source=source)
    all_articles.extend(vnstock_articles)

    # 2. Try VnExpress RSS filtered by ticker
    for url in vn_config.VNEXPRESS_RSS_URLS:
        rss_articles = _parse_rss_articles(url, limit=30)
        ticker_upper = ticker.upper()
        for article in rss_articles:
            title_upper = article["title"].upper()
            summary_upper = article.get("summary", "").upper()
            if ticker_upper in title_upper or ticker_upper in summary_upper:
                all_articles.append(article)

    # Filter by date range
    all_articles = _filter_by_date(all_articles, start_dt, end_dt)

    if not all_articles:
        return f"No news found for {ticker} between {start_date} and {end_date}"

    header = f"## {ticker} News (Vietnam Market), from {start_date} to {end_date}:\n\n"
    return _format_articles(all_articles, header)


def get_global_news_vn(
    curr_date: str,
    look_back_days: int = 7,
    limit: int = 10,
) -> str:
    """
    Retrieve global/macro Vietnam market news from VnExpress RSS.
    """
    curr_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    start_dt = curr_dt - relativedelta(days=look_back_days)
    start_date = start_dt.strftime("%Y-%m-%d")

    all_articles = []
    seen_titles = set()

    # Fetch from VnExpress RSS
    for url in vn_config.VNEXPRESS_RSS_URLS:
        rss_articles = _parse_rss_articles(url, limit=limit * 2)
        for article in rss_articles:
            title = article["title"]
            if title not in seen_titles:
                seen_titles.add(title)
                all_articles.append(article)

        if len(all_articles) >= limit:
            break

    # Filter by date range
    all_articles = _filter_by_date(all_articles, start_dt, curr_dt)

    # Limit results
    all_articles = all_articles[:limit]

    if not all_articles:
        return f"No Vietnam market news found for {curr_date}"

    header = f"## Vietnam Market News, from {start_date} to {curr_date}:\n\n"
    return _format_articles(all_articles, header)
