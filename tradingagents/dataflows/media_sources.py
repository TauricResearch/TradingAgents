"""Structured social/news fetchers for the media poller.

Unlike the prompt-facing fetchers in this package (which return formatted
strings for an analyst), these return lists of row dicts keyed exactly by
``media_store.COLUMNS``, each carrying the provider's stable id so repeated
polls dedup cleanly. They are the data-collection half of the poller; the
storage half is ``media_store``.

Most sources cannot be queried historically (StockTwits exposes only the latest
~30 messages; Reddit/Bluesky/X searches return only recent windows), so the only
way to obtain a historical series is to capture it as it happens.

Token-gated sources:
    truthsocial  -> TRUTHSOCIAL_TOKEN  (Mastodon session bearer; Cloudflare-gated)
    x            -> X_BEARER_TOKEN      (X/Twitter API v2; paid)
The keyless sources (stocktwits, reddit, bluesky, news) need no credentials.
"""

from __future__ import annotations

import hashlib
import html
import http.client
import json
import logging
import math
import os
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime
from urllib.error import HTTPError
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

# Identified User-Agent — matches the project's prompt-facing fetchers. Reddit
# serves this on the RSS endpoint where it 403s anonymous/generic tokens.
_UA = "tradingagents/0.2 (+https://github.com/TauricResearch/TradingAgents)"
_ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}

_STOCKTWITS_API = "https://api.stocktwits.com/api/2/streams/symbol/{ticker}.json"
_REDDIT_RSS = "https://www.reddit.com/r/{sub}/search.rss?{qs}"
_DEFAULT_SUBREDDITS = ("wallstreetbets", "stocks", "investing")
_BLUESKY_SEARCH = "https://public.api.bsky.app/xrpc/app.bsky.feed.searchPosts?{qs}"
_TRUTHSOCIAL_SEARCH = "https://truthsocial.com/api/v2/search?{qs}"
_X_SEARCH = "https://api.x.com/2/tweets/search/recent?{qs}"
_X_TRENDS = "https://api.x.com/2/trends/by/woeid/{woeid}?{qs}"
_X_REQUIRED_POST_METRICS = (
    "like_count", "reply_count", "retweet_count", "quote_count",
)
_X_REQUIRED_USER_METRICS = (
    "followers_count", "following_count", "tweet_count",
)
_YAHOO_NEWS_RSS = (
    "https://feeds.finance.yahoo.com/rss/2.0/headline?s={symbol}&region=US&lang=en-US"
)
_GOOGLE_NEWS_RSS = (
    "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
)
_GOOGLE_TOP_NEWS_RSS = (
    ("general", "US", "https://news.google.com/rss?hl=en-US&gl=US&ceid=US:en"),
    ("business", "US", (
        "https://news.google.com/rss/headlines/section/topic/BUSINESS"
        "?hl=en-US&gl=US&ceid=US:en"
    )),
    ("technology", "US", (
        "https://news.google.com/rss/headlines/section/topic/TECHNOLOGY"
        "?hl=en-US&gl=US&ceid=US:en"
    )),
    ("world", "US", (
        "https://news.google.com/rss/headlines/section/topic/WORLD"
        "?hl=en-US&gl=US&ceid=US:en"
    )),
    ("world", "GB", (
        "https://news.google.com/rss/headlines/section/topic/WORLD"
        "?hl=en-GB&gl=GB&ceid=GB:en"
    )),
    ("world", "IN", (
        "https://news.google.com/rss/headlines/section/topic/WORLD"
        "?hl=en-IN&gl=IN&ceid=IN:en"
    )),
    ("world", "SG", (
        "https://news.google.com/rss/headlines/section/topic/WORLD"
        "?hl=en-SG&gl=SG&ceid=SG:en"
    )),
    ("world", "AU", (
        "https://news.google.com/rss/headlines/section/topic/WORLD"
        "?hl=en-AU&gl=AU&ceid=AU:en"
    )),
)

# Bare short symbols are ordinary words/letters, so a Google News query like
# ``C stock`` can return Alphabet class-C stories instead of Citigroup. These
# identity anchors improve precision without adding 121 yfinance lookups to
# every poll. The aliases are also used to reject obvious mismatches.
_AMBIGUOUS_NEWS_IDENTITIES = {
    "AA": ("Alcoa",),
    "BK": ("Bank of New York Mellon", "BNY Mellon"),
    "C": ("Citigroup", "Citi"),
    "CL": ("Colgate-Palmolive", "Colgate"),
    "DE": ("Deere & Company", "John Deere"),
    "GE": ("GE Aerospace", "General Electric"),
    "GM": ("General Motors",),
    "GS": ("Goldman Sachs",),
    "HD": ("Home Depot",),
    "KO": ("Coca-Cola", "Coca Cola"),
    "LOW": ("Lowe's", "Lowes"),
    "MA": ("Mastercard",),
    "MO": ("Altria",),
    "MP": ("MP Materials",),
    "MS": ("Morgan Stanley",),
    "NOW": ("ServiceNow",),
    "PG": ("Procter & Gamble", "P&G"),
    "PM": ("Philip Morris",),
    "SO": ("Southern Company",),
    "T": ("AT&T",),
    "V": ("Visa",),
}
# Theme/macro news uses Google News search with the theme's free-text query.
_GLOBAL_NEWS_RSS = "https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
_CORPORATE_SOURCE_MARKERS = (
    "business wire", "globenewswire", "official blog", "press release", "pr newswire",
    "newsroom", "accesswire", "ein presswire",
)
_EDITORIAL_SOURCE_MARKERS = (
    "associated press", "ap news", "ars technica", "axios", "bbc", "bloomberg",
    "cnbc", "cnn", "financial times", "forbes", "fortune", "guardian", "marketwatch",
    "new york times", "nikkei", "reuters", "techcrunch", "the verge", "wall street journal",
    "washington post", "wired",
)
_FIRST_PARTY_HEADLINE = re.compile(
    r"^\s*(?:announcing|introducing|meet\b|our\b|today[, :]+we\b|we\b)",
    re.IGNORECASE,
)

