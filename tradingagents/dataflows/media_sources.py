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
from collections.abc import Iterable, Mapping
from datetime import datetime
from email.utils import parsedate_to_datetime
from types import MappingProxyType
from urllib.error import HTTPError
from urllib.parse import quote, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from tradingagents.logging_utils import safe_exception_type

from .errors import ProviderResponseError, ProviderTransientError

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
GLOBAL_X_ADAPTER_POLICY = MappingProxyType({
    "version": "global-event-x-request-v4",
    "recent_search": MappingProxyType({
        "endpoint": "https://api.x.com/2/tweets/search/recent?{qs}",
        "topic_sort_order": "relevancy",
        "query_language": "en",
        "query_exclusions": ("retweet", "reply"),
        "result_limit": MappingProxyType({
            "default": 10,
            "minimum": 10,
            "maximum": 100,
        }),
        "fields_parameter": "post.fields",
        "post_fields": (
            "created_at",
            "author_id",
            "public_metrics",
        ),
        "expansions": ("author_id",),
        "user_fields": (
            "username",
            "name",
            "description",
            "url",
            "entities",
            "parody",
            "is_identity_verified",
            "verified_type",
            "created_at",
            "public_metrics",
        ),
        "required_post_metrics": (
            "like_count",
            "reply_count",
            "retweet_count",
            "quote_count",
        ),
        "required_user_metrics": MappingProxyType({
            "followers": "followers_count",
            "following": "following_count",
            "activity": "tweet_count",
        }),
        "response_metric_aliases": MappingProxyType({
            "post": MappingProxyType({
                "like_count": ("like_count",),
                "reply_count": ("reply_count",),
                "retweet_count": ("retweet_count", "repost_count"),
                "quote_count": ("quote_count",),
            }),
            "user": MappingProxyType({
                "followers_count": ("followers_count",),
                "following_count": ("following_count",),
                "tweet_count": ("tweet_count", "post_count"),
            }),
        }),
        "known_verified_types": ("none", "blue", "business", "government"),
        "excluded_verified_types": ("business", "government"),
        "profile_screening": MappingProxyType({
            "version": "conservative-organization-signals-v3",
            "profile_url_keys": ("display_url", "expanded_url", "unwound_url", "url"),
            "max_profile_urls": 32,
            "url_normalization": "credential-query-fragment-free-http-s-v1",
            "missing_description": "empty-string",
            "organization_language_pattern": (
                r"\b(agency|association|brand|business|company|corporation|corp|"
                r"department|enterprise|foundation|government|incorporated|"
                r"institute|investor relations|llc|ltd|ministry|newsroom|"
                r"official|organisation|organization|plc|press office|"
                r"public relations|customer support|university)\b"
            ),
            "leadership_language_pattern": (
                r"\b(ceo|cfo|chief executive|co[- ]?founder|coo|cto|founder|"
                r"chair(?:man|woman|person)?|president of)\b"
            ),
            "flags": (
                "description_organization_language",
                "description_leadership_language",
                "name_organization_language",
                "name_leadership_language",
                "parody",
                "profile_url_organization_language",
                "username_organization_language",
                "username_leadership_language",
            ),
        }),
        "automation_risk": MappingProxyType({
            "invalid_score": 1.0,
            "maximum_score": 1.0,
            "young_account_age_days_lt": 30,
            "young_account_weight": 0.4,
            "low_follower_count_lt": 10,
            "high_following_count_gt": 100,
            "low_followers_high_following_weight": 0.3,
            "young_high_volume_age_days_lt": 180,
            "high_tweet_count_gt": 10_000,
            "young_high_volume_weight": 0.2,
        }),
    }),
    "trends": MappingProxyType({
        "endpoint": "https://api.x.com/2/trends/by/woeid/{woeid}?{qs}",
        "result_limit": MappingProxyType({
            "default": 30,
            "minimum": 1,
            "maximum": 50,
        }),
        "fields": ("trend_name", "tweet_count"),
    }),
})


def global_x_adapter_policy_manifest() -> dict[str, object]:
    """Return a JSON-ready projection of the end-to-end global X adapter."""
    def plain(value):
        if isinstance(value, Mapping):
            return {key: plain(item) for key, item in value.items()}
        if isinstance(value, tuple):
            return [plain(item) for item in value]
        return value

    return plain(GLOBAL_X_ADAPTER_POLICY)


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


