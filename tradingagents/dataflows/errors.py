"""Vendor data-error taxonomy.

A single hierarchy so the routing layer reacts by *behavior*, not by vendor:
every condition where a vendor cannot return usable data derives from
``VendorError``, and the router catches the base types. A new vendor raises
these (or a thin vendor-named subclass) and needs no new ``except`` clause.

    VendorError
    ├── NoMarketDataError          no usable rows (empty result OR stale data)
    ├── VendorRateLimitError       transient throttle -> skip to next vendor
    └── VendorNotConfiguredError   missing API key/config -> vendor unavailable

The number of types is the number of distinct router reactions, not the number
of human-describable causes: empty and stale data get identical handling, so
they share ``NoMarketDataError`` and differ only in the free-text ``detail``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


class VendorError(Exception):
    """Base for any condition where a vendor could not return usable data."""


class NoMarketDataError(VendorError):
    """A vendor returned no usable rows for a symbol (empty result or stale data).

    Carries both the symbol the user requested and the canonical symbol the
    vendor was actually queried with, plus a free-text ``detail``, so callers
    can build a clear message instead of emitting a vendor-specific empty
    string into the data channel.
    """

    def __init__(self, symbol: str, canonical: str | None = None, detail: str = ""):
        self.symbol = symbol
        self.canonical = canonical or symbol
        self.detail = detail
        msg = f"No market data for {symbol!r}"
        if canonical and canonical != symbol:
            msg += f" (queried as {canonical!r})"
        if detail:
            msg += f": {detail}"
        super().__init__(msg)


class VendorRateLimitError(VendorError):
    """A vendor throttled the request; the router skips to the next vendor."""


class ProviderRateLimitedError(VendorRateLimitError):
    """A named provider rejected a request because its rate limit was reached.

    This is deliberately a small, safe error payload.  Provider response bodies
    can contain request identifiers or implementation detail and must never be
    surfaced through the local web API.
    """

    code = "PROVIDER_RATE_LIMITED"

    def __init__(
        self,
        provider: str,
        *,
        observed_at: str | None = None,
        retry_after: str | None = None,
        cache_status: str = "miss",
    ):
        self.provider = provider
        self.observed_at = observed_at or datetime.now(UTC).isoformat()
        self.retry_after = retry_after
        self.cache_status = cache_status
        super().__init__(f"{provider} is temporarily rate limited")

    def with_cache_status(self, cache_status: str) -> ProviderRateLimitedError:
        return ProviderRateLimitedError(
            self.provider,
            observed_at=self.observed_at,
            retry_after=self.retry_after,
            cache_status=cache_status,
        )

    def public_detail(self) -> dict[str, Any]:
        detail: dict[str, Any] = {
            "code": self.code,
            "message": "Yahoo Finance is temporarily rate limited. Try again later.",
            "provider": self.provider,
            "observed_at": self.observed_at,
            "cache_status": self.cache_status,
        }
        if self.retry_after:
            detail["retry_after"] = self.retry_after
        return detail


class ProviderTimedOutError(VendorError):
    """A named provider did not respond within the configured request timeout."""

    code = "PROVIDER_TIMED_OUT"

    def __init__(
        self,
        provider: str,
        *,
        timeout_seconds: float,
        observed_at: str | None = None,
        cache_status: str = "miss",
    ):
        self.provider = provider
        self.timeout_seconds = timeout_seconds
        self.observed_at = observed_at or datetime.now(UTC).isoformat()
        self.cache_status = cache_status
        super().__init__(f"{provider} timed out")

    def with_cache_status(self, cache_status: str) -> ProviderTimedOutError:
        return ProviderTimedOutError(
            self.provider,
            timeout_seconds=self.timeout_seconds,
            observed_at=self.observed_at,
            cache_status=cache_status,
        )

    def public_detail(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": "Yahoo Finance did not respond in time. Retry when you are ready.",
            "provider": self.provider,
            "observed_at": self.observed_at,
            "cache_status": self.cache_status,
            "timeout_seconds": self.timeout_seconds,
        }


class VendorNotConfiguredError(VendorError, ValueError):
    """A vendor was selected but its API key/configuration is missing.

    Also a ``ValueError`` so existing callers that catch ``ValueError`` keep
    working while the routing layer can treat it as "vendor unavailable".
    """
