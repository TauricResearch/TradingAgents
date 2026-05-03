"""Tavily-backed news search with conservative API usage defaults."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import requests

from .config import get_config


API_URL = "https://api.tavily.com/search"


class TavilyUnavailableError(Exception):
    """Raised when Tavily is not configured or cannot satisfy a news request."""


def get_news_tavily(ticker: str, start_date: str, end_date: str) -> dict[str, Any]:
    """Retrieve company-specific market news through Tavily Search."""
    query = f'"{ticker}" stock company market news earnings'
    return _search_tavily(
        query=query,
        start_date=start_date,
        end_date=end_date,
        log_key=ticker,
        log_date=end_date,
        method="get_news",
    )


def get_global_news_tavily(
    curr_date: str,
    look_back_days: int = 7,
    limit: int = 5,
) -> dict[str, Any]:
    """Retrieve broad macro and market news through Tavily Search."""
    curr_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    start_date = (curr_dt - timedelta(days=look_back_days)).strftime("%Y-%m-%d")
    query = "global financial markets macro economy central bank inflation news"
    return _search_tavily(
        query=query,
        start_date=start_date,
        end_date=curr_date,
        log_key="GLOBAL",
        log_date=curr_date,
        method="get_global_news",
        limit=limit,
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
) -> dict[str, Any]:
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        raise TavilyUnavailableError("TAVILY_API_KEY environment variable is not set.")

    cfg = get_config()
    configured_max = int(cfg.get("tavily_max_results", 5))
    max_results = min(int(limit), configured_max) if limit else configured_max
    payload = {
        "query": query,
        "search_depth": cfg.get("tavily_search_depth", "basic"),
        "max_results": max_results,
        "topic": cfg.get("tavily_topic", "finance"),
        "start_date": start_date,
        "end_date": end_date,
        "include_raw_content": _config_bool(cfg.get("tavily_include_raw_content", False)),
        "include_answer": _config_bool(cfg.get("tavily_include_answer", False)),
        "include_images": _config_bool(cfg.get("tavily_include_images", False)),
        "auto_parameters": _config_bool(cfg.get("tavily_auto_parameters", False)),
        "include_favicon": True,
    }

    response_data = _post_search(payload, api_key)
    if _looks_like_invalid_topic(response_data) and payload["topic"] == "finance":
        payload["topic"] = "news"
        response_data = _post_search(payload, api_key)

    _save_raw_response(log_key, log_date, method, payload, response_data)
    return {
        "source": "tavily",
        "query": query,
        "payload": payload,
        "response": response_data,
        "items": _items_from_response(response_data),
    }


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


def _items_from_response(response_data: dict[str, Any]) -> list[dict[str, Any]]:
    items = []
    for result in response_data.get("results") or []:
        if not isinstance(result, dict):
            continue
        items.append(
            {
                "title": result.get("title") or "Untitled",
                "url": result.get("url") or "",
                "content": result.get("content") or "",
                "published": result.get("published_date") or result.get("published_time") or "",
                "score": result.get("score"),
                "source": "tavily",
            }
        )
    return items


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
