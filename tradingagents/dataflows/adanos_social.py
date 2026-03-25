import os
import re
from typing import Any

import requests


ADANOS_BASE_URL = "https://api.adanos.org"
_LETTER_TICKER_RE = re.compile(r"^[A-Z]{1,10}$")
_REDDIT_NEWS_TICKER_RE = re.compile(r"^[A-Z][A-Z0-9]{0,9}(?:\.[A-Z])?$")


def _normalize_ticker(ticker: str) -> str:
    return ticker.strip().upper().lstrip("$")


def _request_json(path: str, *, api_key: str, base_url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    response = requests.get(
        f"{base_url.rstrip('/')}{path}",
        headers={"X-API-Key": api_key, "Accept": "application/json"},
        params=params or {},
        timeout=float(os.getenv("ADANOS_TIMEOUT", "20")),
    )
    response.raise_for_status()
    return response.json()


def _iter_source_requests(ticker: str) -> list[tuple[str, str]]:
    requests_to_make: list[tuple[str, str]] = []

    if _REDDIT_NEWS_TICKER_RE.fullmatch(ticker):
        requests_to_make.extend(
            [
                ("Reddit", f"/reddit/stocks/v1/stock/{ticker}"),
                ("News", f"/news/stocks/v1/stock/{ticker}"),
            ]
        )

    if _LETTER_TICKER_RE.fullmatch(ticker):
        requests_to_make.extend(
            [
                ("X/Twitter", f"/x/stocks/v1/stock/{ticker}"),
                ("Polymarket", f"/polymarket/stocks/v1/stock/{ticker}"),
            ]
        )

    return requests_to_make


def _format_source_section(source_name: str, payload: dict[str, Any]) -> str:
    lines = [f"## {source_name}"]

    company_name = payload.get("company_name")
    if company_name:
        lines.append(f"- Company: {company_name}")

    if payload.get("buzz_score") is not None:
        lines.append(f"- Buzz score: {payload['buzz_score']}")
    if payload.get("sentiment_score") is not None:
        lines.append(f"- Sentiment score: {payload['sentiment_score']}")
    if payload.get("bullish_pct") is not None or payload.get("bearish_pct") is not None:
        lines.append(
            f"- Bullish/Bearish: {payload.get('bullish_pct', 'n/a')}% / {payload.get('bearish_pct', 'n/a')}%"
        )
    if payload.get("trend"):
        lines.append(f"- Trend: {payload['trend']}")

    for key, label in (
        ("total_mentions", "Mentions"),
        ("unique_posts", "Unique posts"),
        ("subreddit_count", "Subreddits"),
        ("source_count", "Sources"),
        ("unique_tweets", "Unique tweets"),
        ("market_count", "Active markets"),
        ("trade_count", "Trades"),
        ("total_liquidity", "Total liquidity"),
    ):
        value = payload.get(key)
        if value is not None:
            lines.append(f"- {label}: {value}")

    explanation = payload.get("explanation")
    if explanation:
        lines.append(f"- Explanation: {explanation}")

    return "\n".join(lines)


def get_social_sentiment(ticker: str, curr_date: str, look_back_days: int = 7) -> str:
    """Retrieve multi-source social sentiment from Adanos when available."""
    api_key = os.getenv("ADANOS_API_KEY")
    if not api_key:
        return (
            "Adanos social sentiment is unavailable because ADANOS_API_KEY is not set. "
            "Configure ADANOS_API_KEY to enable Reddit, X/Twitter, News, and Polymarket sentiment lookups."
        )

    normalized_ticker = _normalize_ticker(ticker)
    source_requests = _iter_source_requests(normalized_ticker)
    if not source_requests:
        return (
            f"Adanos does not currently support the exact ticker format `{ticker}` for per-symbol sentiment lookup. "
            "Exchange-qualified or numeric symbols should fall back to the framework's existing news tools."
        )

    base_url = os.getenv("ADANOS_BASE_URL", ADANOS_BASE_URL)
    days = max(1, int(look_back_days or 7))

    sections: list[str] = []
    notes: list[str] = []

    for source_name, path in source_requests:
        try:
            payload = _request_json(path, api_key=api_key, base_url=base_url, params={"days": days})
        except requests.HTTPError as exc:
            status_code = exc.response.status_code if exc.response is not None else None
            if status_code == 404:
                notes.append(f"- {source_name}: no coverage for {normalized_ticker}")
                continue
            if status_code in {401, 403}:
                return "Adanos social sentiment request failed due to invalid API credentials."
            notes.append(f"- {source_name}: request failed with HTTP {status_code}")
            continue
        except requests.RequestException as exc:
            notes.append(f"- {source_name}: request failed ({exc.__class__.__name__})")
            continue

        sections.append(_format_source_section(source_name, payload))

    if not sections:
        note_block = "\n".join(notes) if notes else "- No compatible Adanos sources were available."
        return (
            f"# {normalized_ticker} Adanos social sentiment\n\n"
            f"Analysis date: {curr_date}\n"
            f"Lookback window: {days} days\n\n"
            "No Adanos sentiment sources returned usable data.\n"
            f"{note_block}"
        )

    output = [
        f"# {normalized_ticker} Adanos social sentiment",
        "",
        f"Analysis date: {curr_date}",
        f"Lookback window: {days} days",
        "",
        *sections,
    ]
    if notes:
        output.extend(["", "## Coverage notes", *notes])

    return "\n".join(output)
