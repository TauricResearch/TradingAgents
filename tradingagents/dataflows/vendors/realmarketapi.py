"""RealMarketAPI vendor: daily OHLCV and indicators for forex, metals and crypto.

RealMarketAPI (https://realmarketapi.com) quotes spot instruments under their
broker names (EURUSD, XAUUSD, BTCUSD). It does not cover equities, so it is meant
for FX, gold and crypto analyses, either alone or ahead of yfinance in a chain.

Two endpoints are used:

- ``/candle`` returns a recent window of D1 candles in one request. It serves
  any range that window reaches, and is the only source for indicators.
- ``/history`` returns 1-hour candles, newest first, a page at a time. Older
  ``get_stock_data`` ranges are paged from it and resampled to daily bars.

Daily bars are dated by UTC calendar day. The key is read from ``REALMARKETAPI_API_KEY``; if
it is unset the vendor raises ``RealMarketAPINotConfiguredError`` so the routing
layer treats it as "unavailable" rather than a hard crash.
"""

import os
from datetime import datetime, timedelta

import pandas as pd
import requests
from dateutil.relativedelta import relativedelta
from stockstats import wrap

from tradingagents.dataflows.errors import (
    NoMarketDataError,
    VendorNotConfiguredError,
    VendorUnavailableError,
)
from tradingagents.dataflows.net import get_scrubbed
from tradingagents.dataflows.vendors.yahoo.common import price_text
from tradingagents.dataflows.vendors.yahoo.market import INDICATOR_DESCRIPTIONS
from tradingagents.dataflows.vendors.yahoo.ohlcv import _assert_ohlcv_not_stale

API_BASE_URL = "https://api.realmarketapi.com/api/v1"

# Network timeout (seconds) so a stalled request can't hang the agents,
# mirroring the Alpha Vantage and FRED clients.
REQUEST_TIMEOUT = 30

# The API clamps pageSize to 1000.
HISTORY_PAGE_SIZE = 1000

# A page of 1000 hourly candles spans about 41 days of round-the-clock trading
# (crypto) and about eight weeks of forex, so 12 pages reach back roughly 16
# months for crypto and further for forex. The cap bounds the requests (and
# quota) one call can spend; a longer range keeps its most recent part and says so.
MAX_HISTORY_PAGES = 12

# Broker feeds open a D1 candle at the server's midnight, which for the common
# UTC+2/UTC+3 servers is 21:00 or 22:00 UTC on the previous day. Dating a D1
# bar by its open plus half a day lands both that and a 00:00 UTC open on the
# day the bar mostly covers.
_D1_DATE_SHIFT = pd.Timedelta(hours=12)

# Error codes from the API's problem+json body, grouped by router reaction.
_INVALID_KEY_CODES = {"ERR_0005_INVALID_API_KEY"}
_QUOTA_CODES = {"ERR_0017_REQUEST_QUOTA_EXCEEDED"}
_NO_DATA_CODES = {"ERR_0001_DATA_NOT_FOUND", "ERR_0008_SYMBOL_NOT_SUPPORTED"}


class RealMarketAPINotConfiguredError(VendorNotConfiguredError):
    """Raised when RealMarketAPI is selected but no valid API key is configured."""


class RealMarketAPIRateLimitError(VendorUnavailableError):
    """Raised when the key's request quota is exhausted."""


def get_api_key() -> str:
    """Retrieve the RealMarketAPI key from the environment."""
    api_key = os.getenv("REALMARKETAPI_API_KEY")
    if not api_key:
        raise RealMarketAPINotConfiguredError(
            "REALMARKETAPI_API_KEY environment variable is not set. "
            "Get a key at https://realmarketapi.com."
        )
    return api_key


def to_api_symbol(symbol: str) -> str:
    """Map a broker or Yahoo-style symbol to RealMarketAPI's (XAUUSD+, EURUSD=X, BTC-USD)."""
    s = symbol.strip().upper().rstrip("+").removesuffix("=X")
    return s.replace("-", "").replace("/", "")