def _has_nonnegative_metrics(value: object, required: Iterable[str]) -> bool:
    """Validate requested X metric counters without accepting booleans as ints."""
    return isinstance(value, dict) and all(
        isinstance(value.get(name), int)
        and not isinstance(value[name], bool)
        and value[name] >= 0
        for name in required
    )


def _normalize_x_metrics(
    value: object,
    aliases: Mapping[str, Iterable[str]],
) -> dict:
    """Normalize X's Tweet/Post counter aliases into one stable wire shape."""
    if not isinstance(value, dict):
        raise ProviderResponseError("X response metrics schema is invalid")
    normalized = {}
    for canonical, accepted in aliases.items():
        names = tuple(accepted)
        present = [name for name in names if name in value]
        if len(present) != 1:
            raise ProviderResponseError("X response metrics schema is invalid")
        counter = value[present[0]]
        if isinstance(counter, bool) or not isinstance(counter, int) or counter < 0:
            raise ProviderResponseError("X response metrics schema is invalid")
        normalized[canonical] = counter
    return normalized


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
    return urlunsplit((
        parsed.scheme.lower(), netloc, parsed.path or "/", "", "",
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
        logger.info("GET %s failed (%s)", url.split("?")[0], safe_exception_type(exc))
        if _is_transient_http_error(exc):
            raise ProviderTransientError("provider request did not complete") from exc
        raise ProviderResponseError("provider HTTP response was not retryable") from exc
    except (OSError, http.client.HTTPException) as exc:
        logger.info("GET %s failed (%s)", url.split("?")[0], safe_exception_type(exc))
        raise ProviderTransientError("provider request did not complete") from exc
    except (
        json.JSONDecodeError,
        UnicodeDecodeError,
        ProviderResponseError,
    ) as exc:
        logger.info("GET %s failed (%s)", url.split("?")[0], safe_exception_type(exc))
        raise ProviderResponseError("provider JSON response schema was invalid") from exc


def _response_list(data: object, field: str) -> list[dict]:
    """Return an explicit provider collection, rejecting ambiguous envelopes."""
    if (
        not isinstance(data, dict)
        or field not in data
        or not isinstance(data[field], list)
        or any(not isinstance(item, dict) for item in data[field])
    ):
        raise ProviderResponseError("provider JSON response schema was invalid")
    return data[field]


def _required_mapping(value: object) -> dict:
    if not isinstance(value, dict):
        raise ProviderResponseError("provider JSON response item schema was invalid")
    return value


def _required_text(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProviderResponseError("provider JSON response item schema was invalid")
    return value.strip()


def _required_external_id(value: object) -> str:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, str))
        or not str(value).strip()
    ):
        raise ProviderResponseError("provider JSON response item schema was invalid")
    return str(value).strip()


def _required_created_utc(value: object) -> float:
    created_utc = _iso_to_epoch(value if isinstance(value, str) else None)
    if created_utc is None:
        raise ProviderResponseError("provider JSON response item schema was invalid")
    return created_utc


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
        normalized_items = []
        aliases = GLOBAL_X_ADAPTER_POLICY["recent_search"][
            "response_metric_aliases"
        ]["post"]
        for item in items:
            if (
                not isinstance(item.get("id"), str)
                or not item["id"].strip()
                or not isinstance(item.get("author_id"), str)
                or not item["author_id"].strip()
                or not isinstance(item.get("text"), str)
                or not item["text"].strip()
                or _iso_to_epoch(item.get("created_at")) is None
            ):
                raise ProviderResponseError(
                    "X recent-search response item schema is invalid"
                )
            try:
                metrics = _normalize_x_metrics(item.get("public_metrics"), aliases)
            except ProviderResponseError:
                raise ProviderResponseError(
                    "X recent-search response item schema is invalid"
                ) from None
            normalized_items.append({**item, "public_metrics": metrics})
        items = normalized_items
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


