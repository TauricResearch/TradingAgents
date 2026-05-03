"""
Defuddle integration — fetch full article content as Markdown via the hosted endpoint.

Usage:
    from tradingagents.dataflows.defuddle import deep_fetch_article
    markdown = deep_fetch_article("https://example.com/article")

Config via env var DEFUDDELL_BASE (default: "https://defuddle.md").
"""

import os
import re
import requests
from typing import Optional

DEFUDDLE_BASE = os.environ.get("DEFUDDLE_BASE", "https://defuddle.md").rstrip("/")
FETCH_TIMEOUT = int(os.environ.get("DEFUDDLE_TIMEOUT", "15"))
MAX_CONTENT_LEN = int(os.environ.get("DEFUDDLE_MAX_LEN", "100000"))  # ~100KB cap

# Block private/internal URLs to prevent SSRF
_BLOCKED_PATTERNS = [
    re.compile(r"^https?://(localhost|127\.|0\.0\.0\.0)", re.I),
    re.compile(r"^https?://10\.", re.I),
    re.compile(r"^https?://192\.168\.", re.I),
    re.compile(r"^https?://172\.(1[6-9]|2\d|3[01])\.", re.I),
    re.compile(r"^https?://169\.254\.", re.I),      # Link-local / AWS metadata
    re.compile(r"^(file|ftp|gopher|data):", re.I),    # Non-HTTP schemes
]


def _is_blocked(url: str) -> bool:
    return any(p.match(url) for p in _BLOCKED_PATTERNS)


def deep_fetch_article(url: str) -> Optional[str]:
    """
    Fetch a single article URL and return full content as Markdown
    via the hosted defuddle.md endpoint.

    Args:
        url: Full HTTP(S) URL of the article to fetch.

    Returns:
        Markdown string with YAML frontmatter (title, author, date, etc.),
        or None if fetch failed or URL is blocked.
    """
    if not url or not url.startswith(("http://", "https://")):
        return None

    if _is_blocked(url):
        return None

    try:
        resp = requests.get(
            f"{DEFUDDLE_BASE}/{url}",
            timeout=FETCH_TIMEOUT,
            headers={"Accept": "text/plain"},
        )
        resp.raise_for_status()
        content = resp.text[:MAX_CONTENT_LEN]

        # If the response is too short, defuddle may have failed to extract
        if len(content.strip()) < 50:
            return None

        return content

    except (requests.RequestException, ValueError, KeyError):
        return None


def deep_fetch_batch(urls: list[str], max_articles: int = 5) -> str:
    """
    Fetch multiple articles and return combined Markdown.
    Articles that fail or are blocked are silently skipped.

    Args:
        urls: List of article URLs to fetch.
        max_articles: Maximum number of articles to fetch (default 5).

    Returns:
        Combined Markdown from all successfully fetched articles.
    """
    results = []
    for url in urls[:max_articles]:
        content = deep_fetch_article(url)
        if content:
            results.append(content)

    if not results:
        return ""

    return "\n\n---\n\n".join(results)
