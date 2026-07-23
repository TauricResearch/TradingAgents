"""Newsflash deduplicated news-event vendor.

Fetches news as an *event graph* rather than raw articles: Newsflash
(https://newsflash.sh) crawls many outlets, deduplicates coverage of one
happening into a single event, and attaches a ``corroboration`` count (distinct
outlets) plus a ``confidence`` score (``min(1, sources/3)``). That makes it a
fake-news/rumor gate for the news analyst: a single-source item arrives at
confidence 0.33 and is flagged as unconfirmed, while >= 0.67 means two or more
independent outlets corroborate the story.

Keyless access works out of the box (test tier, ~50 requests/day, 24-hour
lookback). An optional free API key read from ``NEWSFLASH_API_KEY`` raises the
rate limit and history depth (up to the full multi-year archive for backtests).
History depth is tier-gated server-side; when a requested window is clamped the
response discloses it in a ``window`` note, which is surfaced in the report so
a backtest never silently mistakes "outside my tier's window" for "no news".

Date filtering (``from``/``to``) is applied server-side, so a historical
``end_date`` never leaks future events into a backtest window.
"""
import logging
import os
from datetime import datetime, timedelta

import requests

from .config import get_config
from .errors import VendorRateLimitError

logger = logging.getLogger(__name__)

NEWSFLASH_BASE = "https://newsflash.sh"

# Network timeout (seconds), consistent with the other vendors.
REQUEST_TIMEOUT = 30

# Categories understood by the API's ``category`` filter (informational; the
# vendor queries across all of them and lets corroboration do the ranking).
CATEGORIES = (
    "crypto", "tradfi", "business", "tech", "politics",
    "world", "science", "health", "energy", "sports",
)

# Events corroborated by at least this many outlets (confidence >= 0.67) are
# labeled confirmed; below it they are flagged as single-source/unconfirmed.
CONFIRMED_CONFIDENCE = 0.66


class NewsflashRateLimitError(VendorRateLimitError):
    """Raised when the Newsflash daily request limit is exceeded.

    A VendorRateLimitError, so the routing layer skips to the next configured
    vendor instead of aborting the run.
    """


def _request(params: dict) -> dict:
    """GET /api/events, surfacing rate limits and API error bodies clearly.

    No key is required (keyless test tier); when ``NEWSFLASH_API_KEY`` is set it
    is sent as a bearer token to unlock higher limits and deeper history.
    """
    headers = {}
    api_key = os.getenv("NEWSFLASH_API_KEY")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    response = requests.get(
        f"{NEWSFLASH_BASE}/api/events",
        params=params,
        headers=headers,
        timeout=REQUEST_TIMEOUT,
    )

    # The API reports problems as JSON {"error": ..., "hint": ...}; keep the
    # body's message when we have one, it is more actionable than the status.
    if response.status_code >= 400:
        try:
            detail = response.json().get("error", response.text)
        except ValueError:
            detail = response.text
        if response.status_code == 429:
            raise NewsflashRateLimitError(f"Newsflash rate limit exceeded: {detail}")
        raise ValueError(f"Newsflash request failed ({response.status_code}): {detail}")

    return response.json()


def _search_events(params: dict) -> dict:
    """Query events, preferring semantic (meaning-based) search for keywords.

    ``semantic=1`` matches by embedding similarity, so a ticker or topic finds
    events that never contain the literal string (e.g. "AAPL" -> Apple
    stories). Deployments without embeddings answer 503 for semantic queries;
    degrade to the plain keyword match rather than failing the call.
    """
    if not params.get("q"):
        return _request(params)
    try:
        return _request({**params, "semantic": "1"})
    except ValueError as e:
        if "503" not in str(e):
            raise
        logger.warning("Newsflash semantic search unavailable; using keyword match: %s", e)
        return _request(params)


def _to_bound(end_date: str) -> str:
    """Upper window bound: the whole of ``end_date``, nothing after it.

    The API parses a bare ``yyyy-mm-dd`` as midnight UTC, which would silently
    drop the end day itself. Pin the bound to the day's last instant so the
    window is inclusive of ``end_date`` (matching the other news vendors'
    convention, #1126) while remaining look-ahead safe for backtests.
    """
    return f"{end_date}T23:59:59.999Z"