# Provider payloads are untrusted and the production collector runs in a small
# VM.  Read at most this many bytes from any one HTTP response before parsing.
_MAX_PROVIDER_RESPONSE_BYTES = 4 * 1024 * 1024


class ProviderResponseError(RuntimeError):
    """A sanitized provider schema failure that must not be retried blindly."""


class ProviderTransientError(RuntimeError):
    """A sanitized transport failure eligible for a bounded free-source retry."""


def _is_transient_http_error(exc: HTTPError) -> bool:
    """Return whether an HTTP response can plausibly succeed on a bounded retry."""
    code = exc.code
    return isinstance(code, int) and not isinstance(code, bool) and (
        code in {408, 429} or 500 <= code <= 599
    )


# Sources that run without a key. 'x' is added by the poller only when a token
# is present (see media poller's source resolution).
KEYLESS_SOURCES = ("stocktwits", "reddit", "bluesky", "truthsocial", "news")


def _iso_to_epoch(iso_str: str | None) -> float | None:
    if not isinstance(iso_str, str) or not iso_str:
        return None
    try:
        normalized = iso_str[:-1] + "+00:00" if iso_str.endswith("Z") else iso_str
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return None
        timestamp = parsed.timestamp()
        return timestamp if math.isfinite(timestamp) else None
    except (OSError, OverflowError, ValueError, TypeError):
        return None


def _rfc822_to_epoch(date_str: str | None) -> float | None:
    """Parse an RSS 2.0 ``pubDate`` (RFC-822, e.g. 'Wed, 28 Jun 2026 12:00:00 GMT')."""
    if not isinstance(date_str, str) or not date_str:
        return None
    try:
        parsed = parsedate_to_datetime(date_str)
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return None
        timestamp = parsed.timestamp()
        return timestamp if math.isfinite(timestamp) else None
    except (OSError, OverflowError, ValueError, TypeError):
        return None


def _strip_html(text: str | None) -> str:
    """Reduce an HTML fragment (Mastodon/RSS body) to collapsed plain text."""
    if not text:
        return ""
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", text)).split())


def _has_meaningful_text(value: object) -> bool:
    """Require at least one Unicode letter or number, not only blank/punctuation."""
    return isinstance(value, str) and any(char.isalnum() for char in value)


def _has_nonnegative_metrics(value: object, required: tuple[str, ...]) -> bool:
    """Validate requested X metric counters without accepting booleans as ints."""
    return isinstance(value, dict) and all(
        isinstance(value.get(name), int)
        and not isinstance(value[name], bool)
        and value[name] >= 0
        for name in required
    )


_TRACKING_QUERY_KEYS = frozenset({
    "fbclid", "gclid", "mc_cid", "mc_eid", "ref", "ref_src",
})