def _ticker_news_item(item: ET.Element) -> dict:
    """Validate one generic company-news RSS item without partial salvage."""
    guid_el = item.find("guid")
    link_el = item.find("link")
    title_el = item.find("title")
    date_el = item.find("pubDate")
    desc_el = item.find("description")
    source_el = item.find("source")
    article_url = normalize_public_url(
        link_el.text if link_el is not None else None
    )
    guid = ((guid_el.text if guid_el is not None else "") or "").strip()
    external_id = normalize_public_url(guid) or guid or article_url or ""
    title = ((title_el.text if title_el is not None else "") or "").strip()
    created_utc = _rfc822_to_epoch(
        date_el.text if date_el is not None else None
    )
    if not external_id or not article_url or not _has_meaningful_text(title) \
            or created_utc is None:
        raise ProviderResponseError("company-news RSS item schema is invalid")
    metadata = {"article_url": article_url}
    domain = publisher_domain(
        source_el.get("url") if source_el is not None else None
    )
    if domain:
        metadata["publisher_domain"] = domain
    return {
        "external_id": external_id,
        "title": title,
        "body": _strip_html(desc_el.text if desc_el is not None else ""),
        "created_utc": created_utc,
        "publisher": (
            ((source_el.text if source_el is not None else "") or "").strip()
            or None
        ),
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
    policy = GLOBAL_X_ADAPTER_POLICY["recent_search"]
    risk_policy = policy["automation_risk"]
    metrics = user.get("public_metrics")
    created = _iso_to_epoch(user.get("created_at"))
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
            for key in policy["required_user_metrics"].values()
        )
    ):
        return float(risk_policy["invalid_score"])
    age_days = (now - created) / 86400
    metric_fields = policy["required_user_metrics"]
    followers = metrics[metric_fields["followers"]]
    following = metrics[metric_fields["following"]]
    tweets = metrics[metric_fields["activity"]]
    risk = 0.0
    if age_days < risk_policy["young_account_age_days_lt"]:
        risk += risk_policy["young_account_weight"]
    if (
        followers < risk_policy["low_follower_count_lt"]
        and following > risk_policy["high_following_count_gt"]
    ):
        risk += risk_policy["low_followers_high_following_weight"]
    if (
        age_days < risk_policy["young_high_volume_age_days_lt"]
        and tweets > risk_policy["high_tweet_count_gt"]
    ):
        risk += risk_policy["young_high_volume_weight"]
    return min(float(risk_policy["maximum_score"]), risk)


def _x_author_profile(user: dict, policy: Mapping) -> dict:
    """Validate and freeze the profile fields used by the organization screen."""
    username = user.get("username")
    name = user.get("name")
    description = user.get("description", "")
    profile_url = user.get("url")
    entities = user.get("entities")
    parody = user.get("parody")
    identity_verified = user.get("is_identity_verified")
    if (
        not isinstance(username, str)
        or not username.strip()
        or not isinstance(name, str)
        or not isinstance(description, str)
        or (profile_url is not None and not isinstance(profile_url, str))
        or (entities is not None and not isinstance(entities, dict))
        or not isinstance(parody, bool)
        or not isinstance(identity_verified, bool)
    ):
        raise ProviderResponseError(
            "X recent-search response expanded author profile is invalid"
        )
    screen = policy["profile_screening"]
    if screen["missing_description"] != "empty-string":
        raise RuntimeError("X author profile description policy is unsupported")
    if screen["url_normalization"] != "credential-query-fragment-free-http-s-v1":
        raise RuntimeError("X author profile URL policy is unsupported")
    normalized_profile_url = normalize_public_url(profile_url)
    if (
        isinstance(profile_url, str)
        and profile_url.strip()
        and normalized_profile_url is None
    ):
        raise ProviderResponseError(
            "X recent-search response expanded author profile URL is invalid"
        )
    profile_urls = set()

    def collect_profile_urls(value: object, key: str | None = None) -> None:
        if isinstance(value, dict):
            if key in screen["profile_url_keys"] and "urls" not in value:
                raise ProviderResponseError(
                    "X recent-search response expanded author profile URL is invalid"
                )
            for child_key, child in value.items():
                collect_profile_urls(child, str(child_key))
        elif isinstance(value, list):
            if key in screen["profile_url_keys"]:
                raise ProviderResponseError(
                    "X recent-search response expanded author profile URL is invalid"
                )
            for child in value:
                collect_profile_urls(child, key)
        elif key in screen["profile_url_keys"]:
            if value is None or value == "":
                return
            if not isinstance(value, str):
                raise ProviderResponseError(
                    "X recent-search response expanded author profile URL is invalid"
                )
            normalized = normalize_public_url(value)
            if normalized is None:
                raise ProviderResponseError(
                    "X recent-search response expanded author profile URL is invalid"
                )
            profile_urls.add(normalized)

    collect_profile_urls(entities)
    if len(profile_urls) > int(screen["max_profile_urls"]):
        raise ProviderResponseError(
            "X recent-search response expanded author profile is too large"
        )
    organization_pattern = str(screen["organization_language_pattern"])
    leadership_pattern = str(screen["leadership_language_pattern"])
    signals = []
    if parody:
        signals.append("parody")
    username_text = re.sub(r"[_\-.]+", " ", username.strip())
    for field, text in (
        ("username", username_text),
        ("name", name),
        ("description", description),
    ):
        if re.search(organization_pattern, text, flags=re.IGNORECASE):
            signals.append(f"{field}_organization_language")
        if re.search(leadership_pattern, text, flags=re.IGNORECASE):
            signals.append(f"{field}_leadership_language")
    url_text = " ".join((
        normalized_profile_url or "",
        *sorted(profile_urls),
    ))
    if re.search(organization_pattern, url_text, flags=re.IGNORECASE):
        signals.append("profile_url_organization_language")
    signals = sorted(set(signals))
    if any(value not in screen["flags"] for value in signals):
        raise RuntimeError("X author profile screen emitted an undeclared signal")
    return {
        "author_display_name": name.strip(),
        "author_description": description.strip(),
        "author_profile_url": normalized_profile_url,
        "author_profile_entity_urls": sorted(profile_urls),
        "author_parody": parody,
        "author_identity_verified": identity_verified,
        "profile_screening_complete": True,
        "organization_signals": signals,
    }


