"""Tradier API common utilities: authentication, HTTP helpers, and rate limit handling.

Mirrors the pattern established by alpha_vantage_common.py for vendor-abstracted
data access with automatic rate limit detection and retry logic.
"""

import os
import time

import requests


TRADIER_PRODUCTION_URL = "https://api.tradier.com"
TRADIER_SANDBOX_URL = "https://sandbox.tradier.com"


class TradierRateLimitError(Exception):
    """Exception raised when Tradier API rate limit is exceeded."""

    pass


def get_api_key() -> str:
    """Retrieve the Tradier API key from environment variables.

    Returns:
        The API key string.

    Raises:
        ValueError: If TRADIER_API_KEY is not set.
    """
    api_key = os.getenv("TRADIER_API_KEY")
    if not api_key:
        raise ValueError("TRADIER_API_KEY environment variable is not set.")
    return api_key


def get_base_url() -> str:
    """Return the Tradier base URL based on sandbox configuration.

    Reads TRADIER_SANDBOX env var. If set to 'true', '1', or 'yes' (case-insensitive),
    returns the sandbox URL; otherwise returns production URL.

    Returns:
        The base URL string for Tradier API requests.
    """
    sandbox = os.getenv("TRADIER_SANDBOX", "false")
    if sandbox.lower() in ("true", "1", "yes"):
        return TRADIER_SANDBOX_URL
    return TRADIER_PRODUCTION_URL


def make_tradier_request(path: str, params: dict | None = None) -> dict:
    """Make an authenticated GET request to the Tradier API.

    Args:
        path: API endpoint path (e.g. '/v1/markets/options/chains').
        params: Optional query parameters.

    Returns:
        Parsed JSON response as a dict.

    Raises:
        TradierRateLimitError: On HTTP 429 or exhausted X-Ratelimit-Available.
        requests.HTTPError: On other non-2xx responses.
    """
    url = f"{get_base_url()}{path}"
    headers = {
        "Authorization": f"Bearer {get_api_key()}",
        "Accept": "application/json",
    }

    response = requests.get(url, headers=headers, params=params or {})

    # Check rate limit headers before status code
    available = response.headers.get("X-Ratelimit-Available")
    if available is not None:
        try:
            available_int = int(available)
        except (ValueError, TypeError):
            expiry = response.headers.get("X-Ratelimit-Expiry")
            raise TradierRateLimitError(
                f"Tradier rate limit: non-numeric X-Ratelimit-Available={available!r}, "
                f"X-Ratelimit-Expiry={expiry}"
            )
        if available_int <= 0:
            expiry = response.headers.get("X-Ratelimit-Expiry")
            raise TradierRateLimitError(
                f"Tradier rate limit exhausted: X-Ratelimit-Available=0, "
                f"X-Ratelimit-Expiry={expiry}"
            )

    if response.status_code == 429:
        raise TradierRateLimitError("Tradier rate limit exceeded (HTTP 429)")

    response.raise_for_status()
    return response.json()


def make_tradier_request_with_retry(
    path: str, params: dict | None = None, max_retries: int = 3
) -> dict:
    """Make a Tradier API request with exponential backoff retry on rate limits.

    Args:
        path: API endpoint path.
        params: Optional query parameters.
        max_retries: Maximum number of attempts (default 3).

    Returns:
        Parsed JSON response as a dict.

    Raises:
        TradierRateLimitError: If all retries are exhausted.
    """
    for attempt in range(max_retries):
        try:
            return make_tradier_request(path, params)
        except TradierRateLimitError:
            if attempt < max_retries - 1:
                time.sleep(2**attempt)
                continue
            raise
