"""Google News RSS-based news fetching for Malaysian stocks.

Google News RSS provides structured, reliable access to news articles from
Malaysian financial sources (The Edge Malaysia, The Star, BusinessToday,
Malaysian Reserve, etc.) without requiring API keys or JavaScript rendering.
"""

from datetime import datetime, timedelta
from typing import Optional
from xml.etree import ElementTree as ET

import requests
import yfinance as yf

from .config import get_config


GOOGLE_NEWS_RSS = "https://news.google.com/rss/search"

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)


def _get_company_name(ticker: str) -> str:
    """Resolve a ticker to its company name via yfinance.

    Prefers ``shortName`` over ``longName`` because shorter names tend to
    return better Google News RSS results (``longName`` often includes a
    legal suffix like "Berhad" or "Limited" that reduces recall).
    """
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        return info.get("shortName") or info.get("longName") or ""
    except Exception:
        return ""


def _parse_rss_date(date_str: str) -> Optional[datetime]:
    """Parse an RSS pubDate string to a datetime."""
    if not date_str:
        return None
    for fmt in ("%a, %d %b %Y %H:%M:%S %Z", "%a, %d %b %Y %H:%M:%S %z"):
        try:
            return datetime.strptime(date_str, fmt)
        except (ValueError, TypeError):
            continue
    return None


def _fetch_rss(query: str, limit: int) -> list[dict]:
    """Fetch and parse Google News RSS for a query. Returns list of articles."""
    params = {
        "q": query,
        "hl": "en-MY",
        "gl": "MY",
        "ceid": "MY:en",
    }
    try:
        resp = requests.get(
            GOOGLE_NEWS_RSS,
            params=params,
            headers={"User-Agent": _USER_AGENT},
            timeout=15,
        )
        resp.raise_for_status()
    except requests.RequestException:
        return []

    try:
        root = ET.fromstring(resp.content)
    except ET.ParseError:
        return []

    items = root.findall(".//item")
    articles = []
    seen_titles = set()

    for item in items:
        title = (item.findtext("title") or "").strip()
        if not title or len(title) < 15:
            continue

        # Deduplicate by normalized title
        title_lower = title.lower().strip()
        if title_lower in seen_titles:
            continue
        seen_titles.add(title_lower)

        link = item.findtext("link", "")
        source = (item.findtext("source") or "").strip()
        pub_date_str = item.findtext("pubDate", "")
        pub_date = _parse_rss_date(pub_date_str)

        articles.append({
            "title": title,
            "link": link,
            "source": source or "Google News",
            "pub_date": pub_date,
        })

        if len(articles) >= limit:
            break

    return articles


def get_news_google(
    ticker: str,
    start_date: str,
    end_date: str,
) -> str:
    """Retrieve news for a stock ticker using Google News RSS, with a focus
    on Malaysian financial news sources when the ticker has a ``.KL`` suffix.

    Uses a multi-query strategy: tries several query variants and
    deduplicates results, so a single query format failing (e.g. no recent
    articles for the exact company name) doesn't leave the agent empty-handed.

    Args:
        ticker: Stock ticker symbol (e.g., ``0275.KL``, ``AAPL``)
        start_date: Start date in yyyy-mm-dd format
        end_date: End date in yyyy-mm-dd format

    Returns:
        Formatted string containing news articles
    """
    config = get_config()
    article_limit = config.get("news_article_limit", 20)
    is_malaysia = ticker.upper().endswith(".KL")

    stock_code = ticker.split(".")[0]
    company_name = _get_company_name(ticker)

    # Build multiple queries to maximise recall.  No ``site:`` filters or
    # quoted exact phrases because Google News RSS handles them poorly.
    queries = []
    if is_malaysia:
        if company_name:
            queries.append(f"{company_name} Malaysia stock")
            queries.append(f"{company_name} {stock_code} Malaysia")
        queries.append(f"{stock_code} Malaysia stock")
    else:
        name_part = company_name or stock_code
        queries.append(f"{name_part} stock news")
        if company_name and stock_code:
            queries.append(f"{company_name} {stock_code}")

    # Fetch from each query, deduplicate across queries
    all_articles = []
    seen_titles = set()

    for query in queries:
        articles = _fetch_rss(query, article_limit)
        for article in articles:
            title_lower = article["title"].lower().strip()
            if title_lower not in seen_titles:
                seen_titles.add(title_lower)
                all_articles.append(article)

    if not all_articles:
        return f"No news found for {ticker}"

    # Filter by date range
    try:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
    except ValueError:
        start_dt = end_dt = None

    news_str = ""
    filtered_count = 0

    for article in all_articles:
        if start_dt and article["pub_date"]:
            if not (start_dt <= article["pub_date"] <= end_dt):
                continue

        news_str += f"### {article['title']} (source: {article['source']})\n"
        if article["link"]:
            news_str += f"Link: {article['link']}\n"
        news_str += "\n"
        filtered_count += 1

    if filtered_count == 0:
        return f"No news found for {ticker} between {start_date} and {end_date}"

    return f"## {ticker} News, from {start_date} to {end_date}:\n\n{news_str}"


def get_global_news_google(
    curr_date: str,
    look_back_days: Optional[int] = None,
    limit: Optional[int] = None,
) -> str:
    """Retrieve global/macroeconomic news using Google News RSS with a focus
    on Malaysian and regional economic news.

    Args:
        curr_date: Current date in yyyy-mm-dd format
        look_back_days: Number of days to look back. ``None`` falls back to
            ``global_news_lookback_days`` from the active config.
        limit: Maximum number of articles to return. ``None`` falls back to
            ``global_news_article_limit`` from the active config.

    Returns:
        Formatted string containing global news articles
    """
    config = get_config()
    if look_back_days is None:
        look_back_days = config["global_news_lookback_days"]
    if limit is None:
        limit = config["global_news_article_limit"]

    try:
        curr_dt = datetime.strptime(curr_date, "%Y-%m-%d")
        start_dt = curr_dt - timedelta(days=look_back_days)
    except ValueError:
        curr_dt = datetime.now()
        start_dt = curr_dt - timedelta(days=look_back_days)

    start_date = start_dt.strftime("%Y-%m-%d")

    queries = [
        "Bursa Malaysia KLSE economy",
        "Malaysia central bank OPR ringgit trade",
        "ASEAN Southeast Asia economic growth",
        "Federal Reserve interest rates inflation global economy",
    ]

    all_articles = []
    seen_titles = set()

    for query in queries:
        articles = _fetch_rss(query, limit)
        for article in articles:
            title_lower = article["title"].lower().strip()
            if title_lower not in seen_titles:
                seen_titles.add(title_lower)
                all_articles.append(article)
        if len(all_articles) >= limit * 2:
            break

    if not all_articles:
        return f"No global news found for {curr_date}"

    news_str = ""
    for article in all_articles[:limit]:
        if article["pub_date"] and article["pub_date"] > curr_dt + timedelta(days=1):
            continue

        news_str += f"### {article['title']} (source: {article['source']})\n"
        if article["link"]:
            news_str += f"Link: {article['link']}\n"
        news_str += "\n"

    return f"## Global Market News, from {start_date} to {curr_date}:\n\n{news_str}"
