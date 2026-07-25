"""Vendor error classification, cooldown mapping, and unavailable-data messages.

Extracted from ``interface.py``. These helpers decide how the router reacts to
vendor failures: which errors are recoverable (try next vendor), which are
transient (record a cooldown), how long to cool down, and how to summarize the
failure for progress events and aggregate messages.

The module depends on the health registry (in ``health.py``), the error
taxonomy (``errors.py``), and vendor-specific exception types. It reaches
``_market_for_request`` (routing core) via a function-local import to avoid a
circular dependency.
"""

from __future__ import annotations

import re
from typing import Any

import requests
from yfinance.exceptions import YFRateLimitError

from .alpha_vantage_common import AlphaVantageNotConfiguredError, AlphaVantageRateLimitError
from .china_data import ChinaDataUnavailableError
from .config import get_config
from .errors import (
    DataUnavailableError,
    VendorError,
    VendorRateLimitError,
)
from .fred import FredNotConfiguredError
from .health import (
    RATE_LIMIT_COOLDOWN_SECONDS,
    TRANSIENT_FAILURE_COOLDOWN_SECONDS,
)
from .tavily_news import TavilyUnavailableError

try:
    from curl_cffi.requests.exceptions import RequestException as CurlCffiRequestException
except Exception:  # pragma: no cover - curl_cffi is an indirect yfinance dependency
    CurlCffiRequestException = ()


def _record_vendor_success(vendor: str, method: str, args: tuple[Any, ...]) -> None:
    # Function-local import: tests monkeypatch interface._vendor_health, so both
    # the router and these helpers must read the same (interface-module) binding.
    from .interface import _market_for_request, _vendor_health

    _vendor_health.record_success(
        vendor=vendor,
        market=_market_for_request(args, method),
        capability=method,
    )


def _record_vendor_failure(vendor: str, method: str, args: tuple[Any, ...], exc: Exception) -> None:
    from .interface import _market_for_request, _vendor_health

    cooldown_seconds, reason = _cooldown_for_exception(exc)
    _vendor_health.record_failure(
        vendor=vendor,
        market=_market_for_request(args, method),
        capability=method,
        cooldown_seconds=cooldown_seconds,
        reason=reason,
    )


def _cooldown_for_exception(exc: Exception) -> tuple[float, str]:
    """Map retry semantics to the circuit-breaker policy.

    A 403 remains a normal per-request fallback error but creates no global
    cooldown: access policies can be endpoint-specific and must not poison a
    provider forever.  Other non-transient errors also remain uncooled.
    """
    status_code = _http_status_code(exc)
    if isinstance(exc, (VendorRateLimitError, YFRateLimitError)) or status_code == 429:
        return RATE_LIMIT_COOLDOWN_SECONDS, "rate_limit"
    if status_code == 403:
        return 0.0, "forbidden"
    if status_code == 0:
        return TRANSIENT_FAILURE_COOLDOWN_SECONDS, "network"
    if isinstance(status_code, int) and 500 <= status_code <= 599:
        return TRANSIENT_FAILURE_COOLDOWN_SECONDS, f"http_{status_code}"
    request_errors = (requests.RequestException,)
    if CurlCffiRequestException:
        request_errors = (*request_errors, CurlCffiRequestException)
    if isinstance(exc, request_errors):
        return TRANSIENT_FAILURE_COOLDOWN_SECONDS, "network"
    return 0.0, type(exc).__name__


def _http_status_code(exc: Exception) -> int | None:
    """Read a transport status from structured errors or legacy vendor text."""
    status_code = getattr(exc, "status_code", None)
    if isinstance(status_code, int):
        return status_code
    response = getattr(exc, "response", None)
    response_status_code = getattr(response, "status_code", None)
    if isinstance(response_status_code, int):
        return response_status_code
    match = re.search(r"\bHTTP\s+(\d{3})\b", str(exc), flags=re.IGNORECASE)
    return int(match.group(1)) if match else None


