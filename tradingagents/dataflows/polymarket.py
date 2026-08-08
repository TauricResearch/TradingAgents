"""Polymarket prediction-market vendor.

Surfaces live, market-implied probabilities for forward-looking events (Fed
decisions, recession, elections, geopolitics, crypto) to the news analyst, as a
complement to news (what happened) and FRED macro data (where things stand):
what the crowd actually prices to happen next.

Uses Polymarket's public Gamma API (https://gamma-api.polymarket.com) — no key,
no auth. Each market's ``outcomePrices`` are the implied probabilities of its
outcomes (a "Yes" at 0.76 means the market prices a 76% chance).
"""
import json
import logging
import math
from datetime import datetime, timezone

import requests

from tradingagents.dataflows.errors import (
    ProviderResponseError,
    ProviderTransientError,
)
from tradingagents.logging_utils import safe_exception_type

logger = logging.getLogger(__name__)

GAMMA_BASE = "https://gamma-api.polymarket.com"

# Network timeout (seconds), consistent with the other vendors.
REQUEST_TIMEOUT = 30

# Default number of markets to return, ranked by traded volume.
DEFAULT_LIMIT = 6


def _request(path: str, params: dict) -> dict:
    response = requests.get(
        f"{GAMMA_BASE}/{path}", params=params, timeout=REQUEST_TIMEOUT
    )
    response.raise_for_status()
    return response.json()


def _parse_json_list(value) -> list:
    """Gamma encodes ``outcomes``/``outcomePrices`` as JSON-string arrays."""
    if isinstance(value, list):
        return value
    try:
        parsed = json.loads(value)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ProviderResponseError("Polymarket market schema was invalid") from exc
    if not isinstance(parsed, list):
        raise ProviderResponseError("Polymarket market schema was invalid")
    return parsed


def _is_forward_looking(market: dict, now: datetime) -> bool:
    """Keep only open markets that resolve in the future.

    ``closed`` is the reliable resolved flag (``active`` stays True even for
    settled markets), and a past ``endDate`` means the event already resolved —
    either way it is not a forward-looking signal.
    """
    if market.get("closed"):
        return False
    end_date = datetime.fromisoformat(market["endDate"].replace("Z", "+00:00"))
    return end_date >= now


def _validated_market(market: dict) -> dict:
    """Reject a nonempty market item that cannot produce trustworthy odds."""
    if (
        not isinstance(market.get("question"), str)
        or not market["question"].strip()
        or not isinstance(market.get("closed"), bool)
        or not isinstance(market.get("endDate"), str)
    ):
        raise ProviderResponseError("Polymarket market schema was invalid")
    try:
        end_date = datetime.fromisoformat(
            market["endDate"].replace("Z", "+00:00")
        )
    except ValueError as exc:
        raise ProviderResponseError("Polymarket market schema was invalid") from exc
    if end_date.tzinfo is None or end_date.utcoffset() is None:
        raise ProviderResponseError("Polymarket market schema was invalid")

    outcomes = _parse_json_list(market.get("outcomes"))
    prices = _parse_json_list(market.get("outcomePrices"))
    try:
        probabilities = [float(value) for value in prices]
    except (TypeError, ValueError) as exc:
        raise ProviderResponseError("Polymarket market schema was invalid") from exc
    if (
        not outcomes
        or len(outcomes) != len(probabilities)
        or any(not isinstance(value, str) or not value.strip() for value in outcomes)
        or any(not math.isfinite(value) or not 0 <= value <= 1 for value in probabilities)
    ):
        raise ProviderResponseError("Polymarket market schema was invalid")

    volume = market.get("volumeNum")
    weekly_change = market.get("oneWeekPriceChange")
    if (
        isinstance(volume, bool)
        or not isinstance(volume, (int, float))
        or not math.isfinite(float(volume))
        or volume < 0
        or weekly_change is not None
        and (
            isinstance(weekly_change, bool)
            or not isinstance(weekly_change, (int, float))
            or not math.isfinite(float(weekly_change))
        )
    ):
        raise ProviderResponseError("Polymarket market schema was invalid")
    return market