def _window_note(payload: dict) -> str:
    """Render the API's history-clamp disclosure, if any.

    Present whenever the tier window tightened the requested ``from`` bound —
    without it a keyless backtest would read "no news" where the truth is
    "outside the 24-hour test-tier window".
    """
    window = payload.get("window") or {}
    note = window.get("note")
    if not note:
        return ""
    clamped_from = (window.get("from") or "")[:10]
    scope = f" to {clamped_from} onward" if clamped_from else ""
    return f"\n_Note: history window clamped{scope} — {note}_\n"


def _format_events(payload: dict, empty_message: str) -> str:
    """Render events as markdown with per-event corroboration and confidence."""
    events = payload.get("events") or []
    if not events:
        return empty_message + _window_note(payload)

    lines = []
    for event in events:
        confidence = event.get("confidence") or 0.0
        corroboration = event.get("corroboration") or 0
        sources = ", ".join(event.get("sources") or [])
        status = "confirmed" if confidence >= CONFIRMED_CONFIDENCE else "unconfirmed"
        date = (event.get("last_seen_at") or "")[:10]
        lines.append(
            f"### {event.get('canonical_title')} "
            f"({status}, confidence {confidence:.2f}, "
            f"{corroboration} source{'s' if corroboration != 1 else ''}: {sources})"
        )
        if date:
            lines.append(f"Date: {date}")
        summary = event.get("summary")
        if summary:
            lines.append(summary)
        lines.append("")

    return "\n".join(lines) + _window_note(payload)


def _report_header(title: str) -> str:
    return (
        f"## {title}\n"
        f"Deduplicated news events from Newsflash: each item is one happening with a "
        f"corroboration count and a confidence score (min(1, sources/3)). Treat events "
        f"below confidence {CONFIRMED_CONFIDENCE} as single-source and unconfirmed — "
        f"do not trade on them as established fact.\n\n"
    )


def get_news(ticker: str, start_date: str, end_date: str) -> str:
    """Retrieve deduplicated news events for a ticker/topic from Newsflash.

    Args:
        ticker: Ticker symbol or topic keyword(s); matched semantically, so a
            symbol also finds company coverage that never spells it out.
        start_date: Start date in yyyy-mm-dd format.
        end_date: End date in yyyy-mm-dd format; applied server-side, so a
            historical window never leaks future events (look-ahead safe).

    Returns:
        A markdown report of matching events, each with its corroboration
        count, confidence score, and contributing outlets.
    """
    article_limit = get_config()["news_article_limit"]

    payload = _search_events({
        "q": ticker,
        "from": start_date,
        "to": _to_bound(end_date),
        "limit": str(article_limit),
    })

    return _report_header(
        f"{ticker} News (Newsflash), from {start_date} to {end_date}:"
    ) + _format_events(
        payload,
        f"No news events found for {ticker} between {start_date} and {end_date}.",
    )


def get_global_news(
    curr_date: str,
    look_back_days: int | None = None,
    limit: int | None = None,
) -> str:
    """Retrieve global/macro news events from Newsflash.

    Args:
        curr_date: Current date in yyyy-mm-dd format; the end of the window
            (applied server-side, look-ahead safe).
        look_back_days: Number of days to look back. ``None`` falls back to
            ``global_news_lookback_days`` from the active config.
        limit: Maximum number of events to return. ``None`` falls back to
            ``global_news_article_limit`` from the active config.

    Returns:
        A markdown report of the latest events across all categories (crypto,
        tradfi, business, tech, politics, world, science, health, energy,
        sports), each with its corroboration count and confidence score.
    """
    config = get_config()
    if look_back_days is None:
        look_back_days = config["global_news_lookback_days"]
    if limit is None:
        limit = config["global_news_article_limit"]

    curr_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    start_date = (curr_dt - timedelta(days=look_back_days)).strftime("%Y-%m-%d")

    payload = _search_events({
        "from": start_date,
        "to": _to_bound(curr_date),
        "limit": str(limit),
    })

    return _report_header(
        f"Global News (Newsflash), from {start_date} to {curr_date}:"
    ) + _format_events(
        payload,
        f"No global news events found between {start_date} and {curr_date}.",
    )
