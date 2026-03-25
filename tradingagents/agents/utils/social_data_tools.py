from datetime import date, datetime
import os
from typing import Annotated

import requests
from langchain_core.tools import tool


ADANOS_API_BASE_URL = os.getenv("ADANOS_API_BASE_URL", "https://api.adanos.org").rstrip("/")
RECENT_WINDOW_LOOKBACK_DAYS = 4
RECENT_WINDOW_FORWARD_DAYS = 1


def has_social_sentiment_support() -> bool:
    """Return whether the optional Adanos-backed social sentiment tool is available."""
    return bool(os.getenv("ADANOS_API_KEY"))


def _supports_recent_social_window(requested_date: date, today: date) -> bool:
    window_delta_days = (today - requested_date).days
    return -RECENT_WINDOW_FORWARD_DAYS <= window_delta_days <= RECENT_WINDOW_LOOKBACK_DAYS


def _safe_number(value, digits: int = 1):
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return round(number, digits)


def _safe_int(value):
    if value is None:
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _format_percent(value) -> str:
    if value is None:
        return "n/a"
    return f"{value:.1f}%"


def _format_score(value) -> str:
    if value is None:
        return "n/a"
    return f"{value:.1f}/100"


def _format_currency(value) -> str:
    if value is None:
        return "n/a"
    if value >= 1_000_000_000:
        return f"${value / 1_000_000_000:.1f}B"
    if value >= 1_000_000:
        return f"${value / 1_000_000:.1f}M"
    if value >= 1_000:
        return f"${value / 1_000:.1f}K"
    return f"${value:.0f}"


def _normalize_compare_row(payload: dict) -> dict:
    stocks = payload.get("stocks") if isinstance(payload, dict) else None
    if not isinstance(stocks, list) or not stocks or not isinstance(stocks[0], dict):
        return {}
    return stocks[0]


def _alignment_label(bullish_values: list[float]) -> str:
    if len(bullish_values) < 2:
        return "single-source"

    spread = max(bullish_values) - min(bullish_values)
    average = sum(bullish_values) / len(bullish_values)

    if spread <= 10:
        if average >= 55:
            return "aligned bullish"
        if average <= 45:
            return "aligned bearish"
        return "aligned neutral"
    if spread <= 25:
        return "mixed"
    return "divergent"


def _fetch_compare(source: str, ticker: str, look_back_days: int, api_key: str) -> dict:
    response = requests.get(
        f"{ADANOS_API_BASE_URL}/{source}/stocks/v1/compare",
        params={"tickers": ticker, "days": look_back_days},
        headers={"X-API-Key": api_key},
        timeout=20,
    )
    response.raise_for_status()
    return _normalize_compare_row(response.json())


