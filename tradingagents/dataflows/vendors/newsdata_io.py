"""NewsData.io market-news vendor.

The Market endpoint serves symbol-specific and broad financial news. One page is
requested per tool call to keep API-credit use bounded. Results are filtered locally against the requested window so a historical
analysis never sees future news.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta

from tradingagents.dataflows.config import get_config
from tradingagents.dataflows.date_window import coverage_gap, in_window
from tradingagents.dataflows.errors import (
    NoMarketDataError,
    VendorNotConfiguredError,
    VendorUnavailableError,
)
from tradingagents.dataflows.net import get_scrubbed

API_URL = "https://newsdata.io/api/1/market"
REQUEST_TIMEOUT = 30


class NewsDataNotConfiguredError(VendorNotConfiguredError):
    """NewsData.io was selected without a usable API key."""


def _api_key() -> str:
    key = os.getenv("NEWSDATA_API_KEY", "").strip()
    if not key:
        raise NewsDataNotConfiguredError(
            "NEWSDATA_API_KEY is not configured. Create a key at https://newsdata.io/."
        )
    return key


def _error_message(payload: dict, fallback: str) -> str:
    value = payload.get("results") or payload.get("message") or fallback
    if isinstance(value, dict):
        value = value.get("message") or value.get("error") or str(value)
    return " ".join(str(value).split())


def _request(params: dict) -> dict:
    key = _api_key()
    response = get_scrubbed(
        API_URL,
        params={**params, "apikey": key},
        timeout=REQUEST_TIMEOUT,
        secret=key,
        passthrough=(400, 401, 403, 422, 429),
    )
    try:
        payload = response.json()
    except ValueError as exc:
        raise VendorUnavailableError("NewsData.io returned an unreadable response") from exc

    if response.status_code < 400 and payload.get("status") != "error":
        return payload

    message = _error_message(payload, f"HTTP {response.status_code}")
    low = message.lower()
    if response.status_code in (401, 403) or "api key" in low or "apikey" in low:
        raise NewsDataNotConfiguredError(f"NewsData.io authentication failed: {message}")
    if response.status_code == 429 or any(
        marker in low for marker in ("rate limit", "credit", "quota", "too many")
    ):
        raise VendorUnavailableError(f"NewsData.io limit reached: {message}")
    # Entitlement/date failures should fall through to the next configured
    # source instead of aborting the complete analysis.
    raise VendorUnavailableError(f"NewsData.io request unavailable: {message}")


def _published_at(article: dict) -> datetime | None:
    raw = article.get("pubDate")
    if not raw:
        return None
    value = str(raw).strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                continue
    return None


def _render(
    payload: dict,
    *,
    start_date: str,
    end_date: str,
    limit: int,
    subject: str,
    heading: str,
) -> str:
    raw_results = payload.get("results")
    if not isinstance(raw_results, list):
        raise VendorUnavailableError("NewsData.io returned an unexpected response shape")

    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    articles = []
    seen = set()
    for article in raw_results:
        if not isinstance(article, dict):
            continue
        published = _published_at(article)
        if not in_window(published, start_dt, end_dt):
            continue
        title = " ".join(str(article.get("title") or "").split())
        dedupe_key = article.get("article_id") or (title, article.get("link"))
        if not title or dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        articles.append((article, published, title))
        if len(articles) >= limit:
            break

    if not articles:
        gap = coverage_gap(
            (_published_at(item) for item in raw_results if isinstance(item, dict)),
            start_date,
            end_date,
            "NewsData.io market news",
            subject,
        )
        detail = gap or f"no matching articles within {start_date}..{end_date}"
        raise NoMarketDataError(subject, subject, detail)

    lines = [f"## {heading}, from {start_date} to {end_date}:", ""]
    gap = coverage_gap(
        (_published_at(item) for item in raw_results if isinstance(item, dict)),
        start_date,
        end_date,
        "NewsData.io market news",
        subject,
    )
    if gap:
        clean_gap = gap.removeprefix("<").removesuffix(">")
        lines.extend([f"Coverage note: {clean_gap}", ""])
    for article, published, title in articles:
        source = article.get("source_name") or article.get("source_id") or "Unknown"
        lines.append(f"### {title} (source: {source})")
        meta = []
        if published:
            meta.append(f"Published: {published.isoformat()}")
        if article.get("sentiment"):
            meta.append(f"Vendor sentiment: {article['sentiment']}")
        if meta:
            lines.append(" · ".join(meta))
        description = " ".join(str(article.get("description") or "").split())
        if description:
            lines.append(description[:1000] + ("…" if len(description) > 1000 else ""))
        if article.get("link"):
            lines.append(f"Link: {article['link']}")
        lines.append("")
    return "\n".join(lines).rstrip()


def get_news(ticker: str, start_date: str, end_date: str) -> str:
    """Return NewsData.io financial news associated with ``ticker``."""
    limit = int(get_config()["news_article_limit"])
    payload = _request(
        {
            "q": ticker.strip().upper(),
            "language": "en",
            "removeduplicate": "1",
        }
    )
    return _render(
        payload,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        subject=f"news about {ticker.upper()}",
        heading=f"{ticker.upper()} News — NewsData.io",
    )


def get_global_news(
    curr_date: str,
    look_back_days: int | None = None,
    limit: int | None = None,
) -> str:
    """Return broad financial and market news from NewsData.io."""
    config = get_config()
    if look_back_days is None:
        look_back_days = int(config["global_news_lookback_days"])
    if limit is None:
        limit = int(config["global_news_article_limit"])
    curr_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    start_date = (curr_dt - timedelta(days=look_back_days)).strftime("%Y-%m-%d")
    payload = _request(
        {
            "language": "en",
            "removeduplicate": "1",
        }
    )
    return _render(
        payload,
        start_date=start_date,
        end_date=curr_date,
        limit=int(limit),
        subject="global market news",
        heading="Global Market News — NewsData.io",
    )
