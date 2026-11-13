"""Reddit fetcher for ticker-specific discussion posts.

Reads Reddit's public Atom/RSS listing of the newest posts, all subreddits in
one combined request, and keeps the posts that discuss the ticker. Both search
endpoints answer anonymous clients ``HTTP 403``: the JSON one long since (#862),
the RSS one this module used to read as of 2026-11-11. The listing is still
served; it carries no score or comment counts. On a 429 we back off once,
honouring ``Retry-After``.

A listing is not a search. It holds the newest ``_FEED_PAGE`` posts whatever
they are about, so how far back it reaches depends on how busy the subreddits
are (one to five days when measured, where the search covered a week), and it
vouches for nothing older than its oldest post: an absence is reported against
the page that was read, never as silence over days it did not reach.

A fetch that fails is reported as ``<unavailable>``, never as "no posts found":
the two are different claims, and passing a rate-limited fetch off as silence
hands the sentiment analyst a signal that was never observed (#1295).

No API key required. Returns formatted plaintext blocks ready for prompt
injection and degrades gracefully — returns a placeholder string rather than
raising, so callers never special-case missing data.
"""

from __future__ import annotations

import html
import http.client
import logging
import random
import re
import time
import xml.etree.ElementTree as ET
from collections.abc import Iterable
from datetime import UTC, datetime
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from tradingagents.dataflows.date_window import coverage_gap, in_window
from tradingagents.dataflows.symbols import crypto_base

logger = logging.getLogger(__name__)


def _within_window(posts, start_date, end_date):
    """Keep only posts published in [start_date, end_date] (look-ahead safe).

    No window (both None) leaves the list untouched for live callers. A post with
    no ``created_utc`` epoch is dropped in a historical window (#1220).
    """
    if not (start_date and end_date):
        return posts
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    return [p for p in posts if in_window(_posted_at(p), start_dt, end_dt)]


def _posted_at(post) -> datetime | None:
    """A post's ``created_utc`` epoch as a UTC datetime, or None when missing."""
    ts = post.get("created_utc")
    return datetime.fromtimestamp(ts, tz=UTC) if ts else None


def _oldest(posts) -> datetime | None:
    """When the oldest dated post was published. A listing is newest-first and
    unbroken in time, so this is how far back the page reaches and all that
    bounds its coverage: there is no lookback to fall back on."""
    return min((d for d in map(_posted_at, posts) if d is not None), default=None)


_RSS = "https://www.reddit.com/r/{sub}/new.rss?limit={limit}"
# A descriptive, identified User-Agent (per Reddit's API etiquette). Reddit
# blocks generic/anonymous tokens like bare "Mozilla/5.0" or "curl/…" but
# serves this one the listing feed, so no browser-spoofing is needed. The
# search endpoints 403 it.
_UA = "tradingagents/0.2 (+https://github.com/TauricResearch/TradingAgents)"
_ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}

# Default subreddits ordered roughly by signal density for ticker-specific
# discussion. wallstreetbets has the most volume but most noise; stocks /
# investing trend more measured. Caller can override.
DEFAULT_SUBREDDITS = ("wallstreetbets", "stocks", "investing")

# Crypto is discussed in crypto communities, where a coin's own subreddit carries
# most of it; the stock subreddits above barely mention it.
CRYPTO_SUBREDDITS = ("CryptoCurrency", "CryptoMarkets")
_COIN_SUBREDDITS = {"BTC": "Bitcoin", "ETH": "ethereum", "SOL": "solana"}
# Symbols that are not also words, so posts may write them in any case ("btc
# dumping"). LINK or DOT must stay out: in lower case they are ordinary words.
_ANY_CASE_SYMBOLS = frozenset({"BTC", "ETH", "SOL"})


def subreddits_for(ticker: str) -> tuple[str, ...]:
    """The subreddits read for ``ticker``: crypto communities for a crypto pair."""
    base = crypto_base(ticker)
    if not base:
        return DEFAULT_SUBREDDITS
    coin = _COIN_SUBREDDITS.get(base)
    return ((coin,) if coin else ()) + CRYPTO_SUBREDDITS

