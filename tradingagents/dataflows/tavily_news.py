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
from .news_key_health import (
    RATE_LIMIT_COOLDOWN_SECONDS,
    TRANSIENT_FAILURE_COOLDOWN_SECONDS,
    NewsProviderKeyPool,
)
from .target_context import get_target_ticker
from .ticker_utils import is_a_share_ticker, to_akshare_symbol

API_URL = "https://api.tavily.com/search"


class TavilyUnavailableError(Exception):
    """Raised when Tavily is not configured or cannot satisfy a news request."""


class _TavilyHTTPError(TavilyUnavailableError):
    """Transport failure with a structured status for key health policy."""

    def __init__(self, status_code: int, detail: str = "") -> None:
        self.status_code = status_code
        super().__init__(f"Tavily search failed with HTTP {status_code}: {detail}")


_tavily_key_pool = NewsProviderKeyPool("tavily")


def clear_tavily_key_health() -> None:
    """Clear in-process key cooldowns (mainly useful to deterministic tests)."""
    _tavily_key_pool.clear()


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
    api_keys = _configured_api_keys()
    if not api_keys:
        raise TavilyUnavailableError(
            "No Tavily API key is configured. Set TAVILY_API_KEY or the comma-separated TAVILY_API_KEYS."
        )
    _tavily_key_pool.configure(api_keys)

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

    response_data = _post_with_healthy_key(payload)
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
        response_data = _post_with_healthy_key(payload)
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


def _configured_api_keys() -> tuple[str, ...]:
    """Read multi-key configuration without logging or returning it to callers."""
    multi = os.getenv("TAVILY_API_KEYS", "")
    values = [part.strip() for part in multi.split(",") if part.strip()]
    legacy = os.getenv("TAVILY_API_KEY", "").strip()
    if legacy:
        values.append(legacy)
    # ``dict.fromkeys`` preserves operator-supplied priority while removing
    # duplicate credentials that would otherwise waste a rotation attempt.
    return tuple(dict.fromkeys(values))


def _post_with_healthy_key(payload: dict[str, Any]) -> dict[str, Any]:
    """Try each healthy key exactly once for transient failures.

    Authentication and authorization failures are made explicit and do not
    rotate: retrying another configured credential would disguise a provider
    policy problem and violates the data-layer no-bypass contract.
    """
    attempted = 0
    last_error: Exception | None = None
    while (api_key := _tavily_key_pool.acquire()) is not None:
        attempted += 1
        try:
            data = _post_search(payload, api_key)
        except _TavilyHTTPError as exc:
            last_error = exc
            cooldown_seconds, reason = _key_cooldown_for_status(exc.status_code)
            if cooldown_seconds <= 0:
                raise TavilyUnavailableError(
                    f"Tavily rejected the configured request with HTTP {exc.status_code}; key rotation was not attempted."
                ) from exc
            _tavily_key_pool.record_failure(
                api_key,
                cooldown_seconds=cooldown_seconds,
                reason=reason,
            )
            continue
        except requests.RequestException as exc:
            last_error = exc
            _tavily_key_pool.record_failure(
                api_key,
                cooldown_seconds=TRANSIENT_FAILURE_COOLDOWN_SECONDS,
                reason="network",
            )
            continue
        _tavily_key_pool.record_success(api_key)
        return data

    if attempted:
        raise TavilyUnavailableError(
            "Tavily is temporarily unavailable: every configured key is cooling down after a transient provider failure."
        ) from last_error
    raise TavilyUnavailableError(
        "Tavily is temporarily unavailable: every configured key is in cooldown."
    )


def _key_cooldown_for_status(status_code: int) -> tuple[float, str]:
    if status_code == 429:
        return RATE_LIMIT_COOLDOWN_SECONDS, "rate_limit"
    if 500 <= status_code <= 599:
        return TRANSIENT_FAILURE_COOLDOWN_SECONDS, f"http_{status_code}"
    return 0.0, f"http_{status_code}"


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
    # Anchor the query with the resolved company name (when available from the
    # run's target context) so Tavily full-text search distinguishes the target
    # company from peers that share a ticker fragment or sector keywords.
    target = get_target_ticker()
    company_name = (target.company_name if target else None) or ""
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
    query = template.format(
        ticker=ticker, plain_ticker=plain_ticker, company_name=company_name
    )
    # Drop empty quoted placeholders (company name unavailable) and collapse
    # whitespace so the query stays well-formed for either market.
    query = re.sub(r'""', "", query)
    return re.sub(r"\s+", " ", query).strip()


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
        # The caller redacts details before surfacing an error.  Do not insert
        # request headers here: a key may never become part of an exception,
        # progress event, or durable raw-response artifact.
        raise _TavilyHTTPError(response.status_code, "provider returned an error response")
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
