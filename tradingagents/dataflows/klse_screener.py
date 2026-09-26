"""KLSE Screener comment fetcher — Malaysian retail-trader sentiment for
Bursa Malaysia (``.KL``) stocks.

klsescreener.com is a Malaysian retail-investor community site; its
per-stock discussion thread is the closest Bursa-listed equivalent to
StockTwits' cashtag stream. Unlike StockTwits and the Reddit finance
subreddits — both effectively empty for ``.KL`` names, since they are
US-centric platforms indexed overwhelmingly on US-listed tickers — this is
where Malaysian retail sentiment on a specific KLSE counter actually gets
posted, in a mix of English, Malay and Chinese.

The per-stock page (``/v2/stocks/view/{code}``) server-renders the first two
comments; the full thread lives at ``/v2/comments/all/stock/{code}``, whose
first page is plain HTML and whose subsequent pages ("Load More") are JSON
(``{"count": ..., "html": "..."}``) — but only when the request carries an
``X-Requested-With: XMLHttpRequest`` header; without it the endpoint just
serves the full page shell again instead of the fragment. Verified by hand
against the live site (2026-09-26) before writing this fetcher.

Comments carry no user-labeled Bullish/Bearish tag (unlike StockTwits), so
sentiment must be read from the text itself — same as Reddit.

Degrades gracefully like the other optional sentiment sources: never
raises, returns a placeholder string when a fetch fails so callers don't
special-case missing data, and distinguishes "fetch failed" from "searched
and found nothing" (the two are different claims — see reddit.py's #1295
note for why that distinction matters to the agents reading this output).
"""

from __future__ import annotations

import contextlib
import http.client
import json
import logging
import re
from datetime import datetime, timezone
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from parsel import Selector

from .date_window import in_window

logger = logging.getLogger(__name__)

_PAGE1_URL = "https://www.klsescreener.com/v2/comments/all/stock/{code}"
_PAGEN_URL = "https://www.klsescreener.com/v2/comments/all/stock/{code}/{page}"
_UA = "tradingagents/0.2 (+https://github.com/TauricResearch/TradingAgents)"

# Comment pages are small (~10 top-level comments + replies); cap the read so
# a compromised or misbehaving endpoint can't stream an unbounded body into
# memory before it's parsed — same guard reddit.py and google_news_my.py apply.
_MAX_PAGE_BYTES = 5 * 1024 * 1024


def _read_capped(resp) -> bytes:
    data = resp.read(_MAX_PAGE_BYTES + 1)
    if len(data) > _MAX_PAGE_BYTES:
        raise http.client.HTTPException(
            f"KLSE Screener page exceeded {_MAX_PAGE_BYTES} bytes; refusing to parse"
        )
    return data


def _bursa_code(ticker: str) -> str | None:
    """Extract Bursa's bare numeric stock code from a Yahoo-style ticker.

    KLSE Screener addresses stocks by Bursa's own numeric code ("1295"),
    not the Yahoo ".KL" ticker ("1295.KL") this codebase uses elsewhere.
    Returns None for a non-Bursa ticker so the caller can decline the fetch
    rather than querying a code that means nothing on this site.
    """
    upper = ticker.strip().upper()
    if not upper.endswith(".KL"):
        return None
    code = upper[:-3]
    return code or None


def _parse_comments(html_fragment: str) -> list[dict]:
    """Parse one page's comment HTML (top-level comments + threaded replies)
    into a flat list of ``{id, is_reply, user, created, likes, text}`` dicts.

    Each top-level ``<div id="comment-NNN" class="... comment ...">`` nests
    its replies in a sibling ``.comment-replies`` container, each carrying
    its own ``id="comment-NNN"``. Selecting every id'd div (regardless of
    depth) and then scoping each one's own text/timestamp/likes extraction to
    its *direct* ``.comment-right`` child — never a ``.//`` search of the
    whole node — visits every comment and reply exactly once without a
    top-level comment's text absorbing its own replies' text.
    """
    sel = Selector(text=html_fragment)
    out = []
    for node in sel.xpath('//div[starts-with(@id,"comment-")]'):
        cid = node.attrib.get("id", "")
        classes = node.attrib.get("class", "")
        is_reply = "comment-reply" in classes

        content = node.xpath(
            './div[contains(concat(" ", normalize-space(@class), " "), " comment-right ")]'
        )
        if not content:
            continue
        content = content[0]

        user = (
            content.xpath('.//strong[contains(@class,"text-primary")]/text()').get("")
            or ""
        ).strip()

        text_parts = content.xpath(
            './div[contains(@class,"panel-body")]'
            '//div[contains(@class,"message-container")]//text()'
        ).getall()
        text = " ".join(t.strip() for t in text_parts if t.strip())
        if not text:
            continue

        ts_raw = content.xpath(".//*[@data-datetime]/@data-datetime").get()
        created = None
        if ts_raw:
            with contextlib.suppress(ValueError, TypeError):
                created = datetime.strptime(ts_raw.strip(), "%Y-%m-%d %H:%M:%S %z")

        # Reply likes carry a reliable data-count attribute; top-level likes
        # are plain "N Like" text in the first panel-heading. Try the
        # attribute first, fall back to the text pattern.
        likes = None
        count_attr = content.xpath('.//a[contains(@class,"alike")]/@data-count').get()
        if count_attr is not None:
            with contextlib.suppress(ValueError, TypeError):
                likes = int(count_attr)
        if likes is None:
            heading_text = " ".join(
                content.xpath('./div[contains(@class,"panel-heading")][1]//text()').getall()
            )
            m = re.search(r"(\d+)\s*Like", heading_text)
            if m:
                likes = int(m.group(1))

        out.append({
            "id": cid,
            "is_reply": is_reply,
            "user": user or "?",
            "created": created,
            "likes": likes,
            "text": text,
        })
    return out