def _is_missing_required_data_result(result: Any) -> bool:
    if result is None:
        return True
    if hasattr(result, "empty") and result.empty:
        return True
    if isinstance(result, dict):
        return not bool(result) or any(
            key in result for key in ("Error Message", "Note", "Information")
        )
    text = str(result).strip()
    if not text:
        return True
    lowered = text.lower()
    missing_prefixes = (
        "no data found",
        "no fundamentals data found",
        "no balance sheet data found",
        "no cash flow data found",
        "no income statement data found",
        "error retrieving",
        "error getting",
        "data unavailable",
    )
    return lowered.startswith(missing_prefixes)


def _should_halt_on_missing_data(method: str) -> bool:
    cfg = get_config()
    if not cfg.get("halt_on_missing_data", True):
        return False
    return method in {
        "get_stock_data",
        "get_indicators",
        "get_fundamentals",
        "get_balance_sheet",
        "get_cashflow",
        "get_income_statement",
    }


def _is_recoverable_vendor_error(vendor: str, exc: Exception) -> bool:
    """Return True when the chain should try the next vendor instead of aborting.

    VendorError subclasses (no-data / rate-limit / not-configured) are always
    recoverable - that is the point of the shared hierarchy. Any other
    ValueError raised by a vendor is also treated as recoverable within the
    chain: vendors raise ValueError for many data-shape reasons, and the next
    vendor may still succeed. The chain's tail logic decides whether to re-raise
    the original error (single broken primary) or aggregate it.
    """
    request_errors = (requests.RequestException,)
    if CurlCffiRequestException:
        request_errors = (*request_errors, CurlCffiRequestException)

    if vendor in {"alpha_vantage", "tavily", "yfinance"} and isinstance(exc, request_errors):
        return True

    if isinstance(
        exc,
        (
            VendorError,
            AlphaVantageRateLimitError,
            AlphaVantageNotConfiguredError,
            FredNotConfiguredError,
            TavilyUnavailableError,
            YFRateLimitError,
            ChinaDataUnavailableError,
        ),
    ):
        return True

    return isinstance(exc, ValueError)


def _is_transient_vendor_error(exc: Exception) -> bool:
    """True for transient errors (rate limit / network) that justify pulling in
    vendors outside the explicitly configured chain as an implicit safety net.

    Not-configured and no-data errors are NOT transient: the former is a config
    problem the user should see, and the latter means the data genuinely does
    not exist, so silently trying an unchosen vendor would mask the real cause.
    """
    request_errors = (requests.RequestException,)
    if CurlCffiRequestException:
        request_errors = (*request_errors, CurlCffiRequestException)
    if _cooldown_for_exception(exc)[0] > 0:
        return True
    return isinstance(
        exc,
        (
            VendorRateLimitError,
            AlphaVantageRateLimitError,
            YFRateLimitError,
            TavilyUnavailableError,
            *request_errors,
        ),
    )


def _format_vendor_unavailable_message(
    method: str,
    errors: list[tuple[str, Exception]],
    category: str = "",
) -> str:
    details = "; ".join(f"{vendor}: {_summarize_vendor_error(exc)}" for vendor, exc in errors)
    category_part = f" (category: {category})" if category else ""
    return (
        f"DATA_UNAVAILABLE: Data unavailable for '{method}'{category_part}. All configured data vendors failed: {details}. "
        "Try again later or configure a working fallback data vendor."
    )


def _summarize_vendor_error(exc: Exception) -> str:
    if isinstance(exc, (ChinaDataUnavailableError, DataUnavailableError)):
        return str(exc)
    if isinstance(exc, TavilyUnavailableError):
        return str(exc)
    if isinstance(exc, YFRateLimitError):
        return "rate limited by Yahoo Finance"
    if isinstance(exc, AlphaVantageRateLimitError):
        return "rate limited by Alpha Vantage"
    return str(exc)
