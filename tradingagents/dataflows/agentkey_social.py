"""AgentKey-backed social channels for the sentiment analyst.

Adds Chinese / international social platforms on top of the analyst's existing
US-centric sources (StockTwits, Reddit, Yahoo news). Channels are split into:

  * Base layer (always, when AgentKey is configured): Weibo, Zhihu — the closest
    Chinese-market analogues to StockTwits/Reddit retail + deep-discussion flow.
  * Consumer layer (only for consumer-brand sectors): Xiaohongshu, Douyin — these
    are product/lifestyle platforms whose buzz is a meaningful alt-data signal for
    consumer names (beverages, autos, electronics, apparel, restaurants) and pure
    noise for industrial / B2B / financial names, so they are industry-gated.

Each fetcher returns a formatted plaintext block ready for prompt injection, and
degrades to a clear ``<… unavailable: reason>`` placeholder on any failure — the
caller never special-cases exceptions or ``None`` (same contract as
``stocktwits.py`` / ``reddit.py``). Parsers are tolerant of the raw, unnormalized
upstream JSON: missing fields are skipped, never fatal.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from tradingagents.dataflows.agentkey_client import AgentKeyError, dispatch, is_configured

logger = logging.getLogger(__name__)

# Channel identifiers used across selection + fetch dispatch.
WEIBO = "weibo"
ZHIHU = "zhihu"
XIAOHONGSHU = "xiaohongshu"
DOUYIN = "douyin"

BASE_CHANNELS = (WEIBO, ZHIHU)
CONSUMER_CHANNELS = (XIAOHONGSHU, DOUYIN)

# yfinance sector strings that are squarely consumer-brand.
_CONSUMER_SECTORS = {"consumer cyclical", "consumer defensive"}
# Industry substrings that flag a consumer brand even when the sector is broad
# (e.g. Apple's sector is "Technology" but its industry is "Consumer Electronics").
_CONSUMER_INDUSTRY_KEYWORDS = (
    "consumer electronic", "apparel", "footwear", "luxury", "restaurant",
    "beverage", "brewer", "winer", "distiller", "auto manufacturer", "vehicle",
    "cosmetic", "personal product", "packaged food", "household", "tobacco",
    "leisure", "gambling", "gaming", "retail", "furnishing", "travel",
    "lodging", "airline", "confection", "food product", "specialty",
)

_HTML_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")

# Trailing corporate-form tokens stripped from a company name before searching.
# yfinance returns full legal names ("Tencent Holdings Limited", "NVIDIA
# Corporation"); social platforms index the bare brand, so the legal suffix
# tanks recall and pulls in registry/compliance noise. Stripping it is a
# general win for every ticker, CN and US alike.
_CORP_SUFFIX_TOKENS = {
    "inc", "incorporated", "corp", "corporation", "co", "company", "ltd",
    "limited", "holdings", "holding", "group", "plc", "llc", "lp", "sa",
    "ag", "nv", "se", "kgaa", "adr", "ads", "class", "cl", "the",
}


def normalize_search_name(name: str) -> str:
    """Strip trailing corporate-form tokens to get a searchable brand name.

    E.g. ``"Tencent Holdings Limited" → "Tencent"``,
    ``"Kweichow Moutai Co., Ltd." → "Kweichow Moutai"``. Falls back to the
    original name if stripping would empty it.
    """
    tokens = _WS.split((name or "").strip())
    while len(tokens) > 1:
        bare = re.sub(r"[^\w&]", "", tokens[-1]).lower()
        if bare in _CORP_SUFFIX_TOKENS or (len(bare) == 1 and bare.isalpha()):
            tokens.pop()
        else:
            break
    cleaned = " ".join(tokens).strip(" ,.")
    return cleaned or (name or "").strip()


# ---------------------------------------------------------------------------
# Industry-adaptive channel selection
# ---------------------------------------------------------------------------
def is_consumer_brand(sector: Optional[str], industry: Optional[str]) -> bool:
    """Whether a ticker's sector/industry warrants consumer-platform signals."""
    if sector and sector.strip().lower() in _CONSUMER_SECTORS:
        return True
    if industry:
        ind = industry.lower()
        return any(kw in ind for kw in _CONSUMER_INDUSTRY_KEYWORDS)
    return False


def select_channels(sector: Optional[str], industry: Optional[str]) -> List[str]:
    """Return the AgentKey channels to query for an instrument.

    Weibo + Zhihu always; Xiaohongshu + Douyin only for consumer brands.
    """
    channels = list(BASE_CHANNELS)
    if is_consumer_brand(sector, industry):
        channels.extend(CONSUMER_CHANNELS)
    return channels


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------
def _clean(text: Any, max_len: int = 280) -> str:
    """Strip HTML tags, collapse whitespace, and truncate."""
    s = _WS.sub(" ", _HTML_TAG.sub(" ", str(text or ""))).strip()
    return (s[:max_len] + "…") if len(s) > max_len else s


