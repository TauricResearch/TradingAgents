"""Reddit search fetcher for ticker-specific discussion posts.

Default path is Reddit's public Atom/RSS search feed
(``reddit.com/r/{sub}/search.rss``). The richer JSON search endpoint
(``/search.json``) is reliably WAF-blocked (``HTTP 403``) for public clients
(issue #862), and probing it on every call only doubled our request volume
against Reddit's per-IP rate limit — tripping ``429`` on the RSS fallback — so
it is kept (``_fetch_subreddit_json``) but not used by default. On a 429 we back
off once (honouring ``Retry-After``). RSS lacks score / comment counts, so those
posts are marked and the formatter omits the metrics rather than printing fake
zeros.

Optional PRAW OAuth path: when ``REDDIT_CLIENT_ID`` (and optionally
``REDDIT_CLIENT_SECRET``, ``REDDIT_USERNAME``, ``REDDIT_PASSWORD``) are set,
PRAW is used for the OAuth JSON endpoint which provides full score/comment
counts and dramatically higher rate limits (~60 req/min vs ~10 for RSS).
Install PRAW with: pip install praw

A module-level rate limiter (``_last_request_time`` / ``_min_request_gap``)
paces requests across subreddits so a burst of N sub-reddit fetches doesn't
trip Reddit's per-IP rate limit. The gap starts at 1.0 s and doubles on every
429 (up to a cap), decaying back down after a quiet period — this lets normal
usage stay fast while still applying back-pressure after a rate-limit hit.

No API key required. Returns formatted plaintext blocks ready for prompt
injection and degrades gracefully — returns a placeholder string rather than
raising, so callers never special-case missing data.
"""

from __future__ import annotations

import contextlib
import html
import http.client
import json
import logging
import os
import re
import threading
import time
import xml.etree.ElementTree as ET
from collections.abc import Iterable
from datetime import datetime
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

_API = "https://www.reddit.com/r/{sub}/search.json?{qs}"
_RSS = "https://www.reddit.com/r/{sub}/search.rss?{qs}"
# A descriptive, identified User-Agent (per Reddit's API etiquette). Reddit
# blocks generic/anonymous tokens like bare "Mozilla/5.0" or "curl/…" but
# serves this one on both endpoints; the RSS feed accepts it even when the
# JSON search endpoint 403s, so no browser-spoofing is needed.
_UA = "tradingagents/0.2 (+https://github.com/TauricResearch/TradingAgents)"
_ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}

# -- PRAW OAuth support -----------------------------------------------------
# Reddit's OAuth API gives ~60 req/min for authenticated requests vs ~10 for
# unauthenticated RSS. When REDDIT_CLIENT_ID (+ optionally REDDIT_CLIENT_SECRET)
# are set, we use PRAW for the richer JSON response (score / comment counts).
# Script apps also need REDDIT_USERNAME / REDDIT_PASSWORD.
# Without credentials the existing RSS fallback continues to work as before.
_reddit_client = None


def _has_praw_credentials() -> bool:
    """True when sufficient Reddit OAuth credentials are configured."""
    client_id = os.getenv("REDDIT_CLIENT_ID", "").strip()
    return bool(client_id)


def _get_praw_client():
    """Lazily create a PRAW Reddit instance authenticated via OAuth.

    Falls back to None if PRAW is not installed or credentials are missing.
    """
    global _reddit_client
    if _reddit_client is not None:
        return _reddit_client
    if not _has_praw_credentials():
        return None
    try:
        import praw
    except ImportError:
        logger.debug("PRAW not installed; Reddit OAuth unavailable.")
        return None
    client_id = os.getenv("REDDIT_CLIENT_ID", "").strip()
    client_secret = os.getenv("REDDIT_CLIENT_SECRET", "").strip() or None
    username = os.getenv("REDDIT_USERNAME", "").strip() or None
    password = os.getenv("REDDIT_PASSWORD", "").strip() or None
    try:
        _reddit_client = praw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            username=username,
            password=password,
            user_agent=_UA,
        )
        # Verify the client works by checking the rate limit endpoint.
        # PRAW 7+ raises on auth failure here rather than on first search.
        with contextlib.suppress(AttributeError):
            _ = _reddit_client.auth.scopes()
        logger.info("Reddit: PRAW OAuth initialized (user=%s).", username or "<anonymous>")
        return _reddit_client
    except Exception as exc:
        logger.warning("Reddit PRAW OAuth init failed: %s — falling back to RSS.", exc)
        _reddit_client = None
        return None


