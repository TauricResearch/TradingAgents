"""
Article content extraction via the defuddle npm CLI.

Provides deep_fetch_article and deep_fetch_batch for fetching
full article text as clean Markdown from URLs. Requires the
`defuddle` npm package to be installed globally:

    npm install -g defuddle
"""

import subprocess
import json
import logging
from typing import List, Optional

logger = logging.getLogger(__name__)

DEFUDDLE_CMD = "defuddle"


def _defuddle_binary() -> Optional[str]:
    """Check if defuddle CLI is available. Returns path or None."""
    try:
        result = subprocess.run(
            ["which", DEFUDDLE_CMD], capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    # Try npx as fallback
    try:
        result = subprocess.run(
            ["npx", DEFUDDLE_CMD, "--version"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            return "npx defuddle"
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    return None


def deep_fetch_article(url: str, timeout: int = 30) -> str:
    """
    Fetch a single URL and return cleaned Markdown content.

    Args:
        url: Full HTTP(S) URL to fetch
        timeout: Subprocess timeout in seconds

    Returns:
        Article content as Markdown string, or empty string on failure
    """
    binary = _defuddle_binary()
    if binary is None:
        logger.warning("defuddle CLI not available — install with: npm install -g defuddle")
        return ""

    cmd_parts = binary.split() if binary == "npx defuddle" else [binary]
    cmd = [*cmd_parts, "parse", url, "--markdown"]

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        )
        if result.returncode == 0:
            return result.stdout.strip()
        else:
            logger.warning(f"defuddle failed for {url}: {result.stderr.strip()}")
            return ""
    except subprocess.TimeoutExpired:
        logger.warning(f"defuddle timed out for {url}")
        return ""
    except Exception as e:
        logger.warning(f"defuddle error for {url}: {e}")
        return ""


def deep_fetch_batch(
    urls: List[str], max_articles: int = 5, timeout: int = 30
) -> str:
    """
    Fetch multiple URLs and return combined Markdown content.

    Args:
        urls: List of HTTP(S) URLs to fetch
        max_articles: Maximum number of articles to fetch
        timeout: Per-article subprocess timeout in seconds

    Returns:
        Combined Markdown content separated by dividers, or empty
        string if all fetches failed
    """
    if not urls:
        return ""

    urls = urls[:max_articles]
    results = []

    for url in urls:
        content = deep_fetch_article(url, timeout=timeout)
        if content:
            results.append(content)

    if not results:
        return ""

    return "\n\n---\n\n".join(results)