"""India-scoped news vendor: ET Markets RSS (direct feed) + Google News RSS (search).

yfinance's ``get_news`` mostly surfaces globally-syndicated wire stories and
has thin coverage for NSE/BSE-listed names — the exact gap flagged in the
KALYANKJIL/NBCC options research (individual Indian stock moves are often
driven by discrete company/PSU/regulatory news that a US-centric vendor
doesn't index).

Two keyless sources, combined:
  - ET Markets' own RSS feed is real Indian financial press covering
    corporate announcements, earnings dates, order wins, block deals, etc. —
    but it's a firehose (no per-ticker query param), so it's filtered by
    ticker-name substring match for per-stock lookups.
  - Google News' RSS search endpoint fills the per-ticker search gap and,
    when scoped with ``gl=IN&ceid=IN:en``, still ranks Indian financial press
    (Moneycontrol, CNBC TV18, Business Standard) ahead of global sources.

NSE's own corporate-announcements RSS (the gold standard for discrete
company events) was evaluated but is blocked by NSE's bot-protection WAF for
non-browser clients — the same class of block already tracked for AngelOne's
API (#155). Revisit if that's ever resolved.

Both sources return only recent articles (no deep historical archive), so
this vendor serves *live* analysis, not retroactive news-to-chart backtesting.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime

import requests
from dateutil.relativedelta import relativedelta

from .config import get_config
from .utils import in_news_window

_GOOGLE_NEWS_RSS_URL = "https://news.google.com/rss/search"
_ET_MARKETS_RSS_URL = "https://economictimes.indiatimes.com/markets/stocks/rssfeeds/2146842.cms"
_TIMEOUT_S = 10
_HEADERS = {"User-Agent": "Mozilla/5.0"}


def _strip_exchange_suffix(ticker: str) -> str:
    """``RELIANCE.NS`` / ``NBCC.BO`` -> ``RELIANCE`` / ``NBCC`` for matching/search."""
    for suffix in (".NS", ".BO"):
        if ticker.upper().endswith(suffix):
            return ticker[: -len(suffix)]
    return ticker


def _parse_rss_items(content: bytes, limit: int) -> list[dict]:
    """Parse a generic RSS ``<item>`` list into ``{title, link, publisher, pub_date}`` dicts."""
    root = ET.fromstring(content)
    articles = []
    for item in list(root.iterfind(".//item"))[:limit]:
        title_el = item.find("title")
        link_el = item.find("link")
        pubdate_el = item.find("pubDate")
        source_el = item.find("source")

        pub_date = None
        if pubdate_el is not None and pubdate_el.text:
            try:
                # Keep whatever offset the feed provides (most RSS pubDate values
                # carry one, e.g. "+0530" or "GMT") -- in_news_window/date_window
                # converts correctly regardless. Stripping it here instead (the
                # old behavior) discarded the real offset and silently misread
                # the timestamp as UTC, the same class of bug fixed for the
                # Yahoo vendor in #1126.
                pub_date = parsedate_to_datetime(pubdate_el.text)
            except (ValueError, TypeError):
                pub_date = None

        articles.append({
            "title": title_el.text if title_el is not None else "No title",
            "link": link_el.text if link_el is not None else "",
            "publisher": source_el.text if source_el is not None and source_el.text else "Economic Times",
            "pub_date": pub_date,
        })
    return articles


def _fetch_google_news(query: str, limit: int) -> list[dict]:
    """Query Google News RSS search, scoped to India."""
    params = {"q": query, "hl": "en-IN", "gl": "IN", "ceid": "IN:en"}
    resp = requests.get(_GOOGLE_NEWS_RSS_URL, params=params, timeout=_TIMEOUT_S, headers=_HEADERS)
    resp.raise_for_status()
    return _parse_rss_items(resp.content, limit)


def _fetch_et_markets(limit: int) -> list[dict]:
    """Fetch ET Markets' general stocks RSS feed (not per-ticker queryable)."""
    resp = requests.get(_ET_MARKETS_RSS_URL, timeout=_TIMEOUT_S, headers=_HEADERS)
    resp.raise_for_status()
    return _parse_rss_items(resp.content, limit)