def _fetch_subreddit_praw(
    ticker: str,
    sub: str,
    limit: int,
) -> list[dict]:
    """Fetch via PRAW OAuth JSON endpoint (provides score / comment counts).

    Requires ``REDDIT_CLIENT_ID`` env var (and ``REDDIT_CLIENT_SECRET`` for
    script apps; anonymous read-only apps only need the client ID).
    Falls back to the RSS path on any error so callers always get a result.
    """
    client = _get_praw_client()
    if client is None:
        return []  # Will trigger RSS fallback in _fetch_subreddit

    try:
        subreddit = client.subreddit(sub)
        posts = []
        for submission in subreddit.search(ticker, sort="new", time_filter="week", limit=limit):
            posts.append({
                "title": submission.title or "",
                "score": submission.score,
                "num_comments": submission.num_comments,
                "created_utc": submission.created_utc,
                "selftext": submission.selftext or "",
                "source": "praw",
            })
        logger.debug("PRAW fetched %d posts for r/%s · %s", len(posts), sub, ticker)
        return posts
    except Exception as exc:
        logger.debug("PRAW fetch failed for r/%s · %s: %s — falling back to RSS.", sub, ticker, exc)
        return []  # Trigger RSS fallback

# Default subreddits ordered roughly by signal density for ticker-specific
# discussion. wallstreetbets has the most volume but most noise; stocks /
# investing trend more measured. Caller can override.
DEFAULT_SUBREDDITS = ("wallstreetbets", "stocks", "investing")

# -- Module-level rate limiter -----------------------------------------------
# Reddit's per-IP rate limit is global (not per-subreddit), so sequential
# fetches for different subreddits must be paced together.  We track the
# timestamp of the last request and enforce a minimum gap; on a 429 the gap
# is doubled (capped) to apply back-pressure, and it decays back to the
# baseline after ``_DECAY_AFTER`` seconds of quiet.

_MIN_REQUEST_GAP = 1.0       # seconds between requests (baseline)
_MAX_REQUEST_GAP = 30.0      # cap on exponential back-off
_DECAY_AFTER = 30.0          # quiet period before resetting gap to baseline

_last_request_time: float = 0.0
_min_request_gap: float = _MIN_REQUEST_GAP
_rate_lock = threading.Lock()

# Track whether we've confirmed persistent rate limiting (429 on retry).
# Set by _fetch_subreddit_rss when the retry also gets a 429, read by
# fetch_reddit_posts to skip remaining subreddits rather than wasting
# backoff time on requests that will also be throttled.
_confirmed_rate_limited: bool = False
_confirmed_rate_lock = threading.Lock()

# -- In-memory TTL cache ----------------------------------------------------
# Reddit RSS is per-IP rate limited.  Cache results per (ticker, sub) so
# repeated analysis runs for the same ticker skip the HTTP request entirely —
# dramatically reducing 429s when multiple tickers run concurrently.
_CACHE_TTL = 3600.0
_cache: dict[tuple[str, str], tuple[float, list[dict]]] = {}
_cache_lock = threading.Lock()

# -- Per-(ticker, sub) deduplication locks ----------------------------------
# When multiple threads (e.g. background run parallel workers) fetch the same
# (ticker, sub) simultaneously, only one thread makes the HTTP request; the
# others wait for the lock, then find the result already cached.
_fetch_dedup_locks: dict[tuple[str, str], threading.Lock] = {}
_fetch_dedup_locks_lock = threading.Lock()


