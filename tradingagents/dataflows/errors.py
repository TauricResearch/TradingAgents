"""Vendor data-error taxonomy.

A single hierarchy so the routing layer reacts by *behavior*, not by vendor:
every condition where a vendor cannot return usable data derives from
``VendorError``, and the router catches the base types. A new vendor raises
these (or a thin vendor-named subclass) and needs no new ``except`` clause.

    VendorError
    ├── NoMarketDataError          no usable rows (empty result OR stale data)
    ├── VendorRateLimitError       transient throttle -> skip to next vendor
    ├── VendorHTTPError            typed direct-HTTP response failure
    └── VendorNotConfiguredError   missing API key/config -> vendor unavailable

The number of types is the number of distinct router reactions, not the number
of human-describable causes: empty and stale data get identical handling, so
they share ``NoMarketDataError`` and differ only in the free-text ``detail``.
"""

from __future__ import annotations


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


class RateLimitError(VendorRateLimitError):
    """HTTP-provider rate limit with the router's standard fallback semantics.

    This deliberately names the transport-level condition without coupling the
    routing layer to a particular provider (EastMoney, Sina, and a future
    direct HTTP source can all raise it).
    """


class VendorHTTPError(VendorError):
    """A provider returned a non-success HTTP response.

    ``status_code`` is structured so retry and circuit-breaker policy does not
    have to parse a vendor's human-readable response body.
    """

    def __init__(self, provider: str, status_code: int, detail: str = "") -> None:
        self.provider = provider
        self.status_code = status_code
        self.detail = detail
        message = f"{provider} HTTP {status_code}"
        if detail:
            message += f": {detail}"
        super().__init__(message)


class VendorAccessDeniedError(VendorHTTPError):
    """A provider denied access (403); retrying would be unsafe and pointless."""


class VendorNotConfiguredError(VendorError, ValueError):
    """A vendor was selected but its API key/configuration is missing.

    Also a ``ValueError`` so existing callers that catch ``ValueError`` keep
    working while the routing layer can treat it as "vendor unavailable".
    """


class DataSourceUnavailableError(RuntimeError):
    """All eligible providers for a required data capability were unavailable.

    This is deliberately separate from ``VendorError``: it is a router-level
    aggregate after every provider attempt (or cooldown skip), not an error
    emitted by one provider adapter.
    """


class DataUnavailableError(DataSourceUnavailableError):
    """Compatibility name for a router-level unavailable data source error."""
