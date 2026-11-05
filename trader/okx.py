"""OKX public market data: contract specs, closed candles, last price, funding history.

Public endpoints only, so no API key is needed. Requests go through
``requests``; OKX answers urllib's default User-Agent with 403.
"""

from __future__ import annotations

from dataclasses import dataclass

import requests

BASE_URL = "https://www.okx.com"
MINUTE_MS = 60_000
DAY_MS = 86_400_000


class OKXError(RuntimeError):
    """OKX answered with a non-zero error code."""


@dataclass(frozen=True)
class Bar:
    """A closed candle. ``ts`` is its open time in UTC milliseconds."""

    ts: int
    open: float
    high: float
    low: float
    close: float


@dataclass(frozen=True)
class ContractSpec:
    contract_value: float  # coins per contract (OKX ctVal)
    lot_size: float        # contract-count increment (lotSz)
    min_size: float        # smallest order, in contracts (minSz)


@dataclass(frozen=True)
class FundingEvent:
    ts: int      # settlement time in UTC milliseconds
    rate: float  # realized rate; positive means longs pay shorts


class OKX:
    def __init__(self, session: requests.Session | None = None):
        self.session = session or requests.Session()

    def contract_spec(self, inst_id: str) -> ContractSpec:
        """Spec of a perpetual, from /api/v5/public/instruments?instType=SWAP."""
        raise NotImplementedError

    def last_price(self, inst_id: str) -> float:
        """Last traded price of a swap or spot instrument, from /api/v5/market/ticker."""
        raise NotImplementedError

    def bars(self, inst_id: str, bar: str, start_ms: int, end_ms: int) -> list[Bar]:
        """Closed candles with ``start_ms <= ts < end_ms``, oldest first, no duplicates.

        ``bar`` is an OKX bar size, here "1m" or "1Dutc"; works for swap and spot
        instruments. Only candles whose ``confirm`` is "1" are returned, so a range
        reaching into the present stops at the last closed candle. Pages back
        through /api/v5/market/history-candles as far as ``start_ms`` needs.
        """
        raise NotImplementedError

    def funding(self, inst_id: str, start_ms: int, end_ms: int) -> list[FundingEvent]:
        """Settled funding with ``start_ms <= ts < end_ms``, oldest first, from
        /api/v5/public/funding-rate-history."""
        raise NotImplementedError