def fetch_stocktwits(ticker: str, now: float, limit: int = 30,
                     timeout: float = 10.0) -> list[dict]:
    """Latest StockTwits messages as rows (dedup key: message id; carries the
    user's Bullish/Bearish label)."""
    data = _get_json(_STOCKTWITS_API.format(ticker=ticker.upper()),
                     {"Accept": "application/json"}, timeout)
    messages = _response_list(data, "messages")
    rows = []
    for m in messages[:limit] if limit else messages:
        mid = _required_external_id(m.get("id"))
        user = _required_mapping(m.get("user"))
        entities = _required_mapping(m.get("entities"))
        sentiment_obj = entities.get("sentiment")
        if sentiment_obj is not None and not isinstance(sentiment_obj, dict):
            raise ProviderResponseError("provider JSON response item schema was invalid")
        sentiment = sentiment_obj.get("basic") if sentiment_obj else None
        if sentiment not in {None, "Bullish", "Bearish"}:
            raise ProviderResponseError("provider JSON response item schema was invalid")
        rows.append(_row(
            "stocktwits", mid, ticker, now,
            author=_required_text(user.get("username")),
            sentiment=sentiment,
            created_utc=_required_created_utc(m.get("created_at")),
            body=_required_text(m.get("body")),
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
            if root.tag != f"{{{_ATOM_NS['atom']}}}feed":
                raise ProviderResponseError("Reddit response schema was invalid")
        except HTTPError as exc:
            if _is_transient_http_error(exc):
                raise ProviderTransientError("Reddit request did not complete") from exc
            raise ProviderResponseError("Reddit HTTP response was not usable") from exc
        except (OSError, http.client.HTTPException) as exc:
            raise ProviderTransientError("Reddit request did not complete") from exc
        except (ET.ParseError, ProviderResponseError) as exc:
            raise ProviderResponseError("Reddit response schema was invalid") from exc
        for entry in root.findall("atom:entry", _ATOM_NS):
            id_el = entry.find("atom:id", _ATOM_NS)
            title_el = entry.find("atom:title", _ATOM_NS)
            published_el = entry.find("atom:published", _ATOM_NS)
            content_el = entry.find("atom:content", _ATOM_NS)
            rows.append(_row(
                "reddit",
                _required_text(id_el.text if id_el is not None else None),
                ticker,
                now,
                subreddit=sub,
                created_utc=_required_created_utc(
                    published_el.text if published_el is not None else None
                ),
                title=_required_text(title_el.text if title_el is not None else None),
                body=_strip_html(content_el.text if content_el is not None else ""),
            ))
    return rows


def fetch_bluesky(ticker: str, now: float, limit: int = 50,
                  timeout: float = 10.0) -> list[dict]:
    """Recent Bluesky posts via the keyless public AppView (dedup key: post uri)."""
    qs = urlencode({"q": f"${ticker}", "limit": limit, "sort": "latest"})
    data = _get_json(_BLUESKY_SEARCH.format(qs=qs), {"Accept": "application/json"}, timeout)
    posts = _response_list(data, "posts")
    rows = []
    for p in posts:
        record = _required_mapping(p.get("record"))
        author = _required_mapping(p.get("author"))
        rows.append(_row(
            "bluesky", _required_text(p.get("uri")), ticker, now,
            author=_required_text(author.get("handle")),
            created_utc=_required_created_utc(record.get("createdAt")),
            body=_required_text(record.get("text")),
        ))
    return rows


def fetch_truthsocial(ticker: str, now: float, limit: int = 40,
                      timeout: float = 10.0) -> list[dict]:
    """Truth Social statuses from its Mastodon-compatible search endpoint."""
    headers = {"Accept": "application/json"}
    token = os.environ.get("TRUTHSOCIAL_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    qs = urlencode({"q": ticker, "type": "statuses", "limit": limit})
    data = _get_json(_TRUTHSOCIAL_SEARCH.format(qs=qs), headers, timeout)
    statuses = _response_list(data, "statuses")
    rows = []
    for s in statuses:
        account = _required_mapping(s.get("account"))
        body = _strip_html(_required_text(s.get("content")))
        if not body:
            raise ProviderResponseError("provider JSON response item schema was invalid")
        rows.append(_row(
            "truthsocial", _required_external_id(s.get("id")), ticker, now,
            author=_required_text(account.get("username")),
            created_utc=_required_created_utc(s.get("created_at")),
            body=body,
        ))
    return rows


def fetch_x(ticker: str, now: float, limit: int = 50,
            timeout: float = 10.0) -> list[dict]:
    """Ticker-specific X search, outside the global-event collection contract."""
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
    policy = GLOBAL_X_ADAPTER_POLICY["recent_search"]
    result_limit = policy["result_limit"]
    query_filters = " ".join((
        f"lang:{policy['query_language']}",
        *(f"-is:{value}" for value in policy["query_exclusions"]),
    ))
    qs = urlencode({
        "query": f"({query}) {query_filters}",
        "max_results": min(
            max(limit, int(result_limit["minimum"])),
            int(result_limit["maximum"]),
        ),
        "sort_order": sort_order,
        policy["fields_parameter"]: ",".join(policy["post_fields"]),
        "expansions": ",".join(policy["expansions"]),
        "user.fields": ",".join(policy["user_fields"]),
    })
    data = _get_json(policy["endpoint"].format(qs=qs),
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
    users = {}
    seen_user_ids = set()
    required_author_ids = {tweet["author_id"] for tweet in tweets}
    user_aliases = policy["response_metric_aliases"]["user"]
    for user in raw_users:
        user_id = user.get("id")
        if not isinstance(user_id, str) or not user_id.strip():
            continue
        if user_id not in required_author_ids:
            continue
        if user_id in seen_user_ids:
            raise ProviderResponseError(
                "X recent-search response expanded author schema is invalid"
            )
        seen_user_ids.add(user_id)
        try:
            metrics = _normalize_x_metrics(user.get("public_metrics"), user_aliases)
        except ProviderResponseError:
            continue
        users[user_id] = {**user, "public_metrics": metrics}
    profiles = {}
    for tweet in tweets:
        user = users.get(str(tweet.get("author_id")))
        account_created_utc = (
            _iso_to_epoch(user.get("created_at")) if isinstance(user, dict) else None
        )
        verified_type = (
            user.get("verified_type").strip().lower()
            if isinstance(user, dict)
            and isinstance(user.get("verified_type"), str)
            else None
        )
        if (
            not isinstance(user, dict)
            or not isinstance(user.get("id"), str)
            or user["id"] != tweet["author_id"]
            or not isinstance(user.get("username"), str)
            or not user["username"].strip()
            or account_created_utc is None
            or account_created_utc <= 0
            or verified_type not in policy["known_verified_types"]
            or not _has_nonnegative_metrics(
                user.get("public_metrics"),
                policy["required_user_metrics"].values(),
            )
        ):
            continue
        try:
            profiles[tweet["author_id"]] = _x_author_profile(user, policy)
        except ProviderResponseError:
            # Optional profile fields can be absent even when requested. Such
            # authors are ineligible, but one unscreenable author must not
            # invalidate every other result in the paid response.
            continue
    rows = []
    for t in tweets:
        tid = t.get("id")
        author_id = str(t.get("author_id") or "").strip()
        profile = profiles.get(author_id)
        if profile is None:
            continue
        user = users[author_id]
        account_created_utc = _iso_to_epoch(user.get("created_at"))
        author_metrics = user.get("public_metrics")
        verified_type = user["verified_type"].strip().lower()
        automation_signals_complete = bool(
            author_id
            and str(user.get("id") or "").strip() == author_id
            and isinstance(user.get("username"), str)
            and user["username"].strip()
            and account_created_utc is not None
            and 0 < account_created_utc <= now
            and verified_type in policy["known_verified_types"]
            and isinstance(author_metrics, dict)
            and all(
                isinstance(author_metrics.get(key), int)
                and not isinstance(author_metrics.get(key), bool)
                and author_metrics[key] >= 0
                for key in policy["required_user_metrics"].values()
            )
        )
        # Provider verification and the conservative profile screen are both
        # necessary: an unverified organization is still not public reaction.
        if (
            verified_type in policy["excluded_verified_types"]
            or profile["organization_signals"]
        ):
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
                "verified_type": verified_type,
                **profile,
                "engagement": t.get("public_metrics") or {},
                "author_metrics": author_metrics or {},
                "automation_risk": _automation_risk(user, now),
            },
        ))
    return rows


def fetch_x_topic(
    topic: str,
    query: str,
    now: float,
    limit: int = int(
        GLOBAL_X_ADAPTER_POLICY["recent_search"]["result_limit"]["default"]
    ),
    timeout: float = 10.0,
) -> list[dict]:
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
        sort_order=GLOBAL_X_ADAPTER_POLICY["recent_search"]["topic_sort_order"],
    )