def _fetch_page(code: str, page: int, timeout: float) -> str | None:
    """Fetch one page of comments as an HTML fragment. ``None`` means the
    fetch itself failed (distinct from a page that parsed to zero comments).

    Page 1 is a full HTML page. Page 2+ requires the XHR marker header or
    the server serves the page shell again instead of the JSON
    ``{"count", "html"}`` fragment the site's own "Load More" button consumes.
    """
    headers = {"User-Agent": _UA}
    if page == 1:
        url = _PAGE1_URL.format(code=code)
    else:
        url = _PAGEN_URL.format(code=code, page=page)
        headers["X-Requested-With"] = "XMLHttpRequest"

    req = Request(url, headers=headers)
    try:
        with urlopen(req, timeout=timeout) as resp:
            raw = _read_capped(resp)
    except HTTPError as exc:
        logger.warning("KLSE Screener fetch failed for stock %s page %d: %s", code, page, exc)
        return None
    except OSError as exc:
        # Covers URLError/TimeoutError/connection resets.
        logger.warning("KLSE Screener fetch failed for stock %s page %d: %s", code, page, exc)
        return None
    except http.client.HTTPException as exc:
        logger.warning("KLSE Screener fetch failed for stock %s page %d: %s", code, page, exc)
        return None

    if page == 1:
        return raw.decode("utf-8", errors="replace")

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.warning("KLSE Screener page %d for stock %s was not JSON: %s", page, code, exc)
        return None
    return payload.get("html") or ""


def _within_window(comments: list[dict], start_date: str | None, end_date: str | None) -> list[dict]:
    """Keep only comments posted in [start_date, end_date] (look-ahead safe).

    No window (both None) leaves the list untouched for live callers. A
    comment whose timestamp failed to parse is dropped in a historical
    window, since we can't prove it isn't from after the as-of date (#1220
    precedent, applied here for consistency with reddit.py/stocktwits.py).
    """
    if not (start_date and end_date):
        return comments
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    return [c for c in comments if in_window(c["created"], start_dt, end_dt)]


def fetch_klse_screener_comments(
    ticker: str,
    max_pages: int = 2,
    timeout: float = 10.0,
    start_date: str | None = None,
    end_date: str | None = None,
) -> str:
    """Fetch retail comments (top-level + threaded replies) for a Bursa
    Malaysia stock from its KLSE Screener discussion thread, and return a
    formatted plaintext block ready for prompt injection.

    Only meaningful for ``.KL`` tickers — KLSE Screener addresses stocks by
    Bursa's own numeric code, derived here from the ticker (e.g. "1295.KL"
    -> "1295"). Returns a placeholder for any other ticker rather than
    querying a code that means nothing on this site.

    Fetches up to ``max_pages`` pages of the thread (~10 top-level comments
    plus their replies per page); most Bursa counters rarely need more than
    one or two to cover a week. When ``start_date``/``end_date`` (yyyy-mm-dd)
    are given, comments are trimmed to that window.
    """
    code = _bursa_code(ticker)
    if code is None:
        return (
            f"<KLSE Screener not applicable: {ticker} is not a Bursa Malaysia "
            f"(.KL) listing>"
        )

    all_comments: list[dict] = []
    any_fetch_succeeded = False
    for page in range(1, max_pages + 1):
        fragment = _fetch_page(code, page, timeout)
        if fragment is None:
            break
        parsed = _parse_comments(fragment)
        if not parsed:
            # Page 1 parsing to zero is a real "no comments" result, not a
            # failure; a later page parsing to zero just means pagination
            # ran out — either way, stop and use what we have.
            any_fetch_succeeded = any_fetch_succeeded or page == 1
            break
        any_fetch_succeeded = True
        all_comments.extend(parsed)

    if not any_fetch_succeeded:
        return (
            f"<KLSE Screener unavailable for {ticker} (stock {code}): fetch "
            f"failed; this is not an absence of comments>"
        )

    # A short thread can repeat its tail comments across a "Load More" page
    # boundary; de-dupe by id rather than assume clean pagination.
    seen: set[str] = set()
    deduped = []
    for c in all_comments:
        if c["id"] in seen:
            continue
        seen.add(c["id"])
        deduped.append(c)

    kept = _within_window(deduped, start_date, end_date)
    if not kept:
        window_note = f" between {start_date} and {end_date}" if start_date and end_date else ""
        return f"<no KLSE Screener comments found for {ticker} (stock {code}){window_note}>"

    kept.sort(key=lambda c: c["created"] or datetime.min.replace(tzinfo=timezone.utc))

    lines = [
        f"## KLSE Screener comments for {ticker} (stock {code}), "
        f"{len(kept)} comment{'s' if len(kept) != 1 else ''}:"
    ]
    for c in kept:
        created_str = c["created"].strftime("%Y-%m-%d %H:%M") if c["created"] else "?"
        kind = "reply" if c["is_reply"] else "comment"
        likes = f"{c['likes']} like{'s' if c['likes'] != 1 else ''}" if c["likes"] else ""
        meta = " · ".join(x for x in [created_str, kind, likes] if x)
        text = c["text"]
        if len(text) > 400:
            text = text[:400] + "…"
        lines.append(f"  [{meta}] @{c['user']}: {text}")

    return "\n".join(lines)
