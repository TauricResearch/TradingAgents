"""yfinance-based news, macro, and sentiment helpers."""

from __future__ import annotations

from datetime import datetime, timezone

from dateutil.relativedelta import relativedelta
import yfinance as yf

from .news_models import (
    NewsItem,
    dedupe_news_items,
    filter_news_items_by_date,
    format_news_items_report,
    normalize_datetime,
)
from .stockstats_utils import yf_retry


_TICKER_NEWS_FETCH_COUNTS = (20, 50, 100)
_MAX_FILTERED_TICKER_ARTICLES = 25
_GLOBAL_QUERY_PRESETS = {
    "US": [
        "stock market economy",
        "Federal Reserve interest rates",
        "inflation economic outlook",
        "global markets trading",
    ],
    "KR": [
        "한국 증시",
        "한국은행 기준금리",
        "원달러 환율",
        "반도체 수출",
    ],
    "GLOBAL": [
        "stock market economy",
        "global markets trading",
        "economy monetary policy",
        "inflation growth outlook",
    ],
}


def _extract_article_fields(article: dict) -> dict:
    """Extract article data from yfinance news format."""
    if "content" in article:
        content = article["content"]
        provider = content.get("provider", {})
        url_obj = content.get("canonicalUrl") or content.get("clickThroughUrl") or {}
        return {
            "title": content.get("title", "No title"),
            "summary": content.get("summary", ""),
            "publisher": provider.get("displayName", "Unknown"),
            "link": url_obj.get("url", ""),
            "pub_date": normalize_datetime(content.get("pubDate")),
            "raw_symbols": content.get("relatedTickers") or [],
        }

    return {
        "title": article.get("title", "No title"),
        "summary": article.get("summary", ""),
        "publisher": article.get("publisher", "Unknown"),
        "link": article.get("link", ""),
        "pub_date": normalize_datetime(article.get("providerPublishTime")),
        "raw_symbols": article.get("relatedTickers") or [],
    }


def normalize_yfinance_article(article: dict, *, fallback_symbol: str | None = None, country: str | None = None) -> NewsItem:
    data = _extract_article_fields(article)
    symbols = [str(symbol).upper() for symbol in data["raw_symbols"] if str(symbol).strip()]
    if fallback_symbol and fallback_symbol.upper() not in symbols:
        symbols.append(fallback_symbol.upper())
    return NewsItem(
        title=data["title"],
        source=data["publisher"],
        published_at=data["pub_date"],
        language=None,
        country=country,
        symbols=symbols,
        topic_tags=[],
        sentiment=None,
        relevance=None,
        reliability=None,
        url=data["link"],
        summary=data["summary"],
        raw_vendor="yfinance",
    )


def _collect_ticker_news(
    ticker: str,
    start_dt: datetime,
) -> tuple[list[NewsItem], datetime | None, datetime | None]:
    """Fetch increasingly larger ticker feeds until the requested window is covered."""
    collected: list[NewsItem] = []
    oldest_pub_date = None
    newest_pub_date = None

    for count in _TICKER_NEWS_FETCH_COUNTS:
        news = yf_retry(lambda batch_size=count: yf.Ticker(ticker).get_news(count=batch_size))
        if not news:
            continue

        batch = dedupe_news_items(
            [normalize_yfinance_article(article, fallback_symbol=ticker) for article in news]
        )

        for item in batch:
            collected.append(item)
            pub_date = item.published_at
            if pub_date:
                if newest_pub_date is None or pub_date > newest_pub_date:
                    newest_pub_date = pub_date
                if oldest_pub_date is None or pub_date < oldest_pub_date:
                    oldest_pub_date = pub_date

        if oldest_pub_date and oldest_pub_date.replace(tzinfo=None) <= start_dt:
            break
        if len(news) < count:
            break

    collected = dedupe_news_items(collected)
    collected.sort(
        key=lambda article: article.published_at.timestamp() if article.published_at else float("-inf"),
        reverse=True,
    )
    return collected, oldest_pub_date, newest_pub_date


def _format_coverage_note(oldest_pub_date: datetime | None, newest_pub_date: datetime | None) -> str:
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