def fetch_x_trends(
    woeid: int,
    limit: int = int(
        GLOBAL_X_ADAPTER_POLICY["trends"]["result_limit"]["default"]
    ),
    timeout: float = 10.0,
) -> list[dict]:
    """Current X trends for a place (WOEID 1 is worldwide).

    Trends are discovery signals only. The poller cross-checks them against
    ranked news headlines before spending a recent-search request, which keeps
    entertainment/sports trends from consuming the small news budget.
    """
    token = (os.environ.get("X_BEARER_TOKEN") or "").strip()
    if not token:
        raise RuntimeError("X bearer token is not configured")
    policy = GLOBAL_X_ADAPTER_POLICY["trends"]
    result_limit = policy["result_limit"]
    qs = urlencode({
        "max_trends": min(
            max(limit, int(result_limit["minimum"])),
            int(result_limit["maximum"]),
        ),
        "trend.fields": ",".join(policy["fields"]),
    })
    data = _get_json(
        policy["endpoint"].format(woeid=woeid, qs=qs),
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
                "Top-news RSS fetch failed (%s:%s)", category, safe_exception_type(exc)
            )
            continue
        except (OSError, http.client.HTTPException) as exc:
            transient_failure_count += 1
            logger.info(
                "Top-news RSS fetch failed (%s:%s)", category, safe_exception_type(exc)
            )
            continue
        except (ET.ParseError, ProviderResponseError) as exc:
            response_failure_count += 1
            logger.info(
                "Top-news RSS fetch failed (%s:%s)", category, safe_exception_type(exc)
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
        (_YAHOO_NEWS_RSS.format(symbol=quote(ticker)), None, _ticker_news_item),
        (_GOOGLE_NEWS_RSS.format(query=quote(google_query)), identities, _google_news_item),
    )
    rows = []
    transient_failure = False
    response_failure = False
    for url, required_identities, item_parser in feeds:
        req = Request(url, headers={"User-Agent": _UA})
        try:
            with urlopen(req, timeout=timeout) as resp:
                channel = _parse_rss_response(resp)
            parsed = [item_parser(item) for item in _rss_channel_items(channel)]
        except HTTPError as exc:
            if _is_transient_http_error(exc):
                transient_failure = True
            else:
                response_failure = True
            continue
        except (OSError, http.client.HTTPException):
            transient_failure = True
            continue
        except (ET.ParseError, ProviderResponseError):
            response_failure = True
            continue
        for normalized in parsed:
            title = normalized["title"]
            description = normalized["body"]
            if required_identities:
                haystack = f"{title} {description}".casefold()
                if not any(identity.casefold() in haystack
                           for identity in required_identities):
                    continue
            rows.append(_row(
                "news", normalized["external_id"], ticker, now,
                author=normalized["publisher"],
                created_utc=normalized["created_utc"],
                title=title,
                body=description,
                metadata=normalized["metadata"],
            ))
        time.sleep(0.5)
    if response_failure:
        raise ProviderResponseError("company-news RSS feed set violated the response contract")
    if transient_failure:
        raise ProviderTransientError(
            "company-news RSS feed set was incomplete; absence was not observed"
        )
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
        prob = float(prices[0])
        market_id = next(
            (
                _required_external_id(m.get(field))
                for field in ("id", "conditionId", "slug")
                if m.get(field) is not None
            ),
            None,
        )
        if market_id is None:
            raise ProviderResponseError("Polymarket market identity was missing")
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
