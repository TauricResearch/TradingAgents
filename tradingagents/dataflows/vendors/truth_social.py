"""Donald Trump's public Truth Social timeline.

Truth Social exposes a Mastodon-compatible account-status endpoint, but may
protect it with Cloudflare depending on the caller's network. This adapter uses
only that public endpoint, never attempts to bypass access controls, and returns
an explicit unavailable marker when access is denied.
"""

from __future__ import annotations

import contextlib
import html
import os
import re
from datetime import datetime

import requests

from tradingagents.dataflows.date_window import coverage_gap, in_window

_DEFAULT_API = "https://truthsocial.com/api/v1"
_TRUMP_ACCOUNT_ID = "107780257626128497"
_UA = "tradingagents/0.5 (+https://github.com/TauricResearch/TradingAgents)"


def _created_at(post: dict) -> datetime | None:
    raw = post.get("created_at")
    if not raw:
        return None
    with contextlib.suppress(ValueError, TypeError):
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    return None


def _plain_text(value: str) -> str:
    without_tags = re.sub(r"<[^>]+>", " ", value or "")
    return " ".join(html.unescape(without_tags).split())


def fetch_trump_truths(
    limit: int = 20,
    timeout: float = 10.0,
    start_date: str | None = None,
    end_date: str | None = None,
) -> str:
    """Return recent posts from Donald Trump's Truth Social account."""
    base = os.getenv("TRUTH_SOCIAL_API_BASE_URL", _DEFAULT_API).rstrip("/")
    account_id = os.getenv("TRUTH_SOCIAL_TRUMP_ACCOUNT_ID", _TRUMP_ACCOUNT_ID)
    headers = {"Accept": "application/json", "User-Agent": _UA}
    token = os.getenv("TRUTH_SOCIAL_BEARER_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        response = requests.get(
            f"{base}/accounts/{account_id}/statuses",
            params={"exclude_replies": "true", "limit": max(1, min(int(limit), 40))},
            headers=headers,
            timeout=timeout,
        )
        response.raise_for_status()
        posts = response.json()
    except (requests.RequestException, ValueError) as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        detail = f"HTTP {status}" if status else type(exc).__name__
        return f"<Truth Social unavailable: official public endpoint returned {detail}>"

    if not isinstance(posts, list):
        return "<Truth Social unavailable: unexpected response shape>"

    fetched = posts
    if start_date and end_date:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        posts = [p for p in posts if in_window(_created_at(p), start_dt, end_dt)]

    if not posts:
        if start_date and end_date:
            gap = coverage_gap(
                (_created_at(p) for p in fetched),
                start_date,
                end_date,
                "Truth Social",
                "posts from @realDonaldTrump",
            )
            if gap:
                return gap
            return f"<no @realDonaldTrump Truths within {start_date}..{end_date}>"
        return "<no recent @realDonaldTrump Truths found>"

    lines = []
    for post in posts[:limit]:
        source = post.get("reblog") if isinstance(post.get("reblog"), dict) else post
        body = _plain_text(str(source.get("content", "")))
        if len(body) > 700:
            body = body[:700] + "…"
        created = post.get("created_at", "")
        url = source.get("url") or post.get("url") or ""
        metrics = (
            f"likes={source.get('favourites_count', 0)}, "
            f"retruths={source.get('reblogs_count', 0)}, replies={source.get('replies_count', 0)}"
        )
        lines.append(f"[{created} · {metrics}] {body} {url}".strip())

    dated = [_created_at(p) for p in posts]
    oldest = min((value for value in dated if value is not None), default=None)
    coverage = f"; returned coverage starts {oldest:%Y-%m-%d %H:%M UTC}" if oldest else ""
    return f"@realDonaldTrump Truth Social: {len(lines)} recent posts{coverage}\n\n" + "\n".join(
        lines
    )
