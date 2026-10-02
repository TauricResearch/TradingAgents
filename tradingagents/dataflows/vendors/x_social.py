"""Live ticker conversation from X's official recent-search API.

The endpoint only covers the most recent seven days and requires an X developer
Bearer Token. Historical windows outside that coverage are reported as
unavailable rather than as an absence of discussion, preserving point-in-time
integrity in backtests.
"""

from __future__ import annotations

import contextlib
import os
from datetime import datetime, timedelta, timezone

import requests

from tradingagents.dataflows.date_window import coverage_gap, in_window

_API = "https://api.x.com/2/tweets/search/recent"
_RECENT_WINDOW = timedelta(days=7)
_UA = "tradingagents/0.5 (+https://github.com/TauricResearch/TradingAgents)"


def _created_at(post: dict) -> datetime | None:
    raw = post.get("created_at")
    if not raw:
        return None
    with contextlib.suppress(ValueError, TypeError):
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    return None


def _query_for(ticker: str) -> str:
    """Build a conservative X query without treating ticker punctuation as syntax."""
    symbol = ticker.strip().upper()
    if symbol.isalnum():
        terms = "($" + symbol + " OR " + symbol + ")"
    else:
        safe = symbol.replace('"', "")
        terms = f'"{safe}"'
    return f"{terms} lang:en -is:retweet"


def fetch_x_posts(
    ticker: str,
    limit: int = 30,
    timeout: float = 10.0,
    start_date: str | None = None,
    end_date: str | None = None,
    bearer_token: str | None = None,
) -> str:
    """Return recent X posts about the ticker as prompt-ready plaintext.

    X bills reads per returned post, so the default deliberately caps each run
    at 30 posts. The token is read from X_BEARER_TOKEN when not supplied.
    """
    token = bearer_token or os.getenv("X_BEARER_TOKEN")
    if not token:
        return "<X unavailable: X_BEARER_TOKEN is not configured>"

    now = datetime.now(timezone.utc)
    recent_start = now - _RECENT_WINDOW
    if start_date and end_date:
        requested_end = datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        if requested_end.date() < recent_start.date():
            return (
                f"<X unavailable for {start_date}..{end_date}: official recent search "
                "only covers the last 7 days, so this is not an absence of discussion>"
            )

    params: dict[str, str | int] = {
        "query": _query_for(ticker),
        "max_results": max(10, min(int(limit), 100)),
        "tweet.fields": "created_at,author_id,lang,public_metrics",
        "expansions": "author_id",
        "user.fields": "username,name,verified",
    }
    if start_date:
        requested_start = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        effective_start = max(requested_start, recent_start)
        params["start_time"] = effective_start.strftime("%Y-%m-%dT%H:%M:%SZ")
    if end_date:
        requested_exclusive_end = datetime.strptime(end_date, "%Y-%m-%d").replace(
            tzinfo=timezone.utc
        ) + timedelta(days=1)
        effective_end = min(requested_exclusive_end, now - timedelta(seconds=10))
        if effective_end > recent_start:
            params["end_time"] = effective_end.strftime("%Y-%m-%dT%H:%M:%SZ")

    try:
        response = requests.get(
            _API,
            params=params,
            headers={"Authorization": f"Bearer {token}", "User-Agent": _UA},
            timeout=timeout,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        detail = f"HTTP {status}" if status else type(exc).__name__
        return f"<X unavailable: {detail}>"

    posts = payload.get("data", []) if isinstance(payload, dict) else []
    if not isinstance(posts, list):
        return "<X unavailable: unexpected response shape>"

    if start_date and end_date:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        posts = [p for p in posts if in_window(_created_at(p), start_dt, end_dt)]

    if not posts:
        if start_date and end_date:
            gap = coverage_gap(
                [recent_start], start_date, end_date, "X", f"discussion of {ticker.upper()}"
            )
            if gap:
                return gap
            return f"<no X posts found about {ticker.upper()} within {start_date}..{end_date}>"
        return f"<no X posts found about {ticker.upper()}>"

    includes = payload.get("includes", {}) if isinstance(payload, dict) else {}
    users = includes.get("users", []) if isinstance(includes, dict) else []
    usernames = {
        str(user.get("id")): user.get("username", "?") for user in users if isinstance(user, dict)
    }

    lines = []
    for post in posts[:limit]:
        text = " ".join(str(post.get("text", "")).split())
        if len(text) > 500:
            text = text[:500] + "…"
        metrics = post.get("public_metrics") or {}
        author = usernames.get(str(post.get("author_id")), "?")
        created = post.get("created_at", "")
        engagement = (
            f"likes={metrics.get('like_count', 0)}, reposts={metrics.get('retweet_count', 0)}, "
            f"replies={metrics.get('reply_count', 0)}, quotes={metrics.get('quote_count', 0)}"
        )
        lines.append(f"[{created} · @{author} · {engagement}] {text}")

    return f"X recent search: {len(lines)} posts about {ticker.upper()}\n\n" + "\n".join(lines)
