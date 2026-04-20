# -*- coding: utf-8 -*-
"""Reddit-based retail sentiment fetching via public JSON API (no auth required)."""

import logging
import requests
import yfinance as yf
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

_HEADERS = {"User-Agent": "TradingAgentsBot/0.1"}
_SUBREDDITS = ["wallstreetbets", "stocks", "options"]
_TIMEOUT = 10
_COMMENT_PREVIEW = 200   # max chars per comment shown to LLM
_TOP_POSTS_WITH_COMMENTS = 3   # fetch comments for this many top posts only


def _get_company_name(ticker: str) -> str:
    """Look up the short company name for a ticker via yfinance."""
    try:
        info = yf.Ticker(ticker).info
        return info.get("shortName") or info.get("longName") or ""
    except Exception:
        return ""


def _search_subreddit(subreddit: str, query: str) -> list:
    """Fetch up to 25 posts from a subreddit matching query. Returns raw post dicts."""
    params = {
        "q": query,
        "restrict_sr": 1,
        "sort": "relevance",
        "limit": 25,
        "t": "week",
    }
    try:
        r = requests.get(
            f"https://www.reddit.com/r/{subreddit}/search.json",
            params=params,
            headers=_HEADERS,
            timeout=_TIMEOUT,
        )
    except requests.RequestException as e:
        logger.warning("Reddit API request failed for r/%s: %s", subreddit, e)
        return []

    if r.status_code == 429:
        logger.warning("Reddit API rate limit hit (429) for r/%s", subreddit)
        return []
    if not r.ok:
        logger.warning("Reddit API returned HTTP %s for r/%s", r.status_code, subreddit)
        return []

    r.encoding = "utf-8"
    try:
        return r.json().get("data", {}).get("children", [])
    except ValueError:
        logger.warning("Reddit API returned invalid JSON for r/%s", subreddit)
        return []


def _fetch_top_comments(subreddit: str, post_id: str, limit: int = 20) -> list[str]:
    """
    Fetch top-level comments for a post, sorted by score.
    Returns a list of comment body strings (truncated to _COMMENT_PREVIEW chars).
    """
    try:
        r = requests.get(
            f"https://www.reddit.com/r/{subreddit}/comments/{post_id}.json",
            params={"sort": "top", "limit": limit, "depth": 1},
            headers=_HEADERS,
            timeout=_TIMEOUT,
        )
    except requests.RequestException as e:
        logger.warning("Reddit comment fetch failed for %s/%s: %s", subreddit, post_id, e)
        return []

    if r.status_code == 429:
        logger.warning("Reddit API rate limit hit (429) fetching comments for %s", post_id)
        return []
    if not r.ok:
        logger.warning("Reddit comment API returned HTTP %s for %s", r.status_code, post_id)
        return []

    r.encoding = "utf-8"
    try:
        data = r.json()
    except ValueError:
        return []

    # Response is [post_listing, comment_listing]
    if len(data) < 2:
        return []

    _BOT_AUTHORS = {"automoderator", "visualmod"}

    comments = []
    for item in data[1].get("data", {}).get("children", []):
        cdata = item.get("data", {})
        author = cdata.get("author", "").lower()
        if author in _BOT_AUTHORS:
            continue
        body = cdata.get("body", "")
        if not body or body == "[deleted]" or body == "[removed]":
            continue
        # Truncate and clean whitespace
        body = " ".join(body.split())
        comments.append(body[:_COMMENT_PREVIEW])

    return comments


def get_reddit_sentiment(ticker: str, days: int = 3) -> str:
    """
    Fetch recent Reddit posts mentioning a ticker from investing subreddits.

    Searches r/wallstreetbets, r/stocks, and r/options via Reddit's public
    JSON API (no authentication required). Runs separate queries for the ticker
    symbol and company name so posts using either form are captured. Only keeps
    posts whose title contains the ticker or company name. Fetches top comments
    for the three highest-scoring posts to capture actual retail discussion.

    Args:
        ticker: Stock ticker symbol (e.g., "NVDA")
        days: Number of days to look back (default 3)

    Returns:
        Formatted string of matching posts with top comments, or empty string
        on API failure.
    """
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=days)

    company_name = _get_company_name(ticker)
    # Use the first meaningful word of the company name as a separate search term
    # e.g. "NVIDIA Corporation" → "NVIDIA", "Apple Inc." → "Apple"
    name_keyword = ""
    if company_name:
        first_word = company_name.split()[0]
        if len(first_word) > 3 and first_word.upper() != ticker.upper():
            name_keyword = first_word

    search_terms = [ticker]
    if name_keyword:
        search_terms.append(name_keyword)

    seen_ids = set()
    all_posts = []

    for subreddit in _SUBREDDITS:
        for term in search_terms:
            for item in _search_subreddit(subreddit, term):
                post = item.get("data", {})
                post_id = post.get("id", "")

                if post_id in seen_ids:
                    continue

                # Only keep posts whose title mentions ticker or company name
                title_lower = post.get("title", "").lower()
                if ticker.lower() not in title_lower and (
                    not name_keyword or name_keyword.lower() not in title_lower
                ):
                    continue

                created_utc = post.get("created_utc", 0)
                post_time = datetime.fromtimestamp(created_utc, tz=timezone.utc)
                if post_time < cutoff:
                    continue

                seen_ids.add(post_id)
                all_posts.append({
                    "id": post_id,
                    "subreddit": subreddit,
                    "title": post.get("title", ""),
                    "score": post.get("score", 0),
                    "num_comments": post.get("num_comments", 0),
                    "upvote_ratio": post.get("upvote_ratio", 0.0),
                    "flair": post.get("link_flair_text") or "",
                })

    if not all_posts:
        return (
            f"No Reddit posts found mentioning {ticker} in the last {days} days "
            f"across r/wallstreetbets, r/stocks, r/options."
        )

    # Sort by score descending — highest engagement first
    all_posts.sort(key=lambda p: p["score"], reverse=True)

    # Fetch comments for top N posts only to keep API calls bounded
    for post in all_posts[:_TOP_POSTS_WITH_COMMENTS]:
        post["comments"] = _fetch_top_comments(post["subreddit"], post["id"])

    label = f"{ticker}" + (f" / {name_keyword}" if name_keyword else "")
    lines = [f"Reddit posts mentioning {label} (last {days} days, sorted by upvotes):\n"]

    for i, p in enumerate(all_posts):
        flair = f" [{p['flair']}]" if p["flair"] else ""
        lines.append(
            f"r/{p['subreddit']}{flair} | "
            f"Score: {p['score']} | "
            f"Comments: {p['num_comments']} | "
            f"Upvote ratio: {p['upvote_ratio']:.0%} | "
            f"{p['title']}"
        )
        comments = p.get("comments", [])
        if comments:
            for c in comments:
                lines.append(f"  > {c}")

    return "\n".join(lines)