def _raise_for_problem(response, symbol: str, canonical: str, api_key: str) -> None:
    """Turn a 4xx problem+json answer into the matching VendorError."""
    try:
        errors = response.json().get("errors") or []
    except ValueError:
        errors = []
    first = errors[0] if errors and isinstance(errors[0], dict) else {}
    code = first.get("errorCode", "")
    message = first.get("message") or first.get("reason") or response.reason or ""
    detail = f"{code}: {message}".strip(": ").replace(api_key, "***")

    if code in _INVALID_KEY_CODES or response.status_code == 401:
        raise RealMarketAPINotConfiguredError(f"RealMarketAPI rejected the API key ({detail})")
    if code in _QUOTA_CODES or response.status_code == 429:
        raise RealMarketAPIRateLimitError(f"RealMarketAPI request quota exceeded ({detail})")
    if code in _NO_DATA_CODES:
        raise NoMarketDataError(symbol, canonical, detail)
    # Anything else (an invalid range, a timeframe the plan excludes) is about
    # the request, not the instrument.
    raise VendorUnavailableError(
        f"RealMarketAPI rejected the request (HTTP {response.status_code}, {detail})"
    )


def _request(path: str, params: dict, symbol: str, canonical: str) -> dict:
    """GET an endpoint, raising the repo's VendorError types on failure."""
    api_key = get_api_key()
    try:
        response = get_scrubbed(
            f"{API_BASE_URL}/{path}",
            params={**params, "apiKey": api_key},
            timeout=REQUEST_TIMEOUT,
            secret=api_key,
            passthrough=range(400, 500),
        )
    except requests.RequestException as e:
        # get_scrubbed has already removed the key from the message.
        raise VendorUnavailableError(f"RealMarketAPI request failed: {e}") from e
    if response.status_code >= 400:
        _raise_for_problem(response, symbol, canonical, api_key)
    try:
        return response.json()
    except ValueError as e:
        raise VendorUnavailableError("RealMarketAPI returned a body that is not JSON") from e


def _to_frame(rows: list) -> pd.DataFrame:
    """API candles as a Date/Open/High/Low/Close/Volume frame, oldest first.

    ``openTime`` carries an offset; dates are converted to naive UTC so every
    bar falls on the same calendar whatever offset it was sent with.
    """
    fields = ["openTime", "openPrice", "highPrice", "lowPrice", "closePrice", "volume"]
    raw = pd.DataFrame(rows, columns=fields)
    frame = pd.DataFrame({
        "Date": pd.to_datetime(raw["openTime"], utc=True).dt.tz_localize(None),
        "Open": pd.to_numeric(raw["openPrice"], errors="coerce"),
        "High": pd.to_numeric(raw["highPrice"], errors="coerce"),
        "Low": pd.to_numeric(raw["lowPrice"], errors="coerce"),
        "Close": pd.to_numeric(raw["closePrice"], errors="coerce"),
        "Volume": pd.to_numeric(raw["volume"], errors="coerce"),
    })
    return frame.dropna(subset=["Close"]).sort_values("Date").reset_index(drop=True)


def _resample_daily(hours: pd.DataFrame) -> pd.DataFrame:
    """Aggregate oldest-first hourly bars into UTC calendar-day bars.

    Each hour is placed by its own UTC open, so no shift is needed here; a day
    built this way runs 00:00-24:00 UTC, while a broker's D1 candle runs from
    its server midnight, so the two can differ by the hours in between.
    """
    daily = hours.groupby(hours["Date"].dt.normalize()).agg(
        Open=("Open", "first"),
        High=("High", "max"),
        Low=("Low", "min"),
        Close=("Close", "last"),
        Volume=("Volume", "sum"),
    )
    return daily.rename_axis("Date").reset_index()


def _recent_daily(symbol: str, canonical: str) -> pd.DataFrame:
    """The recent window of D1 candles from ``/candle``, oldest first."""
    body = _request("candle", {"symbolCode": canonical, "timeFrame": "D1"}, symbol, canonical)
    daily = _to_frame(body.get("data") or [])
    daily["Date"] = (daily["Date"] + _D1_DATE_SHIFT).dt.normalize()
    return daily


def _history_daily(
    symbol: str, canonical: str, start: datetime, end: datetime
) -> tuple[pd.DataFrame, bool]:
    """Daily bars for ``[start, end]`` from paged hourly ``/history``.

    Pages run newest first, so a range longer than MAX_HISTORY_PAGES keeps its
    most recent part. Returns the bars and whether the range was cut short.
    """
    params = {
        "symbolCode": canonical,
        "startTime": start.strftime("%Y-%m-%dT00:00:00Z"),
        # The day after end, so the whole end day is inside the window.
        "endTime": (end + timedelta(days=1)).strftime("%Y-%m-%dT00:00:00Z"),
        "pageSize": HISTORY_PAGE_SIZE,
    }
    rows: list = []
    page, total_pages = 1, 1
    while page <= min(total_pages, MAX_HISTORY_PAGES):
        body = _request("history", {**params, "pageNumber": page}, symbol, canonical)
        data = body.get("data") or []
        if not data:
            break
        rows.extend(data)
        total_pages = int(body.get("totalPages") or 1)
        page += 1

    daily = _resample_daily(_to_frame(rows))
    truncated = total_pages > MAX_HISTORY_PAGES
    if truncated and not daily.empty:
        # The oldest day fetched is only partly covered; a partial bar would
        # misstate its open, high and low.
        daily = daily.iloc[1:].reset_index(drop=True)
    return daily, truncated


