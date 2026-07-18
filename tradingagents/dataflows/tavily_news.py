"""Tavily-backed news search with conservative API usage defaults."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

from tradingagents.observability.provenance import capture_vendor_raw

from .config import get_config
from .ticker_utils import is_a_share_ticker, to_akshare_symbol

API_URL = "https://api.tavily.com/search"


class TavilyUnavailableError(Exception):
    """Raised when Tavily is not configured or cannot satisfy a news request."""


def get_news_tavily(ticker: str, start_date: str, end_date: str) -> dict[str, Any]:
    """Retrieve company-specific market news through Tavily Search."""
    cfg = get_config()
    query = _build_company_news_query(ticker, cfg)
    return _search_tavily(
        query=query,
        start_date=start_date,
        end_date=end_date,
        log_key=ticker,
        log_date=end_date,
        method="get_news",
        cfg=cfg,
    )


def get_global_news_tavily(
    curr_date: str,
    look_back_days: int | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """Retrieve broad macro and market news through Tavily Search."""
    cfg = get_config()
    if look_back_days is None:
        look_back_days = int(cfg.get("global_news_lookback_days", 7))
    if limit is None:
        limit = int(cfg.get("global_news_article_limit", 5))
    curr_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    start_date = (curr_dt - timedelta(days=look_back_days)).strftime("%Y-%m-%d")
    query = str(
        cfg.get(
            "tavily_global_news_query",
            "global financial markets macro economy central bank inflation news",
        )
    )
    return _search_tavily(
        query=query,
        start_date=start_date,
        end_date=curr_date,
        log_key="GLOBAL",
        log_date=curr_date,
        method="get_global_news",
        limit=limit,
        cfg=cfg,
    )


def _search_tavily(
    *,
    query: str,
    start_date: str,
    end_date: str,
    log_key: str,
    log_date: str,
    method: str,
    limit: int | None = None,
    cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        raise TavilyUnavailableError("TAVILY_API_KEY environment variable is not set.")

    cfg = cfg or get_config()
    configured_max = int(cfg.get("tavily_max_results", 5))
    max_results = min(int(limit), configured_max) if limit else configured_max
    payload = {
        "query": query,
        "search_depth": cfg.get("tavily_search_depth", "basic"),
        "max_results": max_results,
        "topic": _topic_for_method(cfg, method),
        "start_date": start_date,
        "end_date": end_date,
        "include_raw_content": _config_bool(cfg.get("tavily_include_raw_content", False)),
        "include_answer": _config_bool(cfg.get("tavily_include_answer", False)),
        "include_images": _config_bool(cfg.get("tavily_include_images", False)),
        "auto_parameters": _config_bool(cfg.get("tavily_auto_parameters", False)),
        "include_favicon": True,
    }
    _apply_domain_filters(payload, cfg, method)

    response_data = _post_search(payload, api_key)
    capture_vendor_raw(
        response_data,
        metadata={
            "provider": "tavily",
            "topic": payload["topic"],
            "transport_attempt": 1,
        },
    )
    fallback_topic = _fallback_topic(payload["topic"], response_data, method, cfg)
    if fallback_topic:
        payload["topic"] = fallback_topic
        response_data = _post_search(payload, api_key)
        capture_vendor_raw(
            response_data,
            metadata={
                "provider": "tavily",
                "topic": payload["topic"],
                "transport_attempt": 2,
                "fallback_reason": "topic_retry",
            },
        )

    _save_raw_response(log_key, log_date, method, payload, response_data)
    return {
        "source": "tavily",
        "query": query,
        "payload": payload,
        "response": response_data,
        "items": _items_from_response(response_data, cfg, start_date, end_date),
    }


def _topic_for_method(cfg: dict[str, Any], method: str) -> str:
    if method == "get_news":
        return str(cfg.get("tavily_company_news_topic") or cfg.get("tavily_topic") or "news")
    if method == "get_global_news":
        return str(cfg.get("tavily_global_news_topic") or cfg.get("tavily_topic") or "news")
    return str(cfg.get("tavily_topic") or "news")


def _fallback_topic(
    current_topic: str,
    response_data: dict[str, Any],
    method: str,
    cfg: dict[str, Any],
) -> str | None:
    if _looks_like_invalid_topic(response_data):
        if method in {"get_news", "get_global_news"}:
            fallback_key = (
                "tavily_company_fallback_topic"
                if method == "get_news"
                else "tavily_global_fallback_topic"
            )
            fallback = str(cfg.get(fallback_key) or "").strip()
            if current_topic == "news" and fallback:
                return fallback
        if current_topic != "news":
            return "news"
        return "general"

    if method in {"get_news", "get_global_news"} and not response_data.get("results"):
        fallback_key = (
            "tavily_company_fallback_topic"
            if method == "get_news"
            else "tavily_global_fallback_topic"
        )
        fallback = str(cfg.get(fallback_key) or "").strip()
        if fallback and fallback != current_topic:
            return fallback
    return None


def _build_company_news_query(ticker: str, cfg: dict[str, Any]) -> str:
    plain_ticker = to_akshare_symbol(ticker) if is_a_share_ticker(ticker) else ticker
    template_key = (
        "tavily_a_share_news_query_template"
        if is_a_share_ticker(ticker)
        else "tavily_company_news_query_template"
    )
    template = str(
        cfg.get(template_key)
        or cfg.get("tavily_company_news_query_template")
        or '"{ticker}" stock company market news earnings'
    )
    return template.format(ticker=ticker, plain_ticker=plain_ticker)


def _apply_domain_filters(
    payload: dict[str, Any],
    cfg: dict[str, Any],
    method: str,
) -> None:
    include_domains = _list_config(cfg.get("tavily_include_domains"))
    exclude_domains = _list_config(cfg.get("tavily_exclude_domains"))
    if method == "get_news":
        include_domains.extend(_list_config(cfg.get("tavily_company_include_domains")))
        exclude_domains.extend(_list_config(cfg.get("tavily_company_exclude_domains")))
    elif method == "get_global_news":
        include_domains.extend(_list_config(cfg.get("tavily_global_include_domains")))
        exclude_domains.extend(_list_config(cfg.get("tavily_global_exclude_domains")))

    if include_domains:
        payload["include_domains"] = _dedupe_domains(include_domains)
    if exclude_domains:
        payload["exclude_domains"] = _dedupe_domains(exclude_domains)


def _list_config(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    if isinstance(value, (list, tuple, set)):
        return [str(part).strip() for part in value if str(part).strip()]
    return []


def _dedupe_domains(domains: list[str]) -> list[str]:
    deduped = []
    seen = set()
    for domain in domains:
        normalized = domain.lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(domain)
    return deduped


def _post_search(payload: dict[str, Any], api_key: str) -> dict[str, Any]:
    response = requests.post(
        API_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=30,
    )
    try:
        data = response.json()
    except ValueError:
        data = {"raw_text": response.text}

    if response.status_code >= 400 and not _looks_like_invalid_topic(data):
        raise TavilyUnavailableError(
            f"Tavily search failed with HTTP {response.status_code}: {data}"
        )
    return data


def _config_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _looks_like_invalid_topic(data: dict[str, Any]) -> bool:
    text = json.dumps(data, ensure_ascii=False).lower()
    return "topic" in text and ("invalid" in text or "unsupported" in text)


def _items_from_response(
    response_data: dict[str, Any],
    cfg: dict[str, Any] | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[dict[str, Any]]:
    items = []
    for result in response_data.get("results") or []:
        if not isinstance(result, dict):
            continue
        url = result.get("url") or ""
        published = result.get("published_date") or result.get("published_time") or ""
        item = {
            "title": result.get("title") or "Untitled",
            "url": url,
            "content": result.get("content") or "",
            "published": published,
            "score": result.get("score"),
            "publisher": _publisher_from_url(url),
            "source": "tavily",
        }
        if start_date and end_date and published:
            item["stale"] = _is_published_outside_window(published, start_date, end_date)
        items.append(item)
    return _filter_items_by_score(items, cfg or {})


_KNOWN_DATE_FORMATS = (
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%dT%H:%M:%S%z",
    "%Y-%m-%d",
    "%Y%m%dT%H%M%S",
    "%Y%m%d",
    "%b %d, %Y",
    "%B %d, %Y",
    "%d %b %Y",
    "%d %B %Y",
)


def _parse_published_date(raw: str) -> datetime | None:
    """Best-effort parse of a published date string into a naive datetime."""
    text = str(raw or "").strip()
    if not text:
        return None
    # Strip trailing timezone abbreviations like "EST", "UTC" for strptime
    cleaned = re.sub(r"\s+[A-Z]{2,4}$", "", text)
    for fmt in _KNOWN_DATE_FORMATS:
        try:
            dt = datetime.strptime(cleaned, fmt)
            return dt.replace(tzinfo=None)  # make naive for comparison
        except ValueError:
            continue
    # Try ISO format as last resort
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None)
    except (ValueError, AttributeError):
        return None


def _is_published_outside_window(published: str, start_date: str, end_date: str) -> bool:
    """Return True if the published date is clearly outside the [start, end] window."""
    dt = _parse_published_date(published)
    if dt is None:
        return False  # can't determine → don't flag as stale
    try:
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
    except ValueError:
        return False
    return dt < start or dt >= end


def _filter_items_by_score(items: list[dict[str, Any]], cfg: dict[str, Any]) -> list[dict[str, Any]]:
    threshold = cfg.get("tavily_min_score")
    if threshold is None or threshold == "":
        return items
    try:
        min_score = float(threshold)
    except (TypeError, ValueError):
        return items
    filtered = [
        item
        for item in items
        if not isinstance(item.get("score"), (int, float)) or float(item["score"]) >= min_score
    ]
    return filtered or items


def _publisher_from_url(url: str) -> str:
    domain = urlparse(str(url or "")).netloc.lower()
    return domain.removeprefix("www.") or "unknown"


def _save_raw_response(
    log_key: str,
    log_date: str,
    method: str,
    payload: dict[str, Any],
    response_data: dict[str, Any],
) -> None:
    cfg = get_config()
    results_dir = cfg.get("results_dir")
    if not results_dir:
        return

    request_id = str(response_data.get("request_id") or "no-request-id")
    usage = response_data.get("usage") if isinstance(response_data.get("usage"), dict) else {}
    usage.setdefault("credits", None)
    safe_key = re.sub(r"[^A-Za-z0-9_.-]+", "_", log_key)
    safe_request_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", request_id)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    data_dir = Path(results_dir) / safe_key / str(log_date) / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / f"tavily_{method}_{timestamp}_{safe_request_id}.json"
    path.write_text(
        json.dumps(
            {
                "payload": payload,
                "response": response_data,
                "usage": usage,
                "request_id": response_data.get("request_id"),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
