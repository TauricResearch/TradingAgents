"""Adapter interfaces and transport for the Pro ingestion layer.

Every feed adapter produces typed Phase-0 contracts (OHLCVBar, SpotQuote,
MetricReading) — never prompt strings; the LLM-facing rendering happens in
the agent layer. Every adapter takes an injectable transport (or loader
callable) so tests and backtests run without network access.

Errors reuse the base framework's taxonomy (dataflows.errors): the number
of error types equals the number of distinct caller reactions.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

import requests

from tradingagents.contracts import MetricReading, OHLCVBar, SpotQuote, Timeframe
from tradingagents.dataflows.errors import VendorRateLimitError

DEFAULT_TIMEOUT = 30.0
_USER_AGENT = "tradingagents-pro/0.1"


class HttpTransport(Protocol):
    """Minimal JSON-over-HTTP surface adapters depend on."""

    def get_json(self, url: str, params: dict | None = None) -> dict | list: ...


class RequestsTransport:
    """Default transport backed by ``requests`` with typed throttle errors."""

    def __init__(
        self,
        session: requests.Session | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        headers: dict | None = None,
    ):
        self._session = session or requests.Session()
        self._timeout = timeout
        self._headers = {"User-Agent": _USER_AGENT, **(headers or {})}

    def get_json(self, url: str, params: dict | None = None) -> dict | list:
        response = self._session.get(
            url, params=params, timeout=self._timeout, headers=self._headers
        )
        # 418 is Binance's repeat-offender throttle ban; treat like 429 so
        # callers back off instead of retrying into a longer ban.
        if response.status_code in (429, 418):
            raise VendorRateLimitError(f"HTTP {response.status_code} from {url}")
        response.raise_for_status()
        return response.json()


@runtime_checkable
class BarsFeed(Protocol):
    """Produces validated OHLCV bars for a symbol/timeframe."""

    name: str

    def get_bars(
        self,
        symbol: str,
        timeframe: Timeframe,
        *,
        limit: int = 250,
        end: datetime | None = None,
    ) -> list[OHLCVBar]: ...


@runtime_checkable
class QuoteFeed(Protocol):
    name: str

    def get_quote(self, symbol: str) -> SpotQuote: ...


@runtime_checkable
class MetricsFeed(Protocol):
    """Produces named observations (macro series, on-chain, derivatives)."""

    name: str

    def get_metrics(self) -> list[MetricReading]: ...
