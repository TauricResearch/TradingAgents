"""Bluesky public post-search fetcher.

Bluesky's AT Protocol exposes a keyword post search at
``public.api.bsky.app/xrpc/app.bsky.feed.searchPosts`` that requires no
API key and no auth. Each post carries text, author handle, timestamp,
and engagement counts (likes / reposts / replies).

Mirrors the stocktwits/reddit fetchers: short timeout, graceful
degradation on any HTTP or parse failure, and a string return type so
the calling agent gets a uniform interface regardless of outcome.

Note: some network edges/CDNs geo-block ``searchPosts``; on failure the
function returns a placeholder string rather than raising.
"""

from __future__ import annotations

import json
import logging
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

_API = "https://public.api.bsky.app/xrpc/app.bsky.feed.searchPosts?{qs}"
_UA = "tradingagents/0.2 (+https://github.com/TauricResearch/TradingAgents)"


def fetch_bluesky_posts(query: str, limit: int = 25, timeout: float = 10.0) -> str:
    """Search Bluesky for recent posts matching ``query`` (e.g. ``$NVDA`` or
    ``Bitcoin``) and return them as a prompt-ready plaintext block.

    Returns a placeholder string when the endpoint is unreachable, the
    query has no results, or the response shape is unexpected.
    """
    qs = urlencode({"q": query, "limit": max(1, min(limit, 100)), "sort": "latest"})
    req = Request(_API.format(qs=qs), headers={"User-Agent": _UA, "Accept": "application/json"})
    try:
        with urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
    except (HTTPError, URLError, json.JSONDecodeError, TimeoutError) as exc:
        logger.warning("Bluesky fetch failed for %s: %s", query, exc)
        return f"<bluesky unavailable: {type(exc).__name__}>"

    posts = data.get("posts", []) if isinstance(data, dict) else []
    if not posts:
        return f"<no Bluesky posts found for '{query}'>"

    lines = [f"Bluesky — {len(posts)} recent posts matching '{query}':"]
    for p in posts[:limit]:
        author = (p.get("author") or {}).get("handle", "?")
        record = p.get("record") or {}
        created = record.get("createdAt", "")[:10] or "?"
        text = (record.get("text") or "").replace("\n", " ").strip()
        if len(text) > 280:
            text = text[:280] + "…"
        likes = p.get("likeCount", 0)
        reposts = p.get("repostCount", 0)
        replies = p.get("replyCount", 0)
        lines.append(f"  [{created} · @{author} · {likes}♥ {reposts}↻ {replies}c] {text}")
    return "\n".join(lines)