def normalize_public_url(value: str | None) -> str | None:
    """Return a deterministic, credential-free HTTP(S) URL for provenance."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = urlsplit(value.strip())
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
            return None
        if parsed.username is not None or parsed.password is not None:
            return None
        host = parsed.hostname.encode("idna").decode("ascii").lower().rstrip(".")
        port = parsed.port
    except (UnicodeError, ValueError):
        return None
    default_port = (parsed.scheme.lower() == "http" and port == 80) or (
        parsed.scheme.lower() == "https" and port == 443
    )
    netloc = host if port is None or default_port else f"{host}:{port}"
    query = urlencode(sorted(
        (key, item)
        for key, item in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in _TRACKING_QUERY_KEYS
    ))
    return urlunsplit((
        parsed.scheme.lower(), netloc, parsed.path or "/", query, "",
    ))


def publisher_domain(source_url: str | None) -> str | None:
    """Extract a normalized publisher hostname from an RSS ``source`` URL."""
    normalized = normalize_public_url(source_url)
    if not normalized:
        return None
    host = urlsplit(normalized).hostname
    if not host:
        return None
    return host[4:] if host.startswith("www.") else host


def _google_news_provenance(item) -> dict:
    """Capture article and publisher provenance exposed by Google News RSS."""
    link_el = item.find("link")
    source_el = item.find("source")
    metadata = {
        "article_url": normalize_public_url(
            link_el.text if link_el is not None else None
        ),
        "publisher_domain": publisher_domain(
            source_el.get("url") if source_el is not None else None
        ),
    }
    return {key: value for key, value in metadata.items() if value is not None}


def _google_news_content_vintage(
    provider_external_id: str,
    *,
    published_utc: float | None,
    publisher: str,
    title: str,
    body: str,
    provenance: dict,
) -> tuple[str, dict]:
    """Name one exact rendering of a mutable Google News cluster.

    Google reuses a cluster GUID after changing publication time, publisher
    display name, title, or description.  Treating that GUID as an immutable
    row key makes one revised item abort an otherwise healthy query receipt.
    Keep the GUID as provider lineage and use the exact normalized RSS
    rendering as the stored content-vintage identity instead.
    """
    if not isinstance(provider_external_id, str) or not provider_external_id:
        raise ValueError("Google News content requires a provider external ID")
    projected_provenance = {
        key: provenance.get(key)
        for key in ("article_url", "publisher_domain")
        if provenance.get(key) is not None
    }
    payload = {
        "schema_version": 1,
        "provider_external_id": provider_external_id,
        "published_utc": published_utc,
        "publisher": publisher,
        "title": title,
        "body": body,
        "provenance": projected_provenance,
    }
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    vintage_id = f"google_news_v1_{hashlib.sha256(encoded).hexdigest()[:24]}"
    return vintage_id, {
        **projected_provenance,
        "provider_external_id": provider_external_id,
        "content_vintage_id": vintage_id,
        "content_vintage_schema_version": 1,
    }


def looks_company_authored(publisher: str | None, title: str | None) -> bool:
    """Heuristically reject releases and first-person corporate posts.

    Google News appends the publisher to nearly every title, so a trailing
    ``- Publisher`` alone is not evidence of corporate authorship.  First-party
    language is only used for non-editorial publishers, preserving independent
    coverage with headlines such as ``Introducing ... - The Verge``.
    """
    publisher_text = (publisher or "").strip().lower()
    if not publisher_text:
        return False
    if any(marker in publisher_text for marker in _CORPORATE_SOURCE_MARKERS):
        return True
    publisher_key = " ".join(re.findall(r"[a-z0-9]+", publisher_text))
    headline = re.sub(r"\s+-\s+[^-]{2,80}$", "", title or "").strip().lower()
    title_tokens = re.findall(r"[a-z0-9]+", headline)
    publisher_tokens = publisher_key.split()
    publisher_named = any(
        title_tokens[index:index + len(publisher_tokens)] == publisher_tokens
        for index in range(len(title_tokens) - len(publisher_tokens) + 1)
    ) if publisher_tokens else False
    publisher_is_editorial = any(
        marker in publisher_text for marker in _EDITORIAL_SOURCE_MARKERS
    ) or bool(re.search(r"\b(news|newspaper|journal|times)\b", publisher_text))
    return bool(
        publisher_key
        and len(publisher_tokens) <= 3
        and not publisher_is_editorial
        and publisher_named
    ) or bool(
        publisher_key
        and not publisher_is_editorial
        and _FIRST_PARTY_HEADLINE.match(headline)
    )


def _read_bounded(response, *, max_bytes: int | None = None) -> bytes:
    """Read one provider response without allowing unbounded memory growth."""
    limit = _MAX_PROVIDER_RESPONSE_BYTES if max_bytes is None else max_bytes
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ValueError("provider response byte limit must be a positive integer")
    payload = response.read(limit + 1)
    if not isinstance(payload, bytes):
        raise ProviderResponseError("provider response body is not bytes")
    if len(payload) > limit:
        raise ProviderResponseError("provider response exceeded the byte limit")
    return payload


def _parse_rss_response(response) -> ET.Element:
    """Parse an RSS 2.0 response and return its required direct channel."""
    root = ET.fromstring(_read_bounded(response))
    if root.tag != "rss":
        raise ProviderResponseError("provider RSS root is invalid")
    channel = root.find("channel")
    if channel is None:
        raise ProviderResponseError("provider RSS channel is missing")
    for required in ("title", "link", "description"):
        element = channel.find(required)
        if element is None or not _has_meaningful_text(element.text):
            raise ProviderResponseError("provider RSS channel schema is invalid")
    return channel


def _rss_channel_items(channel: ET.Element) -> list[ET.Element]:
    """Return direct RSS 2.0 items and reject nested or namespaced lookalikes."""
    items = channel.findall("item")
    item_like = [
        element
        for element in channel.iter()
        if isinstance(element.tag, str) and element.tag.rsplit("}", 1)[-1] == "item"
    ]
    if len(items) != len(item_like):
        raise ProviderResponseError("provider RSS item structure is invalid")
    return items


def _get_json(url: str, headers: dict, timeout: float):
    req = Request(url, headers={"User-Agent": _UA, **headers})
    try:
        with urlopen(req, timeout=timeout) as resp:
            return json.loads(_read_bounded(resp))
    except HTTPError as exc:
        logger.info("GET %s failed (%s)", url.split("?")[0], type(exc).__name__)
        if _is_transient_http_error(exc):
            return None
        raise ProviderResponseError("provider HTTP response was not retryable") from exc
    except (OSError, http.client.HTTPException) as exc:
        logger.info("GET %s failed (%s)", url.split("?")[0], type(exc).__name__)
        return None
    except (
        json.JSONDecodeError,
        UnicodeDecodeError,
        ProviderResponseError,
    ) as exc:
        logger.info("GET %s failed (%s)", url.split("?")[0], type(exc).__name__)
        raise ProviderResponseError("provider JSON response schema was invalid") from exc


def _x_response_items(data, *, response_name: str) -> list[dict]:
    """Validate an X v2 response envelope without trusting error contents."""
    if not isinstance(data, dict):
        raise ProviderResponseError(f"X {response_name} response schema is invalid")

    errors = data.get("errors")
    if errors is not None:
        if not isinstance(errors, list):
            raise ProviderResponseError(f"X {response_name} response schema is invalid")
        if errors:
            raise ProviderResponseError(f"X {response_name} response reported errors")

    meta = data.get("meta")
    if meta is not None and not isinstance(meta, dict):
        raise ProviderResponseError(f"X {response_name} response schema is invalid")
    result_count = meta.get("result_count") if isinstance(meta, dict) else None
    if result_count is not None and (
        isinstance(result_count, bool)
        or not isinstance(result_count, int)
        or result_count < 0
    ):
        raise ProviderResponseError(f"X {response_name} response schema is invalid")

    items = data.get("data")
    if items is None:
        if result_count == 0 and response_name != "trend":
            return []
        raise ProviderResponseError(f"X {response_name} response omitted result data")
    if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
        raise ProviderResponseError(f"X {response_name} response schema is invalid")
    if result_count is not None and result_count != len(items):
        raise ProviderResponseError(f"X {response_name} response count is inconsistent")
    if response_name == "recent-search":
        for item in items:
            if (
                not isinstance(item.get("id"), str)
                or not item["id"].strip()
                or not isinstance(item.get("author_id"), str)
                or not item["author_id"].strip()
                or not isinstance(item.get("text"), str)
                or not item["text"].strip()
                or _iso_to_epoch(item.get("created_at")) is None
                or not _has_nonnegative_metrics(
                    item.get("public_metrics"), _X_REQUIRED_POST_METRICS
                )
            ):
                raise ProviderResponseError(
                    "X recent-search response item schema is invalid"
                )
    elif response_name == "trend":
        if not items:
            raise ProviderResponseError("X trend response omitted ranked trends")
        for item in items:
            count = item.get("tweet_count")
            if (
                not isinstance(item.get("trend_name"), str)
                or not item["trend_name"].strip()
                or (
                    count is not None
                    and (
                        isinstance(count, bool)
                        or not isinstance(count, int)
                        or count < 0
                    )
                )
            ):
                raise ProviderResponseError("X trend response item schema is invalid")
    return items


def _google_news_item(item: ET.Element) -> dict:
    """Validate and normalize one Google News RSS item without partial salvage."""
    guid_el = item.find("guid")
    link_el = item.find("link")
    title_el = item.find("title")
    date_el = item.find("pubDate")
    desc_el = item.find("description")
    source_el = item.find("source")
    provider_external_id = (
        (guid_el.text if guid_el is not None else None)
        or (link_el.text if link_el is not None else None)
        or ""
    ).strip()
    title = ((title_el.text if title_el is not None else "") or "").strip()
    published_utc = _rfc822_to_epoch(
        date_el.text if date_el is not None else None
    )
    publisher = ((source_el.text if source_el is not None else "") or "").strip()
    provenance = _google_news_provenance(item)
    if (
        not provider_external_id
        or not _has_meaningful_text(title)
        or published_utc is None
        or not publisher
        or not provenance.get("article_url")
        or not provenance.get("publisher_domain")
    ):
        raise ProviderResponseError("Google News RSS item schema is invalid")
    body = _strip_html(desc_el.text if desc_el is not None else "")
    content_vintage_id, metadata = _google_news_content_vintage(
        provider_external_id,
        published_utc=published_utc,
        publisher=publisher,
        title=title,
        body=body,
        provenance=provenance,
    )
    return {
        "external_id": content_vintage_id,
        "title": title,
        "body": body,
        "created_utc": published_utc,
        "publisher": publisher,
        "metadata": metadata,
    }


def _row(source: str, ext_id: str, ticker: str, now: float, *,
         author=None, sentiment=None, subreddit=None,
         created_utc=None, title=None, body="", metadata=None) -> dict:
    row = {
        "source": source, "external_id": ext_id, "ticker": ticker.upper(),
        "subreddit": subreddit, "author": author, "sentiment": sentiment,
        "created_utc": created_utc, "title": title, "body": body,
        "fetched_utc": now,
    }
    if metadata:
        row["metadata"] = metadata
    return row


def _automation_risk(user: dict, now: float) -> float:
    metrics = user.get("public_metrics")
    created = _iso_to_epoch(user.get("created_at"))
    required = ("followers_count", "following_count", "tweet_count")
    if (
        not isinstance(metrics, dict)
        or not isinstance(user.get("username"), str)
        or not user["username"].strip()
        or created is None
        or created <= 0
        or created > now
        or any(
            isinstance(metrics.get(key), bool)
            or not isinstance(metrics.get(key), int)
            or metrics[key] < 0
            for key in required
        )
    ):
        return 1.0
    age_days = (now - created) / 86400
    followers = metrics["followers_count"]
    following = metrics["following_count"]
    tweets = metrics["tweet_count"]
    risk = 0.0
    if age_days < 30:
        risk += 0.4
    if followers < 10 and following > 100:
        risk += 0.3
    if age_days < 180 and tweets > 10_000:
        risk += 0.2
    if not user.get("username"):
        risk += 0.2
    return min(1.0, risk)


def fetch_stocktwits(ticker: str, now: float, limit: int = 30,
                     timeout: float = 10.0) -> list[dict]:
    """Latest StockTwits messages as rows (dedup key: message id; carries the
    user's Bullish/Bearish label)."""
    data = _get_json(_STOCKTWITS_API.format(ticker=ticker.upper()),
                     {"Accept": "application/json"}, timeout)
    messages = data.get("messages", []) if isinstance(data, dict) else []
    rows = []
    for m in messages[:limit] if limit else messages:
        mid = m.get("id")
        if mid is None:
            continue
        sentiment_obj = (m.get("entities") or {}).get("sentiment") or {}
        rows.append(_row(
            "stocktwits", str(mid), ticker, now,
            author=(m.get("user") or {}).get("username"),
            sentiment=sentiment_obj.get("basic") if isinstance(sentiment_obj, dict) else None,
            created_utc=_iso_to_epoch(m.get("created_at")),
            body=(m.get("body") or "").strip(),
        ))
    return rows


def _reddit_qs(ticker: str, limit: int) -> str:
    return urlencode({"q": ticker, "restrict_sr": "on", "sort": "new",
                      "t": "week", "limit": limit})


def fetch_reddit(ticker: str, now: float, subreddits=_DEFAULT_SUBREDDITS,
                 limit_per_sub: int = 25, timeout: float = 10.0,
                 inter_request_delay: float = 1.0) -> list[dict]:
    """Recent Reddit posts mentioning ``ticker`` (Atom search; dedup key: atom id)."""
    rows = []
    for i, sub in enumerate(subreddits):
        if i > 0:
            time.sleep(inter_request_delay)
        url = _REDDIT_RSS.format(sub=sub, qs=_reddit_qs(ticker, limit_per_sub))
        req = Request(url, headers={"User-Agent": _UA})
        try:
            with urlopen(req, timeout=timeout) as resp:
                root = ET.fromstring(_read_bounded(resp))
        except HTTPError as exc:
            if exc.code == 429:
                logger.warning("Reddit 429 for r/%s · %s — backing off 5s", sub, ticker)
                time.sleep(5.0)
            else:
                logger.warning(
                    "Reddit fetch failed for r/%s · %s (%s)",
                    sub, ticker, type(exc).__name__,
                )
            continue
        except (
            OSError, http.client.HTTPException, ET.ParseError, ProviderResponseError,
        ) as exc:
            logger.warning(
                "Reddit fetch failed for r/%s · %s (%s)",
                sub, ticker, type(exc).__name__,
            )
            continue
        for entry in root.findall("atom:entry", _ATOM_NS):
            id_el = entry.find("atom:id", _ATOM_NS)
            title_el = entry.find("atom:title", _ATOM_NS)
            published_el = entry.find("atom:published", _ATOM_NS)
            content_el = entry.find("atom:content", _ATOM_NS)
            ext_id = id_el.text if id_el is not None else None
            if not ext_id:
                continue
            rows.append(_row(
                "reddit", ext_id, ticker, now, subreddit=sub,
                created_utc=_iso_to_epoch(published_el.text if published_el is not None else None),
                title=(title_el.text if title_el is not None else "") or "",
                body=_strip_html(content_el.text if content_el is not None else ""),
            ))
    return rows


def fetch_bluesky(ticker: str, now: float, limit: int = 50,
                  timeout: float = 10.0) -> list[dict]:
    """Recent Bluesky posts via the keyless public AppView (dedup key: post uri)."""
    qs = urlencode({"q": f"${ticker}", "limit": limit, "sort": "latest"})
    data = _get_json(_BLUESKY_SEARCH.format(qs=qs), {"Accept": "application/json"}, timeout)
    posts = data.get("posts", []) if isinstance(data, dict) else []
    rows = []
    for p in posts:
        uri = p.get("uri")
        if not uri:
            continue
        record = p.get("record") or {}
        rows.append(_row(
            "bluesky", uri, ticker, now,
            author=(p.get("author") or {}).get("handle"),
            created_utc=_iso_to_epoch(record.get("createdAt")),
            body=(record.get("text") or "").strip(),
        ))
    return rows


def fetch_truthsocial(ticker: str, now: float, limit: int = 40,
                      timeout: float = 10.0) -> list[dict]:
    """Truth Social statuses (Mastodon v2 search). Needs TRUTHSOCIAL_TOKEN; degrades silently."""
    headers = {"Accept": "application/json"}
    token = os.environ.get("TRUTHSOCIAL_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    qs = urlencode({"q": ticker, "type": "statuses", "limit": limit})
    data = _get_json(_TRUTHSOCIAL_SEARCH.format(qs=qs), headers, timeout)
    statuses = data.get("statuses", []) if isinstance(data, dict) else []
    rows = []
    for s in statuses:
        sid = s.get("id")
        if sid is None:
            continue
        rows.append(_row(
            "truthsocial", str(sid), ticker, now,
            author=(s.get("account") or {}).get("username"),
            created_utc=_iso_to_epoch(s.get("created_at")),
            body=_strip_html(s.get("content")),
        ))
    return rows


def fetch_x(ticker: str, now: float, limit: int = 50,
            timeout: float = 10.0) -> list[dict]:
    """X/Twitter recent search (API v2). No-ops without X_BEARER_TOKEN."""
    return _fetch_x_search(
        query=f"${ticker}",
        label=ticker,
        now=now,
        limit=limit,
        timeout=timeout,
        sort_order="recency",
    )


def _fetch_x_search(query: str, label: str, now: float, limit: int,
                    timeout: float, sort_order: str) -> list[dict]:
    """Run one bounded X recent-search query and return media-store rows."""
    token = (os.environ.get("X_BEARER_TOKEN") or "").strip()
    if not token:
        raise RuntimeError("X bearer token is not configured")
    qs = urlencode({
        "query": f"({query}) lang:en -is:retweet -is:reply",
        "max_results": min(max(limit, 10), 100),
        "sort_order": sort_order,
        "tweet.fields": "created_at,author_id,public_metrics,possibly_sensitive,referenced_tweets",
        "expansions": "author_id",
        "user.fields": "username,verified_type,created_at,public_metrics",
    })
    data = _get_json(_X_SEARCH.format(qs=qs),
                     {"Authorization": f"Bearer {token}", "Accept": "application/json"},
                     timeout)
    if data is None:
        raise ProviderTransientError(
            "X recent-search request failed; cursor was not advanced"
        )
    tweets = _x_response_items(data, response_name="recent-search")
    includes = data.get("includes")
    if includes is not None and not isinstance(includes, dict):
        raise ProviderResponseError("X recent-search response schema is invalid")
    if tweets and not isinstance(includes, dict):
        raise ProviderResponseError("X recent-search response omitted expanded users")
    raw_users = includes.get("users", []) if isinstance(includes, dict) else []
    if not isinstance(raw_users, list) or any(
        not isinstance(user, dict) for user in raw_users
    ):
        raise ProviderResponseError("X recent-search response schema is invalid")
    users = {
        str(user.get("id")): user
        for user in raw_users
        if user.get("id") is not None
    }
    for tweet in tweets:
        user = users.get(str(tweet.get("author_id")))
        account_created_utc = (
            _iso_to_epoch(user.get("created_at")) if isinstance(user, dict) else None
        )
        if (
            not isinstance(user, dict)
            or not isinstance(user.get("id"), str)
            or user["id"] != tweet["author_id"]
            or not isinstance(user.get("username"), str)
            or not user["username"].strip()
            or account_created_utc is None
            or account_created_utc <= 0
            or not _has_nonnegative_metrics(
                user.get("public_metrics"), _X_REQUIRED_USER_METRICS
            )
        ):
            raise ProviderResponseError(
                "X recent-search response expanded author schema is invalid"
            )
    rows = []
    for t in tweets:
        tid = t.get("id")
        user = users.get(str(t.get("author_id")), {})
        author_id = str(t.get("author_id") or "").strip()
        account_created_utc = _iso_to_epoch(user.get("created_at"))
        author_metrics = user.get("public_metrics")
        automation_signals_complete = bool(
            author_id
            and str(user.get("id") or "").strip() == author_id
            and isinstance(user.get("username"), str)
            and user["username"].strip()
            and account_created_utc is not None
            and 0 < account_created_utc <= now
            and isinstance(author_metrics, dict)
            and all(
                isinstance(author_metrics.get(key), int)
                and not isinstance(author_metrics.get(key), bool)
                and author_metrics[key] >= 0
                for key in ("followers_count", "following_count", "tweet_count")
            )
        )
        # Official business accounts are announcements, not public sentiment.
        if user.get("verified_type") == "business":
            continue
        rows.append(_row(
            "x", str(tid), label, now,
            author=user.get("username") or t.get("author_id"),
            created_utc=_iso_to_epoch(t.get("created_at")),
            body=(t.get("text") or "").strip(),
            metadata={
                "evidence_role": "unverified_public_reaction",
                "author_id": author_id or None,
                "author_username": user.get("username"),
                "account_created_utc": account_created_utc,
                "automation_signals_complete": automation_signals_complete,
                "verified_type": user.get("verified_type"),
                "engagement": t.get("public_metrics") or {},
                "author_metrics": author_metrics or {},
                "automation_risk": _automation_risk(user, now),
                "possibly_sensitive": bool(t.get("possibly_sensitive")),
                "referenced_tweets": t.get("referenced_tweets") or [],
            },
        ))
    return rows


def fetch_x_topic(topic: str, query: str, now: float, limit: int = 10,
                  timeout: float = 10.0) -> list[dict]:
    """Fetch broad, market-relevant X discussion under a pseudo ticker.

    Topic rows use ``@<topic>`` instead of a company ticker. Relevancy ordering
    favors the conversations X considers most meaningful while the small result
    cap keeps pay-per-read costs bounded.
    """
    return _fetch_x_search(
        query=query,
        label=f"@{topic}",
        now=now,
        limit=limit,
        timeout=timeout,
        sort_order="relevancy",
    )


def fetch_x_trends(woeid: int, limit: int = 30,
                   timeout: float = 10.0) -> list[dict]:
    """Current X trends for a place (WOEID 1 is worldwide).

    Trends are discovery signals only. The poller cross-checks them against
    ranked news headlines before spending a recent-search request, which keeps
    entertainment/sports trends from consuming the small news budget.
    """
    token = (os.environ.get("X_BEARER_TOKEN") or "").strip()
    if not token:
        raise RuntimeError("X bearer token is not configured")
    qs = urlencode({
        "max_trends": min(max(limit, 1), 50),
        "trend.fields": "trend_name,tweet_count",
    })
    data = _get_json(
        _X_TRENDS.format(woeid=woeid, qs=qs),
        {"Authorization": f"Bearer {token}", "Accept": "application/json"},
        timeout,
    )
    if data is None:
        raise ProviderTransientError("X trend request failed; cursor was not advanced")
    trends = _x_response_items(data, response_name="trend")
    return [
        {
            "name": (trend.get("trend_name") or "").strip(),
            "tweet_count": trend.get("tweet_count"),
        }
        for trend in trends
        if trend.get("trend_name")
    ]


def fetch_top_news_headlines(limit_per_feed: int = 12,
                             timeout: float = 10.0) -> list[dict]:
    """Ranked, query-free Google News headlines used for topic discovery.

    This reads the public top/general, business, technology, and world feeds;
    it does not search for a company, person, ticker, or predefined event.
    Duplicate articles are deliberately retained across feeds because their
    cross-category appearance is a useful importance signal to the selector.
    """
    if (
        isinstance(limit_per_feed, bool)
        or not isinstance(limit_per_feed, int)
        or limit_per_feed < 1
    ):
        raise ValueError("top-news result limit must be a positive integer")
    headlines = []
    observed_feed_count = 0
    transient_failure_count = 0
    response_failure_count = 0
    for category, region, url in _GOOGLE_TOP_NEWS_RSS:
        req = Request(url, headers={"User-Agent": _UA})
        try:
            with urlopen(req, timeout=timeout) as resp:
                channel = _parse_rss_response(resp)
            items = _rss_channel_items(channel)
            if not items:
                raise ProviderResponseError("top-news RSS feed contained no ranked items")
            parsed = [_google_news_item(item) for item in items[:limit_per_feed]]
        except HTTPError as exc:
            if _is_transient_http_error(exc):
                transient_failure_count += 1
            else:
                response_failure_count += 1
            logger.info(
                "Top-news RSS fetch failed (%s:%s)", category, type(exc).__name__
            )
            continue
        except (OSError, http.client.HTTPException) as exc:
            transient_failure_count += 1
            logger.info(
                "Top-news RSS fetch failed (%s:%s)", category, type(exc).__name__
            )
            continue
        except (ET.ParseError, ProviderResponseError) as exc:
            response_failure_count += 1
            logger.info(
                "Top-news RSS fetch failed (%s:%s)", category, type(exc).__name__
            )
            continue
        observed_feed_count += 1
        for rank, normalized in enumerate(parsed):
            headlines.append({
                **normalized,
                "category": category,
                "region": region,
                "rank": rank,
            })
    if response_failure_count:
        raise ProviderResponseError(
            "top-news discovery feed set violated the response contract"
        )
    if transient_failure_count:
        raise ProviderTransientError(
            "top-news discovery feed set was incomplete; absence was not observed"
        )
    if observed_feed_count == 0:  # defensive: the frozen registry itself cannot be empty
        raise ProviderResponseError("top-news discovery has no configured feeds")
    return headlines


def fetch_news(ticker: str, now: float, timeout: float = 10.0) -> list[dict]:
    """Company headlines from keyless RSS 2.0 feeds (Yahoo, Google News; dedup key: guid/link)."""
    ticker = ticker.strip().upper()
    identities = _AMBIGUOUS_NEWS_IDENTITIES.get(ticker)
    google_query = f'"{identities[0]}" stock {ticker}' if identities else f'"{ticker}" stock'
    feeds = (
        (_YAHOO_NEWS_RSS.format(symbol=quote(ticker)), None),
        (_GOOGLE_NEWS_RSS.format(query=quote(google_query)), identities),
    )
    rows = []
    for url, required_identities in feeds:
        req = Request(url, headers={"User-Agent": _UA})
        try:
            with urlopen(req, timeout=timeout) as resp:
                channel = _parse_rss_response(resp)
        except (
            OSError,
            http.client.HTTPException,
            ET.ParseError,
            HTTPError,
            ProviderResponseError,
        ) as exc:
            logger.warning(
                "News RSS fetch failed (%s:%s)",
                url.split("?")[0], type(exc).__name__,
            )
            continue
        for item in channel.iter("item"):
            guid_el = item.find("guid")
            link_el = item.find("link")
            title_el = item.find("title")
            date_el = item.find("pubDate")
            desc_el = item.find("description")
            title = (title_el.text if title_el is not None else "") or ""
            description = _strip_html(desc_el.text if desc_el is not None else "")
            if required_identities:
                haystack = f"{title} {description}".casefold()
                if not any(identity.casefold() in haystack
                           for identity in required_identities):
                    continue
            ext_id = (guid_el.text if guid_el is not None else None) or \
                     (link_el.text if link_el is not None else None)
            if not ext_id:
                continue
            rows.append(_row(
                "news", ext_id, ticker, now,
                created_utc=_rfc822_to_epoch(date_el.text if date_el is not None else None),
                title=title,
                body=description,
            ))
        time.sleep(0.5)
    return rows


# Registry: source name → fetcher. 'x' is keyed in but no-ops without a token.
FETCHERS = {
    "stocktwits": fetch_stocktwits,
    "reddit": fetch_reddit,
    "bluesky": fetch_bluesky,
    "truthsocial": fetch_truthsocial,
    "news": fetch_news,
    "x": fetch_x,
}
SELECTABLE_SOURCES = tuple(FETCHERS)


# --------------------------------------------------------------------------- #
# Macro snapshotting — not ticker-keyed; captured per theme once per cycle.
# These sources cannot be backfilled (Polymarket exposes only live odds; a
# global-news search at a past date is not reproducible), so the poller records
# them as they happen, exactly like the social sources.
# --------------------------------------------------------------------------- #
def fetch_global_news(query: str, now: float, theme: str,
                      timeout: float = 10.0, limit: int = 25) -> list[dict]:
    """Global/macro headlines for a free-text ``query`` (Google News RSS).

    Stored in the shared ``media_posts`` table under ``source='globalnews'`` and
    a namespaced pseudo-ticker ``@<theme>`` so the backtest loader can pull a
    theme's headline window the same way it pulls a ticker's. The provider GUID
    is retained in metadata while the row key identifies one exact content vintage.
    """
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ValueError("global-news result limit must be a positive integer")
    url = _GLOBAL_NEWS_RSS.format(q=quote(query))
    req = Request(url, headers={"User-Agent": _UA})
    try:
        with urlopen(req, timeout=timeout) as resp:
            channel = _parse_rss_response(resp)
    except HTTPError as exc:
        if not _is_transient_http_error(exc):
            raise ProviderResponseError(
                "global-news HTTP response was not retryable; cursor was not advanced"
            ) from exc
        raise ProviderTransientError(
            "global-news transport failed; cursor was not advanced"
        ) from exc
    except (OSError, http.client.HTTPException) as exc:
        raise ProviderTransientError(
            "global-news transport failed; cursor was not advanced"
        ) from exc
    except (ET.ParseError, ProviderResponseError) as exc:
        raise ProviderResponseError(
            "global-news response schema was invalid; cursor was not advanced"
        ) from exc
    rows = []
    for item in _rss_channel_items(channel)[:limit]:
        normalized = _google_news_item(item)
        rows.append(_row(
            "globalnews", normalized["external_id"], f"@{theme}", now,
            author=normalized["publisher"],
            created_utc=normalized["created_utc"],
            title=normalized["title"],
            body=normalized["body"],
            metadata=normalized["metadata"],
        ))
    return rows


def fetch_polymarket_odds(topic: str, now: float, theme: str,
                          limit: int = 10) -> list[dict]:
    """Live implied probabilities for ``topic`` as odds rows (keyed by theme).

    One row per open market, captured at ``now`` — repeated hourly this builds
    the probability time series the macro brief needs at any past trade date.
    Rows match ``media_store.ODDS_COLUMNS``.
    """
    from tradingagents.dataflows.polymarket import _parse_json_list, iter_forward_markets

    rows = []
    for m in iter_forward_markets(topic, limit):
        prices = _parse_json_list(m.get("outcomePrices"))
        try:
            prob = float(prices[0])
        except (ValueError, IndexError):
            continue
        market_id = str(m.get("id") or m.get("conditionId") or m.get("slug")
                        or m.get("question") or "")
        if not market_id:
            continue
        rows.append({
            "theme": theme,
            "topic": topic,
            "market_id": market_id,
            "captured_utc": now,
            "question": m.get("question"),
            "probability": prob,
            "volume": float(m.get("volumeNum") or 0),
            "resolution_utc": _iso_to_epoch(m.get("endDate")),
        })
    return rows
