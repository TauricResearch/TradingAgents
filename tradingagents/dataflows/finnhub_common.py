"""Common infrastructure for the Finnhub data vendor integration.

Provides the exception hierarchy, thread-safe rate limiter (60 calls/min for
the Finnhub free tier), and the core HTTP request helper used by all other
finnhub_* modules.
"""

import json
import os
import threading
import time as _time
from datetime import datetime

import requests

API_BASE_URL = "https://finnhub.io/api/v1"


# ---------------------------------------------------------------------------
# API key helpers
# ---------------------------------------------------------------------------


def get_api_key() -> str:
    """Retrieve the Finnhub API key from environment variables.

    Returns:
        The API key string.

    Raises:
        APIKeyInvalidError: When FINNHUB_API_KEY is missing or empty.
    """
    api_key = os.environ.get("FINNHUB_API_KEY")
    if not api_key:
        raise APIKeyInvalidError(
            "FINNHUB_API_KEY environment variable is not set or is empty."
        )
    return api_key


# ---------------------------------------------------------------------------
# Exception hierarchy
# ---------------------------------------------------------------------------


class FinnhubError(Exception):
    """Base exception for all Finnhub API errors."""


class APIKeyInvalidError(FinnhubError):
    """Raised when the API key is invalid or missing (401-equivalent)."""


class RateLimitError(FinnhubError):
    """Raised when the Finnhub API rate limit is exceeded (429-equivalent)."""


class ThirdPartyError(FinnhubError):
    """Raised on server-side errors (5xx status codes) or connection failures."""


class ThirdPartyTimeoutError(FinnhubError):
    """Raised when the request times out."""


class ThirdPartyParseError(FinnhubError):
    """Raised when the response cannot be parsed as valid JSON."""


# ---------------------------------------------------------------------------
# Thread-safe rate limiter — 60 calls/minute (Finnhub free tier)
# ---------------------------------------------------------------------------

_rate_lock = threading.Lock()
_call_timestamps: list[float] = []
_RATE_LIMIT = 60  # calls per minute


def _rate_limited_request(endpoint: str, params: dict, timeout: int = 30) -> dict:
    """Make a rate-limited Finnhub API request.

    Enforces the 60-calls-per-minute limit for the free tier using a sliding
    window tracked in a shared list.  The lock is released before any sleep
    to avoid blocking other threads.

    Args:
        endpoint: Finnhub endpoint path (e.g. "quote").
        params: Query parameters (excluding the API token).
        timeout: HTTP request timeout in seconds.

    Returns:
        Parsed JSON response as a dict.

    Raises:
        FinnhubError subclass on any API or network error.
    """
    sleep_time = 0.0
    with _rate_lock:
        now = _time.time()
        _call_timestamps[:] = [t for t in _call_timestamps if now - t < 60]
        if len(_call_timestamps) >= _RATE_LIMIT:
            sleep_time = 60 - (now - _call_timestamps[0]) + 0.1

    # Sleep outside the lock so other threads are not blocked
    if sleep_time > 0:
        _time.sleep(sleep_time)

    # Re-check under lock — another thread may have filled the window while we slept
    while True:
        with _rate_lock:
            now = _time.time()
            _call_timestamps[:] = [t for t in _call_timestamps if now - t < 60]
            if len(_call_timestamps) >= _RATE_LIMIT:
                extra_sleep = 60 - (now - _call_timestamps[0]) + 0.1
            else:
                _call_timestamps.append(_time.time())
                break
        # Sleep outside the lock
        _time.sleep(extra_sleep)

    return _make_api_request(endpoint, params, timeout=timeout)


# ---------------------------------------------------------------------------
# Core HTTP request helper
# ---------------------------------------------------------------------------


def _make_api_request(endpoint: str, params: dict, timeout: int = 30) -> dict:
    """Make a Finnhub API request with proper error handling.

    Calls ``https://finnhub.io/api/v1/{endpoint}`` and returns the parsed JSON
    body.  The ``token`` parameter is injected automatically from the
    ``FINNHUB_API_KEY`` environment variable.

    Args:
        endpoint: Finnhub endpoint path without leading slash (e.g. "quote").
        params: Query parameters dict (do NOT include ``token`` here).
        timeout: HTTP request timeout in seconds.

    Returns:
        Parsed JSON response as a dict.

    Raises:
        APIKeyInvalidError: Invalid or missing API key (HTTP 401 or env missing).
        RateLimitError: Rate limit exceeded (HTTP 429).
        ThirdPartyError: Server-side error (5xx) or connection failure.
        ThirdPartyTimeoutError: Request timed out.
        ThirdPartyParseError: Response body is not valid JSON.
    """
    api_params = params.copy()
    api_params["token"] = get_api_key()

    url = f"{API_BASE_URL}/{endpoint}"

    try:
        response = requests.get(url, params=api_params, timeout=timeout)
    except requests.exceptions.Timeout:
        raise ThirdPartyTimeoutError(
            f"Request timed out: endpoint={endpoint}, params={params}"
        )
    except requests.exceptions.ConnectionError as exc:
        raise ThirdPartyError(
            f"Connection error: endpoint={endpoint}, error={exc}"
        )
    except requests.exceptions.RequestException as exc:
        raise ThirdPartyError(
            f"Request failed: endpoint={endpoint}, error={exc}"
        )

    # HTTP-level error mapping
    if response.status_code == 401:
        raise APIKeyInvalidError(
            f"Invalid API key: status={response.status_code}, body={response.text[:200]}"
        )
    if response.status_code == 403:
        raise APIKeyInvalidError(
            f"Access forbidden (check API key tier): status={response.status_code}, "
            f"body={response.text[:200]}"
        )
    if response.status_code == 429:
        raise RateLimitError(
            f"Rate limit exceeded: status={response.status_code}, body={response.text[:200]}"
        )
    if response.status_code >= 500:
        raise ThirdPartyError(
            f"Server error: status={response.status_code}, endpoint={endpoint}, "
            f"body={response.text[:200]}"
        )
    try:
        response.raise_for_status()
    except requests.exceptions.HTTPError as exc:
        raise ThirdPartyError(
            f"HTTP error: status={response.status_code}, endpoint={endpoint}, "
            f"body={response.text[:200]}"
        ) from exc

    # Parse JSON — Finnhub always returns JSON (never CSV)
    try:
        return response.json()
    except (ValueError, requests.exceptions.JSONDecodeError) as exc:
        raise ThirdPartyParseError(
            f"Failed to parse JSON response for endpoint={endpoint}: {exc}. "
            f"Body preview: {response.text[:200]}"
        ) from exc


# ---------------------------------------------------------------------------
# Shared formatting utilities
# ---------------------------------------------------------------------------


def _now_str() -> str:
    """Return current local datetime as a human-readable string."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _fmt_pct(value: float | None) -> str:
    """Format an optional float as a percentage string with sign.

    Args:
        value: The percentage value, or None.

    Returns:
        String like "+1.23%" or "N/A".
    """
    if value is None:
        return "N/A"
    return f"{value:+.2f}%"


def _to_unix_timestamp(date_str: str) -> int:
    """Convert a YYYY-MM-DD date string to a Unix timestamp (midnight UTC).

    Args:
        date_str: Date in YYYY-MM-DD format.

    Returns:
        Unix timestamp as integer.

    Raises:
        ValueError: When the date string does not match the expected format.
    """
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return int(dt.timestamp())