def _search_markets(topic: str, limit: int) -> list[dict]:
    """Fetch one valid search envelope, preserving failure versus empty."""
    try:
        data = _request(
            "public-search", {"q": topic, "limit_per_type": max(limit, 20)}
        )
    except (requests.ConnectionError, requests.Timeout) as exc:
        raise ProviderTransientError("Polymarket request did not complete") from exc
    except requests.RequestException as exc:
        raise ProviderResponseError("Polymarket response was not usable") from exc

    if (
        not isinstance(data, dict)
        or "events" not in data
        or not isinstance(data["events"], list)
        or any(not isinstance(event, dict) for event in data["events"])
    ):
        raise ProviderResponseError("Polymarket response schema was invalid")

    markets: list[dict] = []
    for event in data["events"]:
        event_markets = event.get("markets")
        if (
            not isinstance(event_markets, list)
            or any(not isinstance(market, dict) for market in event_markets)
        ):
            raise ProviderResponseError("Polymarket response schema was invalid")
        markets.extend(_validated_market(market) for market in event_markets)
    return markets


def iter_forward_markets(topic: str, limit: int = 20) -> list[dict]:
    """Return structured, volume-sorted forward-looking markets for a topic."""
    now = datetime.now(timezone.utc)
    candidates = [
        market
        for market in _search_markets(topic, limit)
        if _is_forward_looking(market, now)
    ]
    candidates.sort(key=lambda market: market.get("volumeNum") or 0, reverse=True)
    return candidates[:limit]


def get_prediction_markets(topic: str, limit: int | None = None) -> str:
    """Return live prediction-market probabilities for an event topic.

    Args:
        topic: Event keyword(s), e.g. "Fed rate cut", "recession 2026",
            "US election", or a sector/company event.
        limit: Max markets to return (ranked by traded volume); ``None`` uses
            DEFAULT_LIMIT.

    Returns:
        A markdown report of the most-traded open markets matching the topic,
        each with its implied probability, traded volume, resolution date, and
        recent (1-week) move.
    """
    if limit is None:
        limit = DEFAULT_LIMIT

    try:
        markets = _search_markets(topic, limit)
    except (ProviderTransientError, ProviderResponseError) as exc:
        logger.warning("Polymarket search failed (%s)", safe_exception_type(exc))
        return (
            "Polymarket data is currently unavailable because its request failed. "
            f"Proceed without prediction-market signal for '{topic}'."
        )

    now = datetime.now(timezone.utc)
    candidates = [
        m
        for m in markets
        if _is_forward_looking(m, now)
    ]
    candidates.sort(key=lambda m: m.get("volumeNum") or 0, reverse=True)

    header = (
        f'## Polymarket prediction markets: "{topic}"\n'
        f"Live, market-implied probabilities (higher traded volume = deeper, "
        f"more reliable). A probability is the crowd's priced odds of the event, "
        f"not a forecast you should take as certain.\n\n"
    )

    if not candidates:
        return header + (
            f"No open prediction markets matched '{topic}'. Polymarket coverage "
            f"is concentrated in macro, political, geopolitical, and crypto "
            f"events; a specific equity may have none."
        )

    lines = []
    for m in candidates[:limit]:
        prices = _parse_json_list(m.get("outcomePrices"))
        outcomes = _parse_json_list(m.get("outcomes"))
        prob = float(prices[0])
        label = outcomes[0]
        volume = m.get("volumeNum") or 0
        end_date = (m.get("endDate") or "")[:10]
        wk = m.get("oneWeekPriceChange")
        wk_str = (
            f", 1-week {wk * 100:+.1f}pp"
            if isinstance(wk, (int, float)) and wk
            else ""
        )
        lines.append(
            f"- **{m.get('question')}** — {label} {prob:.0%} "
            f"(${volume:,.0f} volume, resolves {end_date}{wk_str})"
        )

    return header + "\n".join(lines) + "\n"