def _unix_to_date(value: Any) -> str:
    """Best-effort unix-seconds → YYYY-MM-DD; pass through anything else."""
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc).strftime("%Y-%m-%d")
    except (TypeError, ValueError, OSError):
        return str(value or "")


def _engagement(*pairs) -> str:
    """Render non-empty (label, count) pairs as 'like 12 · comment 3'."""
    return " · ".join(f"{label} {count}" for label, count in pairs if count)


# ---------------------------------------------------------------------------
# Weibo — retail-investor chatter (StockTwits/Twitter analogue for CN market)
# ---------------------------------------------------------------------------
def _iter_weibo_posts(node: Any) -> List[Dict[str, Any]]:
    """Walk the nested Weibo search payload, collecting status dicts.

    A status is any dict carrying both a ``text`` body and a ``user`` object.
    The search response mixes card containers (``items``) and status objects
    (``data``), so we recurse rather than assume a flat list.
    """
    found: List[Dict[str, Any]] = []
    if isinstance(node, dict):
        if isinstance(node.get("text"), str) and isinstance(node.get("user"), dict):
            found.append(node)
        for key in ("items", "data", "card_group", "cards"):
            if key in node:
                found.extend(_iter_weibo_posts(node[key]))
    elif isinstance(node, list):
        for item in node:
            found.extend(_iter_weibo_posts(item))
    return found


def fetch_weibo_posts(query: str, limit: int = 15, timeout: float = 15.0) -> str:
    """Fetch recent Weibo posts mentioning ``query`` as a formatted block."""
    try:
        payload = dispatch("weibo/app/fetch_search_all", {"query": query, "search_type": 1}, timeout)
    except AgentKeyError as exc:
        logger.warning("Weibo fetch failed for %s: %s", query, exc)
        return f"<weibo unavailable: {exc}>"

    posts = _iter_weibo_posts(payload.get("data"))
    if not posts:
        return f"<no Weibo posts found for '{query}'>"

    lines = []
    for p in posts[:limit]:
        user = (p.get("user") or {}).get("screen_name", "?")
        when = _clean(p.get("created_at"), 40)
        region = p.get("region_name") or ""
        eng = _engagement(
            ("repost", p.get("reposts_count")),
            ("comment", p.get("comments_count")),
            ("like", p.get("attitudes_count")),
        )
        meta = " · ".join(x for x in (when, region, eng) if x)
        lines.append(f"[@{user} · {meta}] {_clean(p.get('text'))}")
    return f"{len(lines)} most-relevant Weibo posts for '{query}':\n\n" + "\n".join(lines)


# ---------------------------------------------------------------------------
# Zhihu — deep Q&A / column discussion (Reddit-deep analogue for CN market)
# ---------------------------------------------------------------------------
def fetch_zhihu_discussions(query: str, limit: int = 8, timeout: float = 15.0) -> str:
    """Fetch Zhihu answers/articles about ``query`` as a formatted block."""
    try:
        payload = dispatch(
            "zhihu/web/fetch_article_search_v3", {"keyword": query, "limit": str(limit * 2)}, timeout
        )
    except AgentKeyError as exc:
        logger.warning("Zhihu fetch failed for %s: %s", query, exc)
        return f"<zhihu unavailable: {exc}>"

    data = payload.get("data") or {}
    results = data.get("data") if isinstance(data, dict) else None
    if not isinstance(results, list):
        return f"<no Zhihu discussion found for '{query}'>"

    lines = []
    for entry in results:
        obj = entry.get("object") if isinstance(entry, dict) else None
        if not isinstance(obj, dict) or obj.get("type") not in ("answer", "article"):
            continue
        author = (obj.get("author") or {}).get("name", "?")
        title = _clean(obj.get("title"), 90)
        excerpt = _clean(obj.get("excerpt") or obj.get("excerpt_new"), 220)
        when = _unix_to_date(obj.get("created_time") or obj.get("updated_time"))
        eng = _engagement(("upvote", obj.get("voteup_count")), ("comment", obj.get("comment_count")))
        meta = " · ".join(x for x in (obj.get("type"), author, when, eng) if x)
        lines.append(f"[{meta}] {title}\n   {excerpt}")
        if len(lines) >= limit:
            break

    if not lines:
        return f"<no Zhihu discussion found for '{query}'>"
    return f"{len(lines)} Zhihu answers/articles for '{query}':\n\n" + "\n".join(lines)


