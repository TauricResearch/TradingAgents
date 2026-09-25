"""Crypto sentiment helpers."""

from __future__ import annotations

import logging
from typing import List

import requests

from tradingagents.dataflows.fear_greed import get_fear_greed

logger = logging.getLogger(__name__)


def get_crypto_fear_greed(days: int = 7) -> str:
    """Fetch the crypto Fear & Greed Index from alternative.me."""
    return get_fear_greed(days)


def get_crypto_reddit_sentiment(ticker: str, days: int = 3) -> str:
    """Fetch lightweight public Reddit search results for crypto sentiment."""
    base = ticker.split("/")[0].replace("USDT", "")
    query = f"{base} crypto OR {ticker}"
    try:
        response = requests.get(
            "https://www.reddit.com/search.json",
            params={"q": query, "sort": "new", "t": "day", "limit": 10},
            headers={"User-Agent": "TradingAgents/crypto-train"},
            timeout=10,
        )
        response.raise_for_status()
        children = response.json().get("data", {}).get("children", [])
    except Exception as exc:
        logger.warning("Crypto Reddit sentiment fetch failed for %s: %s", ticker, exc)
        return f"Crypto Reddit sentiment unavailable for {ticker}: {exc}"

    posts: List[str] = []
    for child in children:
        data = child.get("data", {})
        title = data.get("title")
        if not title:
            continue
        subreddit = data.get("subreddit", "unknown")
        score = data.get("score", 0)
        comments = data.get("num_comments", 0)
        posts.append(f"- r/{subreddit} | score={score} comments={comments} | {title}")

    if not posts:
        return f"No recent Reddit crypto posts found for {ticker}."
    return f"Recent Reddit crypto sentiment for {ticker}:\n" + "\n".join(posts)