# Reddit's maximum page size, and all one request can read of a listing.
# Measured 2026-11-13, a page went back 41 hours across BTC's three subreddits,
# 118 across ETH's, 110 across SOL's and 30 across the stock ones.
_FEED_PAGE = 100
_SCREEN_CHARS = 1000   # of a post's title and body sent for screening


def _mentions(ticker: str) -> re.Pattern[str]:
    """Pattern for a post that names ``ticker``.

    A listing is not searched, so outside the coin's own subreddit a post counts
    only when it names the coin: by symbol as written (BTC) or as a cashtag
    ($btc), and for a coin with its own subreddit by the name that subreddit
    carries (Bitcoin, bitcoiners).
    """
    symbol = re.escape(ticker.upper())
    forms = [rf"{symbol}(?!\w)", rf"(?i:\${symbol})(?!\w)"]
    if ticker.upper() in _ANY_CASE_SYMBOLS:
        forms.append(rf"(?i:{symbol})(?!\w)")
    name = _COIN_SUBREDDITS.get(ticker.upper())
    if name:
        forms.append(rf"(?i:{re.escape(name)})")
    return re.compile(rf"(?<!\w)(?:{'|'.join(forms)})")


def _iso_to_timestamp(iso_str: str | None) -> float | None:
    """Parse an Atom ``published`` timestamp to a UTC epoch, or None."""
    if not iso_str:
        return None
    try:
        normalized = iso_str[:-1] + "+00:00" if iso_str.endswith("Z") else iso_str
        return datetime.fromisoformat(normalized).timestamp()
    except (ValueError, TypeError):
        return None


# The byline Reddit ends every entry with. A link post has no text of its own,
# so there it is the whole body: noise in an excerpt, and its username could
# pass for a mention of the coin ("/u/bitcoin-fan").
_BYLINE = re.compile(r"\s*submitted by /u/\S+(?: to r/\S+)? \[link\] \[comments\]$")


def _strip_html(content: str) -> str:
    """Reduce the HTML body Reddit embeds in an Atom entry to the post's own text."""
    if not content:
        return ""
    # Reddit wraps the real selftext between SC_OFF / SC_ON markers.
    if "<!-- SC_OFF -->" in content and "<!-- SC_ON -->" in content:
        content = content.split("<!-- SC_OFF -->")[1].split("<!-- SC_ON -->")[0]
    text = re.sub(r"<[^>]+>", " ", content)
    return _BYLINE.sub("", " ".join(html.unescape(text).split()))


# Headerless-429 backoff when Reddit gives no Retry-After. Measured against
# /r/{sub}/search.rss, a retry still 429s at 8s, 10s and 30s of spacing and
# succeeds at 60s, so a shorter wait spends the one retry on a request that
# cannot succeed (#1295). Jittered so several analyses sharing an IP don't
# retry in lockstep and re-collide on the limit.
_RETRY_FALLBACK_SECONDS = 60.0


def _jitter(seconds: float, frac: float = 0.2) -> float:
    """Return ``seconds`` with +/-``frac`` random jitter, to desynchronize
    concurrent runs pacing against the same per-IP limit."""
    return seconds * (1.0 + random.uniform(-frac, frac))


def _retry_after_seconds(exc: HTTPError) -> float | None:
    """Seconds to wait from a 429's ``Retry-After`` header, capped at 60s.

    The cap matches ``_RETRY_FALLBACK_SECONDS``: honouring less than we would
    wait on our own would spend the one retry on a request we already know is
    too early.

    Returns ``None`` only when the header is absent or unparseable; a valid
    ``Retry-After: 0`` returns ``0.0`` (retry at once), not ``None``.
    """
    try:
        val = exc.headers.get("Retry-After") if getattr(exc, "headers", None) else None
        return min(float(val), 60.0) if val is not None else None
    except (ValueError, TypeError, AttributeError):
        return None


# A Reddit feed is small (one page of posts); cap the read so a
# compromised or misbehaving endpoint can't stream an unbounded body into
# memory before we parse it. Overflow raises http.client.HTTPException, which
# both fetch paths already treat as a failed fetch (degrade to empty / RSS).
_MAX_FEED_BYTES = 5 * 1024 * 1024