def fetch_company_news_yfinance(
    ticker: str,
    start_date: str,
    end_date: str,
) -> tuple[list[NewsItem], datetime | None, datetime | None]:
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d") + relativedelta(days=1)
    articles, oldest_pub_date, newest_pub_date = _collect_ticker_news(ticker, start_dt)
    filtered = filter_news_items_by_date(articles, start_date=start_dt, end_date=end_dt)
    return filtered[:_MAX_FILTERED_TICKER_ARTICLES], oldest_pub_date, newest_pub_date


def get_company_news_yfinance(
    ticker: str,
    start_date: str,
    end_date: str,
) -> str:
    try:
        filtered, oldest_pub_date, newest_pub_date = fetch_company_news_yfinance(ticker, start_date, end_date)
        if not filtered:
            coverage_note = _format_coverage_note(oldest_pub_date, newest_pub_date)
            return f"No news found for {ticker} between {start_date} and {end_date}{coverage_note}"
        return format_news_items_report(
            f"{ticker} Company News, from {start_date} to {end_date}",
            filtered,
            max_items=_MAX_FILTERED_TICKER_ARTICLES,
        )
    except Exception as exc:
        return f"Error fetching news for {ticker}: {exc}"


def _get_query_preset(region: str | None) -> list[str]:
    if not region:
        return _GLOBAL_QUERY_PRESETS["GLOBAL"]
    return _GLOBAL_QUERY_PRESETS.get(region.upper(), _GLOBAL_QUERY_PRESETS["GLOBAL"])


def fetch_macro_news_yfinance(
    curr_date: str,
    look_back_days: int = 7,
    limit: int = 10,
    region: str | None = None,
    language: str | None = None,
) -> list[NewsItem]:
    curr_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    start_dt = curr_dt - relativedelta(days=look_back_days)
    country = (region or "GLOBAL").upper()

    all_news: list[NewsItem] = []
    for query in _get_query_preset(region):
        search = yf_retry(
            lambda q=query: yf.Search(
                query=q if not language else f"{q} {language}",
                news_count=limit,
                enable_fuzzy_query=True,
            )
        )
        search_news = getattr(search, "news", None) or []
        batch = [normalize_yfinance_article(article, country=country) for article in search_news]
        all_news.extend(batch)
        if len(all_news) >= limit * len(_get_query_preset(region)):
            break

    filtered = []
    for item in dedupe_news_items(all_news):
        if item.published_at:
            published = item.published_at.replace(tzinfo=None)
            if published < start_dt or published > curr_dt + relativedelta(days=1):
                continue
        filtered.append(item)

    filtered.sort(
        key=lambda article: article.published_at.timestamp() if article.published_at else float("-inf"),
        reverse=True,
    )
    return filtered[:limit]


def get_macro_news_yfinance(
    curr_date: str,
    look_back_days: int = 7,
    limit: int = 10,
    region: str | None = None,
    language: str | None = None,
) -> str:
    try:
        items = fetch_macro_news_yfinance(
            curr_date,
            look_back_days=look_back_days,
            limit=limit,
            region=region,
            language=language,
        )
        if not items:
            return f"No global news found for {curr_date}"
        start_date = (datetime.strptime(curr_date, "%Y-%m-%d") - relativedelta(days=look_back_days)).strftime("%Y-%m-%d")
        region_label = (region or "GLOBAL").upper()
        return format_news_items_report(
            f"{region_label} Macro News, from {start_date} to {curr_date}",
            items,
            max_items=limit,
        )
    except Exception as exc:
        return f"Error fetching global news: {exc}"


def get_social_sentiment_yfinance(
    symbol: str,
    start_date: str,
    end_date: str,
) -> str:
    articles, _, _ = fetch_company_news_yfinance(symbol, start_date, end_date)
    if not articles:
        return (
            f"Dedicated social provider unavailable; no news-derived sentiment was found for {symbol} "
            f"between {start_date} and {end_date}."
        )

    report_lines = [
        f"Dedicated social provider unavailable; using news-derived sentiment for {symbol} from {start_date} to {end_date}.",
        "Use this as public-narrative context rather than a literal social-media feed.",
        "",
    ]
    for item in articles[:10]:
        date_prefix = item.published_at.strftime("%Y-%m-%d") if item.published_at else "undated"
        summary = item.summary or "No summary available."
        report_lines.append(f"- {date_prefix}: {item.title} ({item.source})")
        report_lines.append(f"  Narrative: {summary}")
    return "\n".join(report_lines)


# Backward-compatible aliases
get_news_yfinance = get_company_news_yfinance
get_global_news_yfinance = get_macro_news_yfinance