def _dedup_lock(ticker: str, sub: str) -> threading.Lock:
    """Return or create a deduplication lock for ``(ticker, sub)``."""
    key = (ticker.upper(), sub)
    with _fetch_dedup_locks_lock:
        if key not in _fetch_dedup_locks:
            _fetch_dedup_locks[key] = threading.Lock()
        return _fetch_dedup_locks[key]


def _cache_get(ticker: str, sub: str) -> list[dict] | None:
    """Return cached posts for ``(ticker, sub)`` or ``None`` if stale/missing."""
    with _cache_lock:
        entry = _cache.get((ticker.upper(), sub))
        if entry is None:
            return None
        ts, results = entry
        if time.monotonic() - ts > _CACHE_TTL:
            del _cache[(ticker.upper(), sub)]
            return None
        return results


def _cache_set(ticker: str, sub: str, results: list[dict]) -> None:
    """Store ``results`` for ``(ticker, sub)`` with the current timestamp."""
    with _cache_lock:
        _cache[(ticker.upper(), sub)] = (time.monotonic(), results)


def _pace_request() -> None:
    """Block until the minimum gap since the last Reddit request has elapsed."""
    global _last_request_time, _min_request_gap
    with _rate_lock:
        elapsed = time.monotonic() - _last_request_time
        needed = _min_request_gap - elapsed
        if needed > 0:
            time.sleep(needed)
        _last_request_time = time.monotonic()


def _on_rate_limited() -> None:
    """Double the request gap (capped) after a 429 response."""
    global _min_request_gap, _last_request_time
    with _rate_lock:
        new_gap = _min_request_gap * 2
        _min_request_gap = min(new_gap, _MAX_REQUEST_GAP)
        _last_request_time = time.monotonic()
        logger.info(
            "Reddit rate-limited; request gap raised to %.1fs",
            _min_request_gap,
        )


def _decay_gap_if_quiet() -> None:
    """If no request was made for ``_DECAY_AFTER`` seconds, reset to baseline."""
    global _min_request_gap
    with _rate_lock:
        if time.monotonic() - _last_request_time >= _DECAY_AFTER and _min_request_gap > _MIN_REQUEST_GAP:
            _min_request_gap = _MIN_REQUEST_GAP
            logger.info("Reddit rate-limiter decayed back to %.1fs", _min_request_gap)


def _search_qs(ticker: str, limit: int) -> str:
    return urlencode({
        "q": ticker,
        "restrict_sr": "on",
        "sort": "new",
        "t": "week",  # last 7 days
        "limit": limit,
    })


def _iso_to_timestamp(iso_str: str | None) -> float | None:
    """Parse an Atom ``published`` timestamp to a UTC epoch, or None."""
    if not iso_str:
        return None
    try:
        normalized = iso_str[:-1] + "+00:00" if iso_str.endswith("Z") else iso_str
        return datetime.fromisoformat(normalized).timestamp()
    except (ValueError, TypeError):
        return None


def _strip_html(content: str) -> str:
    """Reduce the HTML body Reddit embeds in an Atom entry to plain text."""
    if not content:
        return ""
    # Reddit wraps the real selftext between SC_OFF / SC_ON markers.
    if "<!-- SC_OFF -->" in content and "<!-- SC_ON -->" in content:
        content = content.split("<!-- SC_OFF -->")[1].split("<!-- SC_ON -->")[0]
    text = re.sub(r"<[^>]+>", " ", content)
    return " ".join(html.unescape(text).split())


def _retry_after_seconds(exc: HTTPError) -> float | None:
    """Seconds to wait from a 429's ``Retry-After`` header, capped at 30s."""
    try:
        val = exc.headers.get("Retry-After") if getattr(exc, "headers", None) else None
        return min(float(val), 30.0) if val else None
    except (ValueError, TypeError, AttributeError):
        return None


