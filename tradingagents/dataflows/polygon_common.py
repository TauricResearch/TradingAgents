"""Shared utilities for Polygon REST API access.

Polygon is the preferred provider for point-in-time fundamentals (as-reported
SEC filings filtered by ``filing_date.lt``) and split-adjusted historical bars.
This module hosts the request helper, key resolution, in-process caching,
rate-limit handling, and the shared error classes consumed by callers and the
vendor router in :mod:`tradingagents.dataflows.interface`.
"""

from __future__ import annotations

import os
import random
import threading
import time
from typing import Any

import requests

API_BASE_URL = "https://api.polygon.io"

_TRANSIENT_HTTP_STATUSES = {429, 500, 502, 503, 504}
_DEFAULT_TIMEOUT = 30
_MAX_RETRIES = 4


class PolygonError(Exception):
    """Base error class for Polygon REST failures."""


class PolygonRateLimitError(PolygonError):
    """Raised when Polygon returns 429 or signals rate limit exhaustion.

    Mirrors :class:`AlphaVantageRateLimitError` so the vendor router can
    treat it as a fallback trigger.
    """


class PolygonAuthError(PolygonError):
    """Raised when Polygon returns 401/403 — usually a bad/expired API key."""


class PolygonNotFoundError(PolygonError):
    """Raised when the requested resource (ticker, page) is missing."""


def get_api_key() -> str:
    api_key = os.getenv("POLYGON_API_KEY")
    if not api_key:
        raise PolygonError(
            "POLYGON_API_KEY environment variable is not set. "
            "Add it to .env or export it before invoking the agent pipeline."
        )
    return api_key


_session_lock = threading.Lock()
_session: requests.Session | None = None


def _get_session() -> requests.Session:
    global _session
    with _session_lock:
        if _session is None:
            session = requests.Session()
            session.headers.update({
                "User-Agent": "trading_agents/polygon-client",
                "Accept": "application/json",
            })
            _session = session
        return _session


def _sleep_backoff(attempt: int) -> None:
    base = min(2 ** attempt, 16)
    time.sleep(base + random.random())


def _make_request(
    path: str,
    params: dict[str, Any] | None = None,
    *,
    timeout: int = _DEFAULT_TIMEOUT,
    max_retries: int = _MAX_RETRIES,
) -> dict[str, Any]:
    """Issue a GET against ``API_BASE_URL + path``.

    Retries on transient 5xx and 429 with exponential backoff. Returns the
    JSON-decoded payload (Polygon always returns JSON).
    """
    api_params: dict[str, Any] = dict(params or {})
    api_params["apiKey"] = get_api_key()
    url = f"{API_BASE_URL}{path}"

    session = _get_session()

    last_exc: Exception | None = None
    for attempt in range(max_retries):
        try:
            response = session.get(url, params=api_params, timeout=timeout)
        except requests.RequestException as exc:
            last_exc = exc
            _sleep_backoff(attempt)
            continue

        status = response.status_code

        if status == 200:
            try:
                return response.json()
            except ValueError as exc:
                raise PolygonError(
                    f"Polygon returned non-JSON 200 for {path}: {exc}"
                ) from exc

        if status in (401, 403):
            raise PolygonAuthError(
                f"Polygon auth failed for {path}: {status} {response.text[:200]}"
            )

        if status == 404:
            raise PolygonNotFoundError(f"Polygon 404 for {path}: {response.text[:200]}")

        if status in _TRANSIENT_HTTP_STATUSES:
            if status == 429 and attempt == max_retries - 1:
                raise PolygonRateLimitError(
                    f"Polygon rate limit hit on {path} after {max_retries} attempts"
                )
            _sleep_backoff(attempt)
            continue

        raise PolygonError(
            f"Polygon error {status} on {path}: {response.text[:200]}"
        )

    raise PolygonError(f"Polygon request failed after {max_retries} retries: {last_exc}")


def paginated_results(
    initial_path: str,
    initial_params: dict[str, Any] | None = None,
    *,
    max_pages: int = 10,
) -> list[dict[str, Any]]:
    """Iterate Polygon's ``next_url``-style cursor pagination.

    Returns the union of ``results`` arrays across all visited pages. Caps
    at ``max_pages`` to bound runaway crawls (financials/news for a single
    ticker rarely need more than 2-3 pages).
    """
    from urllib.parse import urlparse, parse_qs

    out: list[dict[str, Any]] = []
    payload = _make_request(initial_path, initial_params)
    out.extend(payload.get("results") or [])

    next_url = payload.get("next_url")
    pages_visited = 1
    while next_url and pages_visited < max_pages:
        parsed = urlparse(next_url)
        if not parsed.path:
            break
        # Strip apiKey from any prior url; _make_request will append a fresh one.
        next_params: dict[str, Any] = {
            k: v[0] if isinstance(v, list) and len(v) == 1 else v
            for k, v in parse_qs(parsed.query).items()
            if k != "apiKey"
        }
        payload = _make_request(parsed.path, next_params)
        out.extend(payload.get("results") or [])
        next_url = payload.get("next_url")
        pages_visited += 1
    return out