# ---------------------------------------------------------------------------
# Consumer layer — Xiaohongshu & Douyin (industry-gated alt-data)
# ---------------------------------------------------------------------------
def _first_item_list(node: Any) -> List[Dict[str, Any]]:
    """Find the first list-of-dicts under common container keys, best-effort.

    Used for the consumer endpoints whose exact response shape we don't pin to a
    grounded fixture; tolerant by design so a shape change degrades to fewer
    extracted items rather than an exception.
    """
    if isinstance(node, list):
        return [x for x in node if isinstance(x, dict)]
    if isinstance(node, dict):
        for key in ("items", "list", "data", "notes", "note_list", "aweme_list", "result"):
            if key in node:
                found = _first_item_list(node[key])
                if found:
                    return found
    return []


def _extract_text(item: Dict[str, Any]) -> str:
    for key in ("desc", "title", "content", "text", "note_name", "share_text"):
        val = item.get(key)
        if isinstance(val, str) and val.strip():
            return _clean(val)
    nc = item.get("note_card")
    if isinstance(nc, dict):
        return _clean(nc.get("display_title") or nc.get("desc"))
    return ""


def _extract_author(item: Dict[str, Any]) -> str:
    for key in ("nickname", "author", "user_name", "name"):
        val = item.get(key)
        if isinstance(val, str) and val.strip():
            return val
        if isinstance(val, dict):
            return val.get("nickname") or val.get("name") or "?"
    return "?"


def _extract_engagement(item: Dict[str, Any]) -> str:
    return _engagement(
        ("like", item.get("liked_count") or item.get("digg_count") or item.get("like_count")),
        ("comment", item.get("comment_count") or item.get("comments_count")),
        ("share", item.get("share_count") or item.get("shared_count")),
    )


def _fetch_consumer(channel: str, path: str, query_field: str, query: str, limit: int, timeout: float) -> str:
    try:
        payload = dispatch(path, {query_field: query}, timeout)
    except AgentKeyError as exc:
        logger.warning("%s fetch failed for %s: %s", channel, query, exc)
        return f"<{channel} unavailable: {exc}>"

    items = _first_item_list(payload.get("data", payload))
    lines = []
    for item in items:
        text = _extract_text(item)
        if not text:
            continue
        meta = " · ".join(x for x in (_extract_author(item), _extract_engagement(item)) if x)
        lines.append(f"[{meta}] {text}")
        if len(lines) >= limit:
            break
    if not lines:
        return f"<no {channel} posts found for '{query}'>"
    return f"{len(lines)} {channel} posts for '{query}':\n\n" + "\n".join(lines)


def fetch_xiaohongshu_notes(query: str, limit: int = 10, timeout: float = 15.0) -> str:
    """Fetch Xiaohongshu (RED) notes mentioning ``query`` — consumer buzz signal."""
    return _fetch_consumer(XIAOHONGSHU, "xiaohongshu/search_notes", "keyword", query, limit, timeout)


def fetch_douyin_videos(query: str, limit: int = 10, timeout: float = 15.0) -> str:
    """Fetch Douyin videos mentioning ``query`` — consumer buzz signal."""
    return _fetch_consumer(
        DOUYIN, "douyin/app/v3/fetch_general_search_result", "keyword", query, limit, timeout
    )


# ---------------------------------------------------------------------------
# Orchestration — assemble the prompt section for the sentiment analyst
# ---------------------------------------------------------------------------
_FETCHERS = {
    WEIBO: fetch_weibo_posts,
    ZHIHU: fetch_zhihu_discussions,
    XIAOHONGSHU: fetch_xiaohongshu_notes,
    DOUYIN: fetch_douyin_videos,
}

_CHANNEL_TITLES = {
    WEIBO: "Weibo (微博) — Chinese retail-investor chatter",
    ZHIHU: "Zhihu (知乎) — Chinese deep Q&A / investment-thesis discussion",
    XIAOHONGSHU: "Xiaohongshu (小红书) — consumer product buzz (alt-data)",
    DOUYIN: "Douyin (抖音) — consumer short-video buzz (alt-data)",
}


def build_agentkey_social_section(
    query: str,
    sector: Optional[str] = None,
    industry: Optional[str] = None,
) -> str:
    """Assemble the AgentKey social section for prompt injection.

    Returns ``""`` when AgentKey is not configured, so existing (US-only) runs are
    unchanged and incur no cost. Otherwise fetches the industry-selected channels
    and wraps each in a ``<start_of_{channel}>…<end_of_{channel}>`` block.
    """
    if not is_configured():
        return ""

    query = normalize_search_name(query)
    channels = select_channels(sector, industry)
    parts = [
        "### Chinese / international social platforms — via AgentKey",
        f"Searched by company name '{query}'. Most valuable for A-share / HK / China-listed "
        "or China-exposed names; may be sparse for names with little Chinese-language coverage.",
    ]
    for channel in channels:
        block = _FETCHERS[channel](query)
        parts.append(
            f"\n#### {_CHANNEL_TITLES[channel]}\n"
            f"<start_of_{channel}>\n{block}\n<end_of_{channel}>"
        )
    return "\n".join(parts)
