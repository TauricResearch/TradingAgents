"""Shared request/auth plumbing for the brapi.dev vendor (B3 / Brazilian market).

brapi.dev serves B3 tickers without the exchange suffix (``PETR4``, not
``PETR4.SA``), authenticates via a bearer token, and returns JSON shaped like
Yahoo's quote+modules response rather than a flat CSV. This module owns the
token lookup and the HTTP call; ``brapi_stock.py`` and
``brapi_fundamentals.py`` shape the response into the same CSV/text contract
every other vendor in this package returns.
"""

from __future__ import annotations

import os

from .errors import VendorNotConfiguredError, VendorRateLimitError
from .utils import get_scrubbed

API_BASE_URL = "https://brapi.dev/api"

# Network timeout (seconds) so a stalled brapi.dev request can't hang the
# CLI/agents indefinitely (same discipline as alpha_vantage_common.py, #990).
REQUEST_TIMEOUT = 30


class BrapiNotConfiguredError(VendorNotConfiguredError):
    """Raised when brapi.dev is selected but no API token is configured.

    A VendorNotConfiguredError (and thus still a ValueError), so the routing
    layer's "vendor unavailable" handling and existing ValueError callers
    both keep working (see interface.py's route_to_vendor).
    """


class BrapiRateLimitError(VendorRateLimitError):
    """Raised when brapi.dev throttles the request (HTTP 429 or quota notice)."""


def get_api_token() -> str:
    """Retrieve the brapi.dev API token from the environment.

    brapi.dev lets four test tickers (PETR4, VALE3, MGLU3, ITUB4) through
    without a token, but any other symbol — and any request that mixes a test
    ticker with a real one — requires auth. Requiring the token unconditionally
    here keeps this vendor's behavior predictable across every ticker instead
    of depending on which four names still count as "test" symbols upstream.
    """
    token = os.getenv("BRAPI_TOKEN")
    if not token:
        raise BrapiNotConfiguredError(
            "BRAPI_TOKEN environment variable is not set. Get a free token at "
            "https://brapi.dev/dashboard and export it as BRAPI_TOKEN."
        )
    return token


def strip_b3_suffix(ticker: str) -> str:
    """Map a Yahoo-style B3 ticker (``PETR4.SA``) to brapi's bare form (``PETR4``).

    Passes through unchanged when there is no ``.SA`` suffix, so callers can
    hand this the raw ticker the agent used without checking the market first.
    """
    if not isinstance(ticker, str):
        return ticker
    upper = ticker.strip().upper()
    return upper[:-3] if upper.endswith(".SA") else upper


def brapi_request(path: str, params: dict | None = None) -> dict:
    """GET a brapi.dev endpoint and return the parsed JSON body.

    Raises:
        BrapiNotConfiguredError: no BRAPI_TOKEN set.
        BrapiRateLimitError: brapi.dev throttled or quota-limited the request.
    """
    token = get_api_token()
    query = dict(params or {})
    query["token"] = token

    response = get_scrubbed(
        f"{API_BASE_URL}/{path.lstrip('/')}",
        params=query,
        timeout=REQUEST_TIMEOUT,
        secret=token,
        passthrough=(429,),
    )

    if response.status_code == 429:
        raise BrapiRateLimitError("brapi.dev rate limit exceeded (HTTP 429).")

    payload = response.json()

    # brapi.dev reports auth/plan problems as a JSON "error" body with 200 or
    # 4xx depending on the endpoint, rather than a uniform status code.
    if isinstance(payload, dict) and payload.get("error"):
        message = payload.get("message", "unknown error")
        low = str(message).lower()
        if "token" in low or "auth" in low or "plan" in low:
            raise BrapiNotConfiguredError(f"brapi.dev rejected the request: {message}")
        raise BrapiRateLimitError(f"brapi.dev error: {message}")

    return payload
