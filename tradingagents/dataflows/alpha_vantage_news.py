"""Alpha Vantage news fetchers with markdown normalization and date-scoped cache."""

from __future__ import annotations

import json
from typing import Any

from .alpha_vantage_common import _make_api_request, format_datetime_for_api
from .cache_utils import cache_text


def _format_score(value: Any) -> str:
    try:
        return f"{float(value):.3f}"
    except (TypeError, ValueError):
        return str(value) if value is not None else ""


def _format_ticker_sentiment(items: list[dict[str, Any]] | None) -> str:
    if not items:
        return ""
    parts = []
    for item in items[:8]:
        ticker = item.get("ticker") or item.get("symbol") or "unknown"
        label = item.get("ticker_sentiment_label") or item.get("relevance_score") or ""
        score = item.get("ticker_sentiment_score")
        rendered = ticker
        if label:
            rendered += f" {label}"
        if score is not None:
            rendered += f" ({_format_score(score)})"
        parts.append(rendered)
    return "; ".join(parts)


def _format_news_sentiment_payload(payload: dict[str, Any], heading: str) -> str:
    feed = payload.get("feed") if isinstance(payload, dict) else None
    if not isinstance(feed, list) or not feed:
        return f"No Alpha Vantage news found for {heading}"

    lines = [f"## Alpha Vantage News Sentiment: {heading}", ""]
    for article in feed:
        if not isinstance(article, dict):
            continue
        title = article.get("title") or "No title"
        source = article.get("source") or "Unknown"
        published = article.get("time_published") or "unknown date"
        summary = article.get("summary") or ""
        url = article.get("url") or ""
        overall_label = article.get("overall_sentiment_label")
        overall_score = article.get("overall_sentiment_score")
        ticker_sentiment = _format_ticker_sentiment(article.get("ticker_sentiment"))

        lines.append(f"### {title} (source: {source})")
        lines.append(f"Published: {published}")
        if overall_label or overall_score is not None:
            label_part = f" {overall_label}" if overall_label else ""
            score_part = f" ({_format_score(overall_score)})" if overall_score is not None else ""
            lines.append(f"Overall sentiment:{label_part}{score_part}".strip())
        if ticker_sentiment:
            lines.append(f"Ticker sentiment: {ticker_sentiment}")
        if summary:
            lines.append(summary)
        if url:
            lines.append(f"Link: {url}")
        lines.append("")

    return "\n".join(lines).strip() or f"No Alpha Vantage news found for {heading}"


def _normalize_news_response(response: dict[str, Any] | str, heading: str) -> str:
    if isinstance(response, dict):
        return _format_news_sentiment_payload(response, heading)
    if not isinstance(response, str):
        return str(response)
    try:
        parsed = json.loads(response)
    except json.JSONDecodeError:
        return response
    return _format_news_sentiment_payload(parsed, heading)


def get_news(ticker, start_date, end_date) -> str:
    """Return ticker-specific market news & sentiment as markdown."""

    def fetch() -> str:
        params = {
            "tickers": ticker,
            "time_from": format_datetime_for_api(start_date),
            "time_to": format_datetime_for_api(end_date),
        }
        return _normalize_news_response(
            _make_api_request("NEWS_SENTIMENT", params),
            f"{ticker}, from {start_date} to {end_date}",
        )

    return cache_text("alpha_vantage_news", (str(ticker), str(start_date), str(end_date)), fetch)


def get_global_news(curr_date, look_back_days: int = 7, limit: int = 50) -> str:
    """Return broad market news & sentiment as markdown."""
    from datetime import datetime, timedelta

    curr_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    start_dt = curr_dt - timedelta(days=look_back_days)
    start_date = start_dt.strftime("%Y-%m-%d")

    def fetch() -> str:
        params = {
            "topics": "financial_markets,economy_macro,economy_monetary",
            "time_from": format_datetime_for_api(start_date),
            "time_to": format_datetime_for_api(curr_date),
            "limit": str(limit),
        }
        return _normalize_news_response(
            _make_api_request("NEWS_SENTIMENT", params),
            f"global markets, from {start_date} to {curr_date}",
        )

    return cache_text(
        "alpha_vantage_global_news",
        (str(curr_date), str(look_back_days), str(limit)),
        fetch,
    )


def get_insider_transactions(symbol: str) -> dict[str, str] | str:
    """Returns latest and historical insider transactions by key stakeholders."""
    return _make_api_request("INSIDER_TRANSACTIONS", {"symbol": symbol})