def get_stock(symbol: str, start_date: str, end_date: str) -> str:
    """Daily OHLCV for ``symbol`` between ``start_date`` and ``end_date`` (inclusive).

    Served from the recent D1 window when it reaches back to ``start_date``,
    otherwise resampled from paged hourly history.
    """
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    canonical = to_api_symbol(symbol)

    daily, truncated = _recent_daily(symbol, canonical), False
    if daily.empty or daily["Date"].iloc[0] > start:
        daily, truncated = _history_daily(symbol, canonical, start, end)

    # The D1 window runs to today; trim it so a historical run sees no later bar.
    data = daily[(daily["Date"] >= start) & (daily["Date"] <= end)]
    if data.empty:
        raise NoMarketDataError(symbol, canonical, f"no rows between {start_date} and {end_date}")
    _assert_ohlcv_not_stale(data, end_date, symbol, canonical)

    data = data.assign(Date=data["Date"].dt.strftime("%Y-%m-%d"))
    for col in ("Open", "High", "Low", "Close"):
        data[col] = data[col].map(price_text, na_action="ignore")

    label = canonical if canonical == symbol.upper() else f"{canonical} (from {symbol})"
    header = f"# Stock data for {label} from {start_date} to {end_date}\n"
    header += f"# Total records: {len(data)}\n"
    if truncated:
        header += (
            f"# Note: the range exceeds {MAX_HISTORY_PAGES} pages of hourly history; "
            f"rows start at {data['Date'].iloc[0]}, not {start_date}\n"
        )
    return header + "\n" + data.to_csv(index=False, lineterminator="\n")


def get_indicator(symbol: str, indicator: str, as_of_date: str, look_back_days: int) -> str:
    """One stockstats indicator per day over the look-back window, as yfinance reports it.

    Computed from the recent D1 window only, so a long average (e.g. the 200
    SMA) reads N/A when the window holds too few bars, and an ``as_of_date``
    older than the window has no data.
    """
    if indicator not in INDICATOR_DESCRIPTIONS:
        raise ValueError(
            f"Indicator {indicator} is not supported. Please choose from: {list(INDICATOR_DESCRIPTIONS)}"
        )

    as_of_dt = datetime.strptime(as_of_date, "%Y-%m-%d")
    before = as_of_dt - relativedelta(days=look_back_days)
    canonical = to_api_symbol(symbol)

    # Drop bars after as_of_date before computing, so no value sees the future.
    daily = _recent_daily(symbol, canonical)
    daily = daily[daily["Date"] <= as_of_dt].reset_index(drop=True)
    if daily.empty:
        raise NoMarketDataError(
            symbol, canonical, f"the recent daily window does not reach back to {as_of_date}"
        )
    _assert_ohlcv_not_stale(daily, as_of_date, symbol, canonical)

    values = wrap(daily.copy())[indicator].to_numpy()
    by_date = {
        date.strftime("%Y-%m-%d"): "N/A" if pd.isna(value) else str(value)
        for date, value in zip(daily["Date"], values, strict=True)
    }
    first_bar = daily["Date"].iloc[0]

    lines = []
    day = as_of_dt
    while day >= before:
        key = day.strftime("%Y-%m-%d")
        if key in by_date:
            value = by_date[key]
        elif day < first_bar:
            value = "N/A: before the start of RealMarketAPI's recent daily window"
        else:
            value = "N/A: Not a trading day (weekend or holiday)"
        lines.append(f"{key}: {value}\n")
        day -= relativedelta(days=1)

    return (
        f"## {indicator} values from {before.strftime('%Y-%m-%d')} to {as_of_date}:\n\n"
        + "".join(lines)
        + "\n\n"
        + INDICATOR_DESCRIPTIONS[indicator]
    )
