"""Narrow Yahoo Finance error handling shared by instrument resolution paths."""

from __future__ import annotations

from collections.abc import Iterator

try:  # yfinance keeps this exception in a stable public module.
    from yfinance.exceptions import YFRateLimitError
except ImportError:  # pragma: no cover - supports older optional yfinance installs
    YFRateLimitError = ()  # type: ignore[assignment,misc]

from .errors import ProviderRateLimitedError


def _error_chain(error: BaseException) -> Iterator[BaseException]:
    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        yield current
        current = current.__cause__ or current.__context__


def _retry_after(error: BaseException) -> str | None:
    for item in _error_chain(error):
        response = getattr(item, "response", None)
        headers = getattr(response, "headers", None)
        if headers:
            value = headers.get("Retry-After")
            if isinstance(value, str) and value.strip():
                return value.strip()[:120]
    return None


def yahoo_rate_limit_error(error: BaseException) -> ProviderRateLimitedError | None:
    """Return a safe error only for explicit Yahoo throttling signals.

    Generic wording such as "rate limited" is intentionally not enough: it
    would turn provider bugs or local failures into a false Yahoo diagnosis.
    """
    for item in _error_chain(error):
        if YFRateLimitError and isinstance(item, YFRateLimitError):
            return ProviderRateLimitedError("yahoo_finance", retry_after=_retry_after(error))
        response = getattr(item, "response", None)
        if getattr(response, "status_code", None) == 429:
            return ProviderRateLimitedError("yahoo_finance", retry_after=_retry_after(error))
    return None