def _read_capped(resp) -> bytes:
    """Read a response body bounded to ``_MAX_FEED_BYTES``, raising on overflow."""
    data = resp.read(_MAX_FEED_BYTES + 1)
    if len(data) > _MAX_FEED_BYTES:
        raise http.client.HTTPException(
            f"Reddit feed exceeded {_MAX_FEED_BYTES} bytes; refusing to parse"
        )
    return data


def _fetch_subreddit_rss(
    ticker: str,
    sub: str,
    limit: int,
    timeout: float,
    _retry: bool = True,
) -> list[dict] | None:
    """Read the newest posts of a subreddit from its public Atom listing.

    ``sub`` may be one subreddit or several joined with ``+``. The listing is
    not filtered by ``ticker``, which only labels the log lines. On a 429
    (Reddit's per-IP rate limit) we back off once — honouring ``Retry-After``
    when present — before giving up, so a transient burst doesn't blank the feed.

    Returns the page that was read, and ``None`` when the fetch itself failed.
    The caller must keep these apart: rendering a failed fetch as "no posts
    found" hands the sentiment analyst an absence of discussion that was never
    observed (#1295).
    """
    url = _RSS.format(sub=sub, limit=limit)
    req = Request(url, headers={"User-Agent": _UA})
    try:
        with urlopen(req, timeout=timeout) as resp:
            root = ET.fromstring(_read_capped(resp))
    except HTTPError as exc:
        if exc.code == 429 and _retry:
            # Honour a server-supplied Retry-After exactly (including 0); jitter
            # only our own fallback so concurrent runs don't retry in lockstep.
            retry_after = _retry_after_seconds(exc)
            wait = retry_after if retry_after is not None else _jitter(_RETRY_FALLBACK_SECONDS)
            logger.warning(
                "Reddit RSS 429 for r/%s · %s — backing off %.1fs then retrying once",
                sub, ticker, wait,
            )
            time.sleep(wait)
            return _fetch_subreddit_rss(ticker, sub, limit, timeout, _retry=False)
        logger.warning("Reddit RSS fetch failed for r/%s · %s: %s", sub, ticker, exc)
        return None
    except (OSError, http.client.HTTPException, ET.ParseError) as exc:
        # OSError covers URLError/TimeoutError/connection resets; HTTPException
        # covers chunked-transfer errors (IncompleteRead/BadStatusLine, #1024).
        logger.warning("Reddit RSS fetch failed for r/%s · %s: %s", sub, ticker, exc)
        return None

    posts = []
    for entry in root.findall("atom:entry", _ATOM_NS)[:limit]:
        title_el = entry.find("atom:title", _ATOM_NS)
        published_el = entry.find("atom:published", _ATOM_NS)
        content_el = entry.find("atom:content", _ATOM_NS)
        category_el = entry.find("atom:category", _ATOM_NS)
        posts.append({
            "title": (title_el.text if title_el is not None else "") or "",
            "created_utc": _iso_to_timestamp(
                published_el.text if published_el is not None else None
            ),
            "selftext": _strip_html(content_el.text if content_el is not None else ""),
            # A combined feed names each entry's subreddit; a single-subreddit
            # feed may omit it, and then it can only be that one.
            "subreddit": category_el.get("term") if category_el is not None
            else (sub if "+" not in sub else ""),
        })
    return posts