@tool
def get_social_sentiment(
    ticker: Annotated[str, "Ticker symbol"],
    curr_date: Annotated[str, "Current trade date in yyyy-mm-dd format"],
    look_back_days: Annotated[int, "Rolling lookback window in days"] = 7,
) -> str:
    """
    Retrieve a structured social sentiment snapshot for a stock across Reddit, X/Twitter, and Polymarket.

    This tool is intended for current/live workflows. Historical trade dates are not supported because
    the upstream sentiment API exposes rolling windows ending today rather than point-in-time snapshots.
    """
    api_key = os.getenv("ADANOS_API_KEY")
    if not api_key:
        return "Social sentiment tool unavailable: ADANOS_API_KEY is not configured."

    try:
        requested_date = datetime.strptime(curr_date, "%Y-%m-%d").date()
    except ValueError:
        return f"Social sentiment tool unavailable: invalid curr_date '{curr_date}', expected yyyy-mm-dd."

    today = date.today()
    if not _supports_recent_social_window(requested_date, today):
        return (
            f"Social sentiment snapshot unavailable for historical trade date {curr_date}. "
            "This tool only supports current rolling windows ending near today, so use company/news context instead for historical runs."
        )

    normalized_ticker = ticker.strip().upper().lstrip("$")
    look_back_days = max(1, min(int(look_back_days), 90))

    source_snapshots = {}
    source_errors = {}

    for source in ("reddit", "x", "polymarket"):
        try:
            row = _fetch_compare(source, normalized_ticker, look_back_days, api_key)
        except requests.RequestException as exc:
            source_errors[source] = str(exc)
            continue

        if source == "polymarket":
            activity = _safe_int(row.get("trade_count"))
            source_snapshots[source] = {
                "label": "Polymarket",
                "activity_label": "trades",
                "activity_value": activity,
                "buzz_score": _safe_number(row.get("buzz_score")),
                "bullish_pct": _safe_number(row.get("bullish_pct")),
                "trend": row.get("trend") or "n/a",
                "extra": (
                    f"markets: {_safe_int(row.get('market_count')) or 0}, "
                    f"liquidity: {_format_currency(_safe_number(row.get('total_liquidity')))}"
                ),
            }
        elif source == "reddit":
            activity = _safe_int(row.get("mentions"))
            source_snapshots[source] = {
                "label": "Reddit",
                "activity_label": "mentions",
                "activity_value": activity,
                "buzz_score": _safe_number(row.get("buzz_score")),
                "bullish_pct": _safe_number(row.get("bullish_pct")),
                "trend": row.get("trend") or "n/a",
                "extra": (
                    f"subreddits: {_safe_int(row.get('subreddit_count')) or 0}, "
                    f"upvotes: {_safe_int(row.get('total_upvotes')) or 0}"
                ),
            }
        else:
            activity = _safe_int(row.get("mentions"))
            source_snapshots[source] = {
                "label": "X/Twitter",
                "activity_label": "mentions",
                "activity_value": activity,
                "buzz_score": _safe_number(row.get("buzz_score")),
                "bullish_pct": _safe_number(row.get("bullish_pct")),
                "trend": row.get("trend") or "n/a",
                "extra": (
                    f"unique tweets: {_safe_int(row.get('unique_tweets')) or 0}, "
                    f"likes: {_safe_int(row.get('total_upvotes')) or 0}"
                ),
            }

    if not source_snapshots:
        if source_errors:
            details = "; ".join(f"{source}: {error}" for source, error in source_errors.items())
            return f"Unable to retrieve social sentiment for {normalized_ticker}: {details}"
        return f"No social sentiment data available for {normalized_ticker}."

    available_buzz = [
        snapshot["buzz_score"]
        for snapshot in source_snapshots.values()
        if snapshot["buzz_score"] is not None
    ]
    available_bullish = [
        snapshot["bullish_pct"]
        for snapshot in source_snapshots.values()
        if snapshot["bullish_pct"] is not None
    ]

    average_buzz = round(sum(available_buzz) / len(available_buzz), 1) if available_buzz else None
    average_bullish = (
        round(sum(available_bullish) / len(available_bullish), 1) if available_bullish else None
    )
    alignment = _alignment_label(available_bullish)

    lines = [
        f"## Social sentiment for {normalized_ticker} (last {look_back_days} days)",
        "",
        f"- Average buzz: {_format_score(average_buzz)}",
        f"- Average bullish: {_format_percent(average_bullish)}",
        f"- Source alignment: {alignment}",
        "",
    ]

    for source in ("reddit", "x", "polymarket"):
        snapshot = source_snapshots.get(source)
        if snapshot is None:
            if source in source_errors:
                lines.append(f"### {source.title()}")
                lines.append(f"- unavailable: {source_errors[source]}")
                lines.append("")
            continue

        lines.extend(
            [
                f"### {snapshot['label']}",
                f"- {snapshot['activity_label']}: {snapshot['activity_value'] or 0}",
                f"- buzz: {_format_score(snapshot['buzz_score'])}",
                f"- bullish: {_format_percent(snapshot['bullish_pct'])}",
                f"- trend: {snapshot['trend']}",
                f"- {snapshot['extra']}",
                "",
            ]
        )

    return "\n".join(lines).strip()