def _dedupe_by_title(articles: list[dict]) -> list[dict]:
    seen = set()
    out = []
    for article in articles:
        if article["title"] not in seen:
            seen.add(article["title"])
            out.append(article)
    return out


def get_news_india(ticker: str, start_date: str, end_date: str) -> str:
    """Retrieve India-scoped news for a specific stock ticker.

    Combines ET Markets' general feed (filtered by ticker-name substring
    match in the headline) with a targeted Google News RSS search, since
    neither source alone reliably covers a given NSE/BSE name.

    Args:
        ticker: NSE/BSE ticker, with or without ``.NS``/``.BO`` suffix (e.g. "NBCC", "NBCC.NS").
        start_date: Start date in yyyy-mm-dd format.
        end_date: End date in yyyy-mm-dd format.

    Returns:
        Formatted string containing news articles.
    """
    article_limit = get_config()["news_article_limit"]
    query_ticker = _strip_exchange_suffix(ticker)
    try:
        et_articles = [
            a for a in _fetch_et_markets(100)
            if query_ticker.lower() in a["title"].lower()
        ]
        google_articles = _fetch_google_news(f"{query_ticker} stock NSE", article_limit)
        articles = _dedupe_by_title(et_articles + google_articles)[:article_limit]

        if not articles:
            return f"No news found for {ticker}"

        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")

        news_str = ""
        filtered_count = 0
        for article in articles:
            if not in_news_window(article["pub_date"], start_dt, end_dt):
                continue
            news_str += f"### {article['title']} (source: {article['publisher']})\n"
            if article["link"]:
                news_str += f"Link: {article['link']}\n"
            news_str += "\n"
            filtered_count += 1

        if filtered_count == 0:
            return f"No news found for {ticker} between {start_date} and {end_date}"

        return f"## {ticker} News, from {start_date} to {end_date}:\n\n{news_str}"

    except Exception as e:
        return f"Error fetching news for {ticker}: {str(e)}"


def get_global_news_india(
    curr_date: str,
    look_back_days: int | None = None,
    limit: int | None = None,
) -> str:
    """Retrieve India-scoped macro/market news.

    ET Markets' general feed is the primary source (real Indian financial
    press, not keyword-search-ranked); Google News topic queries top up the
    macro angle (RBI policy, SEBI regulation, FII/DII flows) that a pure
    stock-market feed under-covers.

    Args:
        curr_date: Current date in yyyy-mm-dd format.
        look_back_days: Lookback window in days. ``None`` falls back to
            ``global_news_lookback_days`` from the active config.
        limit: Max articles to return. ``None`` falls back to
            ``global_news_article_limit`` from the active config.

    Returns:
        Formatted string containing global news articles.
    """
    config = get_config()
    if look_back_days is None:
        look_back_days = config["global_news_lookback_days"]
    if limit is None:
        limit = config["global_news_article_limit"]

    macro_queries = [
        "RBI monetary policy repo rate India",
        "SEBI regulation India markets",
        "FII DII flows India equity",
    ]

    try:
        all_articles = list(_fetch_et_markets(limit))
        for query in macro_queries:
            if len(all_articles) >= limit:
                break
            all_articles.extend(_fetch_google_news(query, limit))

        all_articles = _dedupe_by_title(all_articles)

        if not all_articles:
            return f"No global news found for {curr_date}"

        curr_dt = datetime.strptime(curr_date, "%Y-%m-%d")
        start_dt = curr_dt - relativedelta(days=look_back_days)
        start_date = start_dt.strftime("%Y-%m-%d")

        news_str = ""
        kept = 0
        for article in all_articles[:limit]:
            if not in_news_window(article["pub_date"], start_dt, curr_dt):
                continue
            news_str += f"### {article['title']} (source: {article['publisher']})\n"
            if article["link"]:
                news_str += f"Link: {article['link']}\n"
            news_str += "\n"
            kept += 1

        if kept == 0:
            return f"No global news found between {start_date} and {curr_date}"

        return f"## Global Market News (India), from {start_date} to {curr_date}:\n\n{news_str}"

    except Exception as e:
        return f"Error fetching global news: {str(e)}"
