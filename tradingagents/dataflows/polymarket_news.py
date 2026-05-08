"""Exa-powered event news search for Polymarket research.

Phase A uses Exa's neural search API to gather context for prediction market
questions. Returns clean text from authoritative sources, which the LLM
agents reason over.

Low-confidence path: when fewer than MIN_SOURCES_FOR_CONFIDENCE results come
back (network failure, rate limit, or genuinely sparse coverage), this module
returns an empty list. The caller in trading_graph excludes the market from
the recommendation set rather than letting agents reason on thin context.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from tradingagents.agents.utils.sanitize import sanitize_news_text

logger = logging.getLogger(__name__)

EXA_BASE = "https://api.exa.ai"
DEFAULT_TIMEOUT = 15.0
MIN_SOURCES_FOR_CONFIDENCE = 3


class ExaAPIError(Exception):
    """Raised on configuration errors. Network/rate-limit errors degrade to empty."""


def _get_api_key() -> str:
    key = os.environ.get("EXA_API_KEY")
    if not key:
        raise ExaAPIError("EXA_API_KEY environment variable is not set")
    return key


def search_event_news(question: str, limit: int = 10) -> list[dict[str, Any]]:
    """Search Exa for news/context related to a prediction market question.

    Returns a list of articles. Each article is normalised to:
        {"title": str, "url": str, "published_date": str | None, "text": str}

    Returns an empty list when:
    - Exa returns fewer than MIN_SOURCES_FOR_CONFIDENCE results
    - Exa API returns an error (logged, not raised)
    - Network timeout (logged, not raised)

    Empty list signals "low-confidence", the caller should exclude the market
    from the recommendation set this cycle.

    Raises ExaAPIError only when the API key is missing (configuration error,
    not a runtime data condition).
    """
    api_key = _get_api_key()

    payload = {
        "query": question,
        "numResults": limit,
        "useAutoprompt": True,
        "contents": {"text": True},
    }
    headers = {"x-api-key": api_key, "Content-Type": "application/json"}

    try:
        resp = httpx.post(
            f"{EXA_BASE}/search",
            json=payload,
            headers=headers,
            timeout=DEFAULT_TIMEOUT,
        )
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        logger.warning(
            "Exa /search returned %s, treating as low-confidence", e.response.status_code
        )
        return []
    except httpx.RequestError as e:
        logger.warning("Exa /search request failed (%s), treating as low-confidence", e)
        return []

    raw = resp.json()
    results = raw.get("results", []) if isinstance(raw, dict) else []

    if len(results) < MIN_SOURCES_FOR_CONFIDENCE:
        logger.info(
            "Only %d Exa results for question (need >= %d), marking low-confidence",
            len(results),
            MIN_SOURCES_FOR_CONFIDENCE,
        )
        return []

    # Sanitize untrusted internet content before it flows into LLM prompts.
    # Anyone who controls a website indexed by Exa can embed prompt-injection
    # markers; sanitize_news_text neutralizes the most common patterns and
    # truncates to bound prompt growth.
    return [
        {
            "title": sanitize_news_text(r.get("title", ""), max_len=200),
            "url": r.get("url", ""),
            "published_date": r.get("publishedDate"),
            "text": sanitize_news_text(r.get("text", "")),
        }
        for r in results
    ]
