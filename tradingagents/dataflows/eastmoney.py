"""Small, keyless EastMoney adapters behind one conservative HTTP gateway.

The public endpoints used here are optional supplemental sources.  They never
contain credentials and callers receive a typed vendor error (rather than a
partially fabricated report) when EastMoney changes an endpoint or throttles
us.  The normal router can therefore continue to another provider.
"""

from __future__ import annotations

import json
import random
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

import pandas as pd
import requests

from .china_data import ChinaDataUnavailableError
from .errors import RateLimitError, VendorAccessDeniedError, VendorHTTPError
from .ticker_utils import is_a_share_ticker, normalize_ticker_symbol, to_akshare_symbol

EASTMONEY_PUSH2_URL = "https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get"
EASTMONEY_DATACENTER_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"


@dataclass(frozen=True)
class EastMoneyRequestPolicy:
    """Bounded request policy suitable for a shared public endpoint."""

    min_interval_seconds: float = 1.0
    jitter_seconds: float = 0.2
    max_retries: int = 2
    retry_backoff_seconds: float = 1.0
    timeout_seconds: float = 10.0


class EastMoneyHTTPClient:
    """Serial, keep-alive HTTP client with explicit retry behavior.

    A single client serializes both the request and the pre-request delay.
    That is intentional: concurrent callers cannot accidentally bypass the
    public endpoint's pacing contract.  Tests can inject clock/sleeper/jitter
    functions and a session without making network calls.
    """

    def __init__(
        self,
        *,
        session: requests.Session | None = None,
        policy: EastMoneyRequestPolicy | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
        jitter: Callable[[float, float], float] = random.uniform,
    ) -> None:
        self._session = session or requests.Session()
        self._session.headers.update(
            {
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7",
                "Connection": "keep-alive",
                "User-Agent": "TradingAgents/1.0 (+https://github.com/TauricResearch/TradingAgents)",
            }
        )
        self._policy = policy or EastMoneyRequestPolicy()
        self._clock = clock
        self._sleeper = sleeper
        self._jitter = jitter
        self._lock = threading.Lock()
        self._last_request_at: float | None = None

    def get(
        self,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        timeout: float | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> requests.Response:
        with self._lock:
            self._pace()
            for attempt in range(self._policy.max_retries + 1):
                try:
                    response = self._session.get(
                        url,
                        params=params,
                        timeout=timeout or self._policy.timeout_seconds,
                        headers=headers,
                    )
                except requests.RequestException as exc:
                    if attempt == self._policy.max_retries:
                        raise VendorHTTPError("eastmoney", 0, "network request failed") from exc
                    self._backoff(attempt)
                    continue

                self._last_request_at = self._clock()
                status_code = int(response.status_code)
                if 200 <= status_code < 300:
                    return response
                if status_code == 403:
                    raise VendorAccessDeniedError("eastmoney", status_code)
                if status_code == 429:
                    if attempt == self._policy.max_retries:
                        raise RateLimitError("eastmoney rate limited (HTTP 429)")
                    self._backoff(attempt)
                    continue
                if 500 <= status_code <= 599:
                    if attempt == self._policy.max_retries:
                        raise VendorHTTPError("eastmoney", status_code)
                    self._backoff(attempt)
                    continue
                raise VendorHTTPError("eastmoney", status_code)

        raise AssertionError("unreachable")

    def _pace(self) -> None:
        if self._last_request_at is None:
            return
        elapsed = self._clock() - self._last_request_at
        target = self._policy.min_interval_seconds + self._jitter(0.0, self._policy.jitter_seconds)
        if elapsed < target:
            self._sleeper(target - elapsed)

    def _backoff(self, attempt: int) -> None:
        base = self._policy.retry_backoff_seconds * (2**attempt)
        self._sleeper(base + self._jitter(0.0, self._policy.jitter_seconds))


_default_client = EastMoneyHTTPClient()


def em_get(
    url: str,
    *,
    params: Mapping[str, Any] | None = None,
    timeout: float | None = None,
    client: EastMoneyHTTPClient | None = None,
    headers: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Get and validate one EastMoney JSON response through the shared gateway."""
    response = (client or _default_client).get(url, params=params, timeout=timeout, headers=headers)
    try:
        payload = response.json()
    except ValueError as exc:
        raise VendorHTTPError("eastmoney", int(response.status_code), "invalid JSON response") from exc
    if not isinstance(payload, dict):
        raise VendorHTTPError("eastmoney", int(response.status_code), "JSON root is not an object")
    return payload


def get_a_share_capital_flow(
    ticker: str,
    start_date: str | None = None,
    end_date: str | None = None,
) -> str:
    """Return recent A-share main/retail capital-flow rows from EastMoney.

    Dates are accepted for a consistent capability signature; the public
    endpoint returns its recent day-kline window and may not guarantee an
    arbitrary historical range.  The report makes this limitation explicit.
    """
    secid = _eastmoney_secid(ticker)
    payload = em_get(
        EASTMONEY_PUSH2_URL,
        params={
            "secid": secid,
            "klt": "101",
            "lmt": "120",
            "fields1": "f1,f2,f3,f7",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65",
        },
    )
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    lines = data.get("klines") if isinstance(data, dict) else None
    if not isinstance(lines, list) or not lines:
        raise ChinaDataUnavailableError(f"EastMoney returned no capital-flow rows for {ticker}.")
    rows = [_capital_flow_row(line) for line in lines if isinstance(line, str)]
    rows = [row for row in rows if row]
    if not rows:
        raise ChinaDataUnavailableError(f"EastMoney returned unreadable capital-flow rows for {ticker}.")
    _capture_vendor_raw(payload, metadata={"provider": "eastmoney", "dataset": "capital_flow", "ticker": ticker})
    return _format_report(
        pd.DataFrame(rows),
        title=f"China A-share capital flow for {normalize_ticker_symbol(ticker)}",
        caveat="EastMoney public endpoint; optional supplemental source, recent window only.",
        start_date=start_date,
        end_date=end_date,
    )


def get_a_share_margin_financing(ticker: str, curr_date: str | None = None) -> str:
    """Return keyless EastMoney margin-financing records for one A-share.

    EastMoney can change report schemas without notice, so the adapter keeps
    returned fields source-labeled instead of inventing a fixed financial
    interpretation.  Empty or changed responses degrade through the router.
    """
    code = _require_a_share_code(ticker)
    payload = em_get(
        EASTMONEY_DATACENTER_URL,
        params={
            "reportName": "RPTA_WEB_RZRQ_GGMX",
            "columns": "ALL",
            "filter": f'(SECURITY_CODE="{code}")',
            "pageNumber": "1",
            "pageSize": "20",
            "sortColumns": "TRADE_DATE",
            "sortTypes": "-1",
            "source": "WEB",
            "client": "WEB",
        },
    )
    rows = _extract_records(payload)
    if not rows:
        raise ChinaDataUnavailableError(f"EastMoney returned no margin-financing records for {ticker}.")
    _capture_vendor_raw(payload, metadata={"provider": "eastmoney", "dataset": "margin_financing", "ticker": ticker})
    return _format_report(
        pd.DataFrame(rows),
        title=f"China A-share margin financing for {normalize_ticker_symbol(ticker)}",
        caveat="EastMoney public endpoint; optional supplemental source.",
        as_of=curr_date,
    )


def get_a_share_capital_flow_sina(
    ticker: str,
    start_date: str | None = None,
    end_date: str | None = None,
) -> str:
    """Return A-share daily capital-flow rows from Sina (backup for EastMoney).

    Sina's MoneyFlow endpoint is on a different domain and rate-limit plane
    than EastMoney push2, so it stays usable when EastMoney bans an IP.  The
    field schema differs from the EastMoney primary source: Sina exposes net
    inflow + turnover rather than the four-tier main/large/medium/small
    breakdown, so the report labels the source explicitly rather than
    pretending the two are interchangeable.
    """
    code = _require_a_share_code(ticker)
    prefix = _sina_prefix(ticker)
    url = (
        "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/"
        f"MoneyFlow.ssl_qsfx_zjlrqs?page=1&num=120&sort=opendate&asc=0&daima={prefix}{code}"
    )
    try:
        response = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0", "Referer": "https://finance.sina.com.cn/"},
            timeout=15,
        )
    except requests.RequestException as exc:
        raise ChinaDataUnavailableError(f"Sina capital-flow request failed for {ticker}: {exc}") from exc
    text = response.text
    try:
        start = text.index("[")
        end = text.rindex("]")
        rows = json.loads(text[start : end + 1])
    except (ValueError, json.JSONDecodeError) as exc:
        raise ChinaDataUnavailableError(f"Sina returned unparseable capital-flow data for {ticker}: {exc}") from exc
    if not rows:
        raise ChinaDataUnavailableError(f"Sina returned no capital-flow rows for {ticker}.")
    data = pd.DataFrame(
        [
            {
                "Date": row.get("opendate"),
                "Close": row.get("trade"),
                "Net Inflow": row.get("netamount"),
                "Turnover": row.get("turnover"),
            }
            for row in rows
        ]
    )
    _capture_vendor_raw({"rows": rows}, metadata={"provider": "sina", "dataset": "capital_flow", "ticker": ticker})
    return _format_report(
        data,
        title=f"China A-share capital flow for {normalize_ticker_symbol(ticker)} (Sina backup)",
        caveat="Sina daily capital-flow backup source; field schema differs from EastMoney push2 (net inflow + turnover only).",
        source="sina",
        start_date=start_date,
        end_date=end_date,
    )


def _sina_prefix(ticker: str) -> str:
    """Sina quote prefix: sh for Shanghai, bj for Beijing, sz otherwise."""
    canonical = normalize_ticker_symbol(ticker)
    if canonical.endswith((".SS", ".SH")):
        return "sh"
    if canonical.endswith(".BJ"):
        return "bj"
    return "sz"


def _eastmoney_secid(ticker: str) -> str:
    code = _require_a_share_code(ticker)
    canonical = normalize_ticker_symbol(ticker)
    # EastMoney's secid convention: Shanghai=1, Shenzhen/Beijing=0.
    market = "1" if canonical.endswith((".SS", ".SH")) else "0"
    return f"{market}.{code}"


def _require_a_share_code(ticker: str) -> str:
    if not is_a_share_ticker(ticker):
        raise ChinaDataUnavailableError(f"{ticker} is not recognized as an A-share ticker.")
    return to_akshare_symbol(ticker)


def _capital_flow_row(line: str) -> dict[str, str] | None:
    fields = [part.strip() for part in line.split(",")]
    if len(fields) < 2 or not fields[0]:
        return None
    names = (
        "Date", "Main Net Inflow", "Small Net Inflow", "Medium Net Inflow",
        "Large Net Inflow", "Extra Large Net Inflow", "Close", "Pct Change",
    )
    return {name: fields[index] for index, name in enumerate(names) if index < len(fields)}


def _extract_records(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    candidates: list[Any] = [payload.get("data")]
    result = payload.get("result")
    if isinstance(result, Mapping):
        candidates.append(result.get("data"))
    for value in candidates:
        if isinstance(value, list):
            return [dict(row) for row in value if isinstance(row, Mapping)]
    return []


def _format_report(
    data: pd.DataFrame,
    *,
    title: str,
    caveat: str,
    source: str = "eastmoney",
    start_date: str | None = None,
    end_date: str | None = None,
    as_of: str | None = None,
) -> str:
    if data.empty:
        raise ChinaDataUnavailableError(f"{source} returned no rows for {title}.")
    window = ""
    if start_date or end_date:
        window = f"\n# Requested window: {start_date or '?'} to {end_date or '?'}"
    if as_of:
        window += f"\n# Requested as-of: {as_of}"
    return "\n".join(
        [
            f"# {title}",
            f"# Source: {source}",
            f"# Note: {caveat}",
            f"# Total records: {len(data)}" + window,
            "",
            data.to_csv(index=False),
        ]
    )


def _capture_vendor_raw(payload: Any, *, metadata: Mapping[str, str]) -> None:
    """Load observability after the provider has returned a usable payload."""
    from tradingagents.observability.provenance import capture_vendor_raw

    capture_vendor_raw(payload, metadata=dict(metadata))
