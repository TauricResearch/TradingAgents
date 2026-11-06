"""OKX public market data: contract specs, closed candles, last price, funding history.

Public endpoints only, so no API key is needed. Requests go through
``requests``; OKX answers urllib's default User-Agent with 403.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import requests

BASE_URL = "https://www.okx.com"
MINUTE_MS = 60_000
DAY_MS = 86_400_000

# Rows per page. OKX cuts a larger limit down to 300 on candles and 400 on funding.
_CANDLE_PAGE = 300
_FUNDING_PAGE = 400
_PAGE_PAUSE = 0.1  # seconds between pages; history-candles allows about 20 requests per 2 s
_RETRY_PAUSES = (1, 2)  # seconds before the second and third try of a request that failed


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
        """Spec of a perpetual, from /api/v5/public/instruments?instType=SWAP; OKXError
        when OKX lists no such swap."""
        rows = self._get("/api/v5/public/instruments", instType="SWAP", instId=inst_id)
        if not rows:
            raise OKXError(f"OKX lists no SWAP instrument {inst_id}")
        row = rows[0]
        return ContractSpec(
            contract_value=float(row["ctVal"]),
            lot_size=float(row["lotSz"]),
            min_size=float(row["minSz"]),
        )

    def last_price(self, inst_id: str) -> float:
        """Last traded price of a swap or spot instrument, from /api/v5/market/ticker;
        OKXError when OKX has no ticker for it."""
        rows = self._get("/api/v5/market/ticker", instId=inst_id)
        if not rows:
            raise OKXError(f"OKX has no ticker for {inst_id}")
        return float(rows[0]["last"])

    def bars(self, inst_id: str, bar: str, start_ms: int, end_ms: int) -> list[Bar]:
        """Closed candles with ``start_ms <= ts < end_ms``, oldest first, no duplicates.

        ``bar`` is an OKX bar size, here "1m" or "1Dutc"; works for swap and spot
        instruments. Only candles whose ``confirm`` is "1" are returned, so a range
        reaching into the present stops at the last closed candle. Pages back
        through /api/v5/market/history-candles as far as ``start_ms`` needs.
        """
        params = {"instId": inst_id, "bar": bar, "limit": _CANDLE_PAGE}
        rows = self._history("/api/v5/market/history-candles", params, start_ms, end_ms, ts_key=0)
        # A row is [ts, open, high, low, close, vol, volCcy, volCcyQuote, confirm].
        return [
            Bar(int(r[0]), float(r[1]), float(r[2]), float(r[3]), float(r[4]))
            for r in rows
            if r[8] == "1"
        ]

    def funding(self, inst_id: str, start_ms: int, end_ms: int) -> list[FundingEvent]:
        """Settled funding with ``start_ms <= ts < end_ms``, oldest first, from
        /api/v5/public/funding-rate-history."""
        params = {"instId": inst_id, "limit": _FUNDING_PAGE}
        rows = self._history(
            "/api/v5/public/funding-rate-history", params, start_ms, end_ms, ts_key="fundingTime"
        )
        # realizedRate is what settled; fundingRate stands in when OKX leaves it empty.
        return [
            FundingEvent(int(r["fundingTime"]), float(r["realizedRate"] or r["fundingRate"]))
            for r in rows
        ]

    def _get(self, path: str, **params) -> list:
        """``data`` of a GET to ``path``.

        A connection error, timeout, 429 or 5xx is retried after each pause in
        ``_RETRY_PAUSES``; the last failure is raised as is. Any other answer is read as
        JSON before its status is checked, because OKX reports e.g. an unknown instrument
        as a 400 whose body still says why: a non-zero ``code`` raises OKXError with code
        and msg. A body that is not JSON, such as the page behind a 403, raises through
        ``raise_for_status``.
        """
        for pause in (*_RETRY_PAUSES, None):  # None: no try left, so the failure is raised
            try:
                response = self.session.get(BASE_URL + path, params=params, timeout=10)
                if response.status_code == 429 or response.status_code >= 500:
                    response.raise_for_status()
                break
            except (requests.ConnectionError, requests.Timeout, requests.HTTPError):
                if pause is None:
                    raise
                time.sleep(pause)
        try:
            body = response.json()
        except ValueError:  # not JSON, so not an OKX answer
            response.raise_for_status()
            raise
        code = body.get("code")
        if code != "0":
            raise OKXError(f"{path} {params} failed with code {code}: {body.get('msg')}")
        return body["data"]

    def _history(
        self, path: str, params: dict, start_ms: int, end_ms: int, ts_key: int | str
    ) -> list:
        """Rows of a newest-first endpoint with ``start_ms <= ts < end_ms``, oldest first,
        one per timestamp; ``row[ts_key]`` is a row's timestamp.

        ``after`` asks OKX for the rows strictly older than it, so each page picks up
        just before the oldest row of the page before. Paging stops once a page
        reaches ``start_ms`` or comes back empty; a page with no row older than its
        cursor would be requested forever, so it raises OKXError instead.
        """
        rows = {}
        after = end_ms
        while True:
            cursor = after
            page = self._get(path, **params, after=cursor)
            for row in page:
                ts = int(row[ts_key])
                if start_ms <= ts < end_ms:
                    rows[ts] = row
                after = min(after, ts)
            if not page or after <= start_ms:
                break
            if after == cursor:
                raise OKXError(f"{path} {params} page after {cursor} has no older row")
            time.sleep(_PAGE_PAUSE)
        return [rows[ts] for ts in sorted(rows)]