def _fetch_subreddit_rss(
    ticker: str,
    sub: str,
    limit: int,
    timeout: float,
    _retry: bool = True,
) -> list[dict]:
    """Default path: parse the public Atom search feed for a subreddit.

    Carries no score / comment counts, so those fields are left None and the
    post is tagged ``source="rss"`` for honest display. On a 429 (Reddit's
    per-IP rate limit) we back off once — honouring ``Retry-After`` when
    present — before giving up, so a transient burst doesn't blank the feed.

    The module-level rate limiter (``_pace_request`` / ``_on_rate_limited``)
    paces requests *across* subreddits so a burst of N sub-reddit fetches
    doesn't trip Reddit's per-IP rate limit.
    """
    _decay_gap_if_quiet()
    _pace_request()
    url = _RSS.format(sub=sub, qs=_search_qs(ticker, limit))
    req = Request(url, headers={"User-Agent": _UA})
    try:
        with urlopen(req, timeout=timeout) as resp:
            root = ET.fromstring(resp.read())
    except HTTPError as exc:
        if exc.code == 429:
            _on_rate_limited()
            if _retry:
                wait = _retry_after_seconds(exc) or 5.0
                logger.debug(
                    "Reddit RSS 429 for r/%s · %s — backing off %.1fs then retrying once",
                    sub, ticker, wait,
                )
                time.sleep(wait)
                return _fetch_subreddit_rss(ticker, sub, limit, timeout, _retry=False)
            # Retry also failed with 429 — Reddit is actively throttling us.
            # Signal fetch_reddit_posts to skip remaining subreddits rather
            # than retrying each one (they will all fail).
            with _confirmed_rate_lock:
                _confirmed_rate_limited = True
        logger.warning("Reddit RSS fetch failed for r/%s · %s: %s", sub, ticker, exc)
        return []
    except (OSError, http.client.HTTPException, ET.ParseError) as exc:
        # OSError covers URLError/TimeoutError/connection resets; HTTPException
        # covers chunked-transfer errors (IncompleteRead/BadStatusLine, #1024).
        logger.warning("Reddit RSS fetch failed for r/%s · %s: %s", sub, ticker, exc)
        return []

    posts = []
    for entry in root.findall("atom:entry", _ATOM_NS)[:limit]:
        title_el = entry.find("atom:title", _ATOM_NS)
        published_el = entry.find("atom:published", _ATOM_NS)
        content_el = entry.find("atom:content", _ATOM_NS)
        content_text = content_el.text if content_el is not None else None
        posts.append({
            "title": (title_el.text if title_el is not None else "") or "",
            "score": None,
            "num_comments": None,
            "created_utc": _iso_to_timestamp(
                published_el.text if published_el is not None else None
            ),
            "selftext": _strip_html(content_text or ""),
            "source": "rss",
        })
    return posts


def _fetch_subreddit_json(
    ticker: str,
    sub: str,
    limit: int,
    timeout: float,
) -> list[dict]:
    """Richer JSON search path (carries score / comment counts).

    Reddit's WAF currently returns ``403 Blocked`` on this endpoint for
    non-OAuth clients (issue #862), so it is NOT used by default — calling it on
    every request only doubled our volume against the per-IP rate limit and
    triggered 429s on the RSS fallback. Kept for the day the WAF relaxes or an
    OAuth token is wired in; degrades to RSS on failure.
    """
    url = _API.format(sub=sub, qs=_search_qs(ticker, limit))
    req = Request(url, headers={"User-Agent": _UA, "Accept": "application/json"})
    try:
        with urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read())
        children = (payload.get("data") or {}).get("children") or []
        return [c.get("data", {}) for c in children if isinstance(c, dict)]
    except (OSError, http.client.HTTPException, json.JSONDecodeError) as exc:
        logger.warning(
            "Reddit JSON fetch failed for r/%s · %s: %s — falling back to RSS feed.",
            sub, ticker, exc,
        )
        return _fetch_subreddit_rss(ticker, sub, limit, timeout)