def fetch_reddit_posts(
    ticker: str,
    subreddits: Iterable[str] | None = None,
    *,
    limit_per_sub: int = 5,
    timeout: float = 10.0,
    start_date: str | None = None,
    end_date: str | None = None,
    screen=None,
) -> str:
    """Fetch recent Reddit posts about ``ticker`` from finance subreddits (by
    default ``subreddits_for(ticker)``) and return them as a formatted
    plaintext block.

    All subreddits are read in one combined listing (``r/a+b+c``): anonymous
    RSS allows about one request per minute per IP, so a request per subreddit
    spent a back-off on almost every run. Each entry names its subreddit, and
    posts are grouped back by it. A coin's own subreddit is kept whole; from
    any other, only the posts that name the ticker.

    When ``start_date``/``end_date`` (yyyy-mm-dd) are given, posts are trimmed to
    that window so a historical run does not leak current discussion into a
    backtest (#1220).

    ``screen``, when given, takes each post's title and body and returns a keep
    flag per post and a note line that heads the block. It runs before the
    per-subreddit cut, so the posts it keeps fill the slots.
    """
    subreddits = list(subreddits or subreddits_for(ticker))
    # Crypto reaches us as a Yahoo pair (BTC-USD); Reddit writes the base
    # ("BTC"), so that is what posts are matched against.
    ticker = crypto_base(ticker) or ticker
    symbol = ticker.upper()
    label = ", ".join(f"r/{s}" for s in subreddits)
    fetched = _fetch_subreddit_rss(ticker, "+".join(subreddits), _FEED_PAGE, timeout)
    if not fetched:
        # These subreddits always have posts, so an empty page is no more a
        # look at them than a failed fetch.
        why = "fetch failed" if fetched is None else "the feed came back empty"
        return f"<Reddit unavailable: {why} ({label}); this is not an absence of discussion>"

    def sub_of(p):
        return p.get("subreddit") or (subreddits[0] if len(subreddits) == 1 else "unknown")

    own = (_COIN_SUBREDDITS.get(symbol) or "").lower()
    mentions = _mentions(ticker)
    window = bool(start_date and end_date)
    reached = _within_window(fetched, start_date, end_date)
    posts = [
        p for p in reached
        if sub_of(p).lower() == own
        or mentions.search(f"{p.get('title') or ''}\n{p.get('selftext') or ''}")
    ]
    oldest = _oldest(fetched)
    page = f"the newest {len(fetched)} across {label}"
    if oldest:
        page += f", back to {oldest:%Y-%m-%d}"
    within = f" within {start_date}..{end_date}" if window else ""
    if not posts:
        # A window the page holds no post from was never read, unless the page
        # goes back past it. One it does hold posts from was read as far back as
        # the page goes, and the absence says how far that is.
        gap = window and not reached and coverage_gap(
            [oldest], start_date, end_date, "Reddit", f"discussion of {symbol}",
        )
        return gap or f"<no Reddit posts found mentioning {symbol}{within} among {page}>"

    note, screened_out = "", set()
    if screen:
        keep, note = screen([f"{p.get('title') or ''}\n{p.get('selftext') or ''}"[:_SCREEN_CHARS]
                             for p in posts])
        screened_out = {sub_of(p).lower() for p, kept in zip(posts, keep, strict=True) if not kept}
        posts = [p for p, kept in zip(posts, keep, strict=True) if kept]

    # Group by the subreddit each entry names, in the requested order. Nothing
    # is dropped: an unlabelled post from a one-subreddit request belongs to it,
    # and any other name gets its own block.
    by_sub = {s.lower(): (s, []) for s in subreddits}
    for p in posts:
        by_sub.setdefault(sub_of(p).lower(), (sub_of(p), []))[1].append(p)

    blocks = []
    for sub, sub_posts in by_sub.values():
        about = "" if sub.lower() == own else f" mentioning {symbol}"
        if not sub_posts:
            blocks.append(
                f"r/{sub}: <no posts about {symbol} after screening>"
                if sub.lower() in screened_out
                else f"r/{sub}: <no posts{about}{within} among {page}>"
            )
            continue
        sub_posts = sub_posts[:limit_per_sub]  # the feed is newest-first
        lines = [f"r/{sub} — {len(sub_posts)} recent posts{about}:"]
        for p in sub_posts:
            title = (p.get("title") or "").replace("\n", " ").strip()
            created = p.get("created_utc")
            created_str = time.strftime("%Y-%m-%d", time.gmtime(created)) if created else "?"
            selftext = (p.get("selftext") or "").replace("\n", " ").strip()
            if len(selftext) > 240:
                selftext = selftext[:240] + "…"
            lines.append(
                f"  [{created_str}] {title}"
                + (f"\n    body excerpt: {selftext}" if selftext else "")
            )
        blocks.append("\n".join(lines))
    return "\n\n".join(([note] if note else []) + blocks)
