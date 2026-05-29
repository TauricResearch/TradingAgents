"""Mastodon public hashtag-timeline fetcher.

Mastodon instances expose a public hashtag timeline at
``{instance}/api/v1/timelines/tag/{tag}`` that requires no API key and no
auth. Default instance is ``mastodon.social`` (override via the
``MASTODON_INSTANCE`` env var).

Mirrors the stocktwits/reddit fetchers: short timeout, graceful
degradation on any HTTP or parse failure, and a string return type.
"""

from __future__ import annotations

import json
import logging
import os
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

_UA = "tradingagents/0.2 (+https://github.com/TauricResearch/TradingAgents)"
_TAG_RE = re.compile(r"[^A-Za-z0-9]")
_HTML_RE = re.compile(r"<[^>]+>")


def _instance() -> str:
    return os.environ.get("MASTODON_INSTANCE", "https://mastodon.social").rstrip("/")


def fetch_mastodon_posts(tag: str, limit: int = 25, timeout: float = 10.0) -> str:
    """Fetch recent public posts for hashtag ``tag`` (ticker name, symbols
    stripped) and return them as a prompt-ready plaintext block.

    Returns a placeholder string when the endpoint is unreachable, the
    tag has no posts, or the response shape is unexpected.
    """
    clean = _TAG_RE.sub("", tag)
    if not clean:
        return f"<no Mastodon posts: invalid tag '{tag}'>"
    qs = urlencode({"limit": max(1, min(limit, 40))})
    url = f"{_instance()}/api/v1/timelines/tag/{clean}?{qs}"
    req = Request(url, headers={"User-Agent": _UA, "Accept": "application/json"})
    try:
        with urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
    except (HTTPError, URLError, json.JSONDecodeError, TimeoutError) as exc:
        logger.warning("Mastodon fetch failed for #%s: %s", clean, exc)
        return f"<mastodon unavailable: {type(exc).__name__}>"

    if not isinstance(data, list) or not data:
        return f"<no Mastodon posts found for #{clean}>"

    lines = [f"Mastodon — {len(data)} recent posts tagged #{clean}:"]
    for s in data[:limit]:
        if not isinstance(s, dict):
            continue
        acct = (s.get("account") or {}).get("acct", "?")
        created = (s.get("created_at") or "")[:10] or "?"
        body = _HTML_RE.sub("", s.get("content") or "").replace("\n", " ").strip()
        if len(body) > 280:
            body = body[:280] + "…"
        favs = s.get("favourites_count", 0)
        boosts = s.get("reblogs_count", 0)
        replies = s.get("replies_count", 0)
        lines.append(f"  [{created} · @{acct} · {favs}♥ {boosts}↻ {replies}c] {body}")
    return "\n".join(lines)