def _fetch_subreddit(
    ticker: str,
    sub: str,
    limit: int,
    timeout: float,
) -> list[dict]:
    """Fetch one subreddit with TTL cache and thread deduplication.

    Tries PRAW OAuth first when credentials are set (higher rate limits,
    richer data with score/comment counts). Falls back to RSS on any error
    or when PRAW is unavailable, so callers always get a result.

    Results are cached in-memory for ``_CACHE_TTL`` seconds by ``(ticker, sub)``
    so repeated analysis runs for the same ticker skip the HTTP request.

    A per-(ticker, sub) deduplication lock ensures that when multiple threads
    (e.g. background run parallel workers) request the same pair concurrently,
    only one thread makes the HTTP request — the rest wait for the lock, then
    find the result already cached.
    """
    cached = _cache_get(ticker, sub)
    if cached is not None:
        return cached

    lock = _dedup_lock(ticker, sub)
    with lock:
        cached = _cache_get(ticker, sub)
        if cached is not None:
            return cached

        if _has_praw_credentials():
            _decay_gap_if_quiet()
            _pace_request()
            results = _fetch_subreddit_praw(ticker, sub, limit)
            if results:
                _cache_set(ticker, sub, results)
                return results

        results = _fetch_subreddit_rss(ticker, sub, limit, timeout)
        _cache_set(ticker, sub, results)
        return results


def fetch_reddit_posts(
    ticker: str,
    subreddits: Iterable[str] = DEFAULT_SUBREDDITS,
    limit_per_sub: int = 5,
    timeout: float = 10.0,
) -> str:
    """Fetch recent Reddit posts mentioning ``ticker`` across finance
    subreddits and return them as a formatted plaintext block.

    Pacing across subreddits is handled by the module-level rate limiter
    (``_pace_request``), which enforces a minimum gap between *any* two
    Reddit requests and doubles the gap on 429s.
    """
    blocks = []
    total_posts = 0
    # Reset the confirmed-rate-limited flag so a new ticker's fetch gets a
    # fresh chance — rate limiting may have subsided between calls.
    with _confirmed_rate_lock:
        _confirmed_rate_limited = False
    for sub in subreddits:
        # If a previous subreddit confirmed persistent rate limiting (429
        # on retry), skip remaining subreddits — they will also be throttled
        # and each wastes 5+ seconds on a doomed retry.
        with _confirmed_rate_lock:
            if _confirmed_rate_limited:
                blocks.append(
                    f"r/{sub}: <skipped due to Reddit rate limiting — "
                    f"use a smaller subreddit list or wait before retrying>"
                )
                continue
        posts = _fetch_subreddit(ticker, sub, limit_per_sub, timeout)
        total_posts += len(posts)
        if not posts:
            blocks.append(f"r/{sub}: <no posts found mentioning {ticker.upper()} in the past 7 days>")
            continue

        via_rss = any(p.get("source") == "rss" for p in posts)
        header = f"r/{sub} — {len(posts)} recent posts mentioning {ticker.upper()}"
        header += " (via RSS feed; scores/comments unavailable):" if via_rss else ":"
        lines = [header]
        for p in posts:
            title = (p.get("title") or "").replace("\n", " ").strip()
            score = p.get("score")
            comments = p.get("num_comments")
            created = p.get("created_utc")
            created_str = (
                time.strftime("%Y-%m-%d", time.gmtime(created)) if created else "?"
            )
            # Score / comment counts are absent on the RSS fallback path —
            # show them only when present rather than printing fake zeros.
            meta = created_str
            if score is not None and comments is not None:
                meta += f" · {score:>4}↑ · {comments:>3}c"
            selftext = (p.get("selftext") or "").replace("\n", " ").strip()
            if len(selftext) > 240:
                selftext = selftext[:240] + "…"
            lines.append(
                f"  [{meta}] {title}"
                + (f"\n    body excerpt: {selftext}" if selftext else "")
            )
        blocks.append("\n".join(lines))

    if total_posts == 0:
        return (
            f"<no Reddit posts found mentioning {ticker.upper()} across "
            f"{', '.join(f'r/{s}' for s in subreddits)} in the past 7 days>"
        )
    return "\n\n".join(blocks)
