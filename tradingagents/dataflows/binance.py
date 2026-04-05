"""Binance public REST API data fetcher.

Covers three endpoints as per Task 3 design:
  - klines:  https://api.binance.com/api/v3/klines
  - ticker:  https://api.binance.com/api/v3/ticker/
  - depth:   https://api.binance.com/api/v3/depth

No API key is required for these public market-data endpoints.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Annotated, Optional

import pandas as pd
import requests

from .binance_models import DepthParams, Kline, KlineInterval, KlineParams, TickerParams
from .stockstats_utils import _clean_dataframe

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.binance.com"

# Binance rate-limit: HTTP 429 → back off before retrying
_MAX_RETRIES = 3
_BASE_DELAY = 2.0  # seconds


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get(path: str, params: dict) -> dict | list:
    """Execute a GET request against the Binance REST API with retry on 429."""
    url = f"{_BASE_URL}{path}"
    for attempt in range(_MAX_RETRIES + 1):
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 429:
            if attempt < _MAX_RETRIES:
                delay = _BASE_DELAY * (2 ** attempt)
                logger.warning(
                    "Binance rate limited, retrying in %.0fs (attempt %d/%d)",
                    delay, attempt + 1, _MAX_RETRIES,
                )
                time.sleep(delay)
                continue
            response.raise_for_status()
        response.raise_for_status()
        return response.json()
    # unreachable but satisfies type checkers
    raise RuntimeError("Binance request failed after all retries")


def _date_to_ms(date_str: str) -> int:
    """Convert a YYYY-MM-DD string to a Unix millisecond timestamp (UTC midnight)."""
    dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def _fetch_klines_range(params: KlineParams) -> list[Kline]:
    """Fetch all klines for the given params, auto-paginating if needed."""
    query: dict = {
        "symbol": params.symbol.upper(),
        "interval": params.interval.value,
        "limit": min(params.limit, 1000),
    }
    if params.start_time is not None:
        query["startTime"] = params.start_time
    if params.end_time is not None:
        query["endTime"] = params.end_time

    all_klines: list[Kline] = []
    while True:
        raw: list = _get("/api/v3/klines", query)  # type: ignore[assignment]
        if not raw:
            break
        batch = [Kline.from_raw(r) for r in raw]
        all_klines.extend(batch)
        if len(raw) < query["limit"]:
            break  # no more pages
        # advance start to one ms after the last close_time
        query["startTime"] = batch[-1].close_time + 1
        if params.end_time is not None and query["startTime"] > params.end_time:
            break

    return all_klines


def _klines_to_dataframe(klines: list[Kline], symbol: str) -> pd.DataFrame:
    """Convert a list of Kline objects to a normalised OHLCV DataFrame."""
    if not klines:
        return pd.DataFrame()

    rows = [
        {
            "Date": datetime.fromtimestamp(k.open_time / 1000, tz=timezone.utc)
            .strftime("%Y-%m-%d"),
            "Open": k.open,
            "High": k.high,
            "Low": k.low,
            "Close": k.close,
            "Volume": k.volume,
        }
        for k in klines
    ]
    df = pd.DataFrame(rows)
    df["Date"] = pd.to_datetime(df["Date"])
    return df


# ---------------------------------------------------------------------------
# Public API — OHLCV / stock-data equivalent
# ---------------------------------------------------------------------------

def get_binance_klines(
    symbol: Annotated[str, "Binance trading pair, e.g. BTCUSDT"],
    start_date: Annotated[str, "Start date in YYYY-MM-DD format"],
    end_date: Annotated[str, "End date in YYYY-MM-DD format"],
    interval: KlineInterval = KlineInterval.ONE_DAY,
) -> str:
    """Fetch OHLCV candlestick data from Binance for the given symbol and date range.

    This is the Binance equivalent of ``get_YFin_data_online``.
    Returns a CSV string with a descriptive header.
    """
    datetime.strptime(start_date, "%Y-%m-%d")
    datetime.strptime(end_date, "%Y-%m-%d")

    params = KlineParams(
        symbol=symbol.upper(),
        interval=interval,
        start_time=_date_to_ms(start_date),
        end_time=_date_to_ms(end_date),
        limit=1000,
    )
    klines = _fetch_klines_range(params)
    if not klines:
        return f"No kline data found for symbol '{symbol}' between {start_date} and {end_date}"

    df = _klines_to_dataframe(klines, symbol)
    for col in ["Open", "High", "Low", "Close"]:
        df[col] = df[col].round(2)

    header = f"# Binance kline data for {symbol.upper()} from {start_date} to {end_date}\n"
    header += f"# Interval: {interval.value}\n"
    header += f"# Total records: {len(df)}\n"
    header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    return header + df.to_csv(index=False)


# ---------------------------------------------------------------------------
# Public API — technical indicators (re-uses stockstats on Binance data)
# ---------------------------------------------------------------------------

def get_binance_indicators_window(
    symbol: Annotated[str, "Binance trading pair, e.g. BTCUSDT"],
    indicator: Annotated[str, "Technical indicator name understood by stockstats"],
    curr_date: Annotated[str, "Current trading date, YYYY-MM-DD"],
    look_back_days: Annotated[int, "How many calendar days to look back"],
    interval: KlineInterval = KlineInterval.ONE_DAY,
) -> str:
    """Calculate a technical indicator over a look-back window using Binance kline data.

    Mirrors ``get_stock_stats_indicators_window`` but sources data from Binance.
    """
    from dateutil.relativedelta import relativedelta
    from stockstats import wrap

    INDICATOR_DESCRIPTIONS: dict[str, str] = {
        "close_50_sma": "50 SMA: Medium-term trend indicator.",
        "close_200_sma": "200 SMA: Long-term trend benchmark.",
        "close_10_ema": "10 EMA: Responsive short-term average.",
        "macd": "MACD: Momentum via EMA differences.",
        "macds": "MACD Signal: EMA smoothing of the MACD line.",
        "macdh": "MACD Histogram: Gap between MACD and its signal.",
        "rsi": "RSI: Momentum indicator for overbought/oversold conditions.",
        "boll": "Bollinger Middle: 20 SMA as basis for Bollinger Bands.",
        "boll_ub": "Bollinger Upper Band: 2 std deviations above middle.",
        "boll_lb": "Bollinger Lower Band: 2 std deviations below middle.",
        "atr": "ATR: Average True Range, measures volatility.",
        "vwma": "VWMA: Volume-weighted moving average.",
        "mfi": "MFI: Money Flow Index combining price and volume.",
    }

    if indicator not in INDICATOR_DESCRIPTIONS:
        raise ValueError(
            f"Indicator '{indicator}' is not supported. "
            f"Choose from: {list(INDICATOR_DESCRIPTIONS.keys())}"
        )

    curr_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    before_dt = curr_dt - relativedelta(days=look_back_days)
    # Fetch extra history so indicators have enough warm-up data
    fetch_start = curr_dt - relativedelta(years=1)

    params = KlineParams(
        symbol=symbol.upper(),
        interval=interval,
        start_time=_date_to_ms(fetch_start.strftime("%Y-%m-%d")),
        end_time=_date_to_ms(curr_date),
        limit=1000,
    )
    klines = _fetch_klines_range(params)
    if not klines:
        return f"No data available for '{symbol}' up to {curr_date}"

    df = _klines_to_dataframe(klines, symbol)
    df = _clean_dataframe(df)
    df = wrap(df)
    df["Date"] = df["Date"].dt.strftime("%Y-%m-%d")
    df[indicator]  # trigger stockstats calculation

    date_map: dict[str, str] = {
        row["Date"]: str(row[indicator]) if not pd.isna(row[indicator]) else "N/A"
        for _, row in df.iterrows()
    }

    lines: list[str] = []
    cur = curr_dt
    while cur >= before_dt:
        date_str = cur.strftime("%Y-%m-%d")
        value = date_map.get(date_str, "N/A: Not a trading day")
        lines.append(f"{date_str}: {value}")
        cur -= relativedelta(days=1)

    result = (
        f"## {indicator} values from {before_dt.strftime('%Y-%m-%d')} to {curr_date}:\n\n"
        + "\n".join(lines)
        + f"\n\n{INDICATOR_DESCRIPTIONS[indicator]}"
    )
    return result


# ---------------------------------------------------------------------------
# Public API — ticker (24hr stats)
# ---------------------------------------------------------------------------

def get_binance_ticker(
    symbol: Annotated[str, "Binance trading pair, e.g. BTCUSDT"],
) -> str:
    """Fetch 24-hour ticker statistics for a symbol from Binance.

    Returns a formatted string of key price and volume metrics.
    """
    params = TickerParams(symbol=symbol.upper())
    query = {"symbol": params.symbol, "type": params.ticker_type}
    data: dict = _get("/api/v3/ticker/24hr", query)  # type: ignore[assignment]

    fields = [
        ("Symbol", data.get("symbol")),
        ("Price Change", data.get("priceChange")),
        ("Price Change %", data.get("priceChangePercent")),
        ("Weighted Avg Price", data.get("weightedAvgPrice")),
        ("Prev Close Price", data.get("prevClosePrice")),
        ("Last Price", data.get("lastPrice")),
        ("Last Qty", data.get("lastQty")),
        ("Bid Price", data.get("bidPrice")),
        ("Ask Price", data.get("askPrice")),
        ("Open Price", data.get("openPrice")),
        ("High Price", data.get("highPrice")),
        ("Low Price", data.get("lowPrice")),
        ("Volume", data.get("volume")),
        ("Quote Volume", data.get("quoteVolume")),
        ("Count (trades)", data.get("count")),
    ]

    header = f"# Binance 24hr Ticker for {symbol.upper()}\n"
    header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    lines = [f"{label}: {value}" for label, value in fields if value is not None]
    return header + "\n".join(lines)


# ---------------------------------------------------------------------------
# Public API — order book depth
# ---------------------------------------------------------------------------

def get_binance_depth(
    symbol: Annotated[str, "Binance trading pair, e.g. BTCUSDT"],
    limit: Annotated[int, "Number of price levels to return (max 5000)"] = 100,
) -> str:
    """Fetch the current order book (bids and asks) for a symbol from Binance.

    Returns a formatted string with the top bid/ask levels and spread.
    """
    params = DepthParams(symbol=symbol.upper(), limit=limit)
    data: dict = _get("/api/v3/depth", {"symbol": params.symbol, "limit": params.limit})  # type: ignore[assignment]

    bids: list[list[str]] = data.get("bids", [])
    asks: list[list[str]] = data.get("asks", [])

    best_bid = float(bids[0][0]) if bids else None
    best_ask = float(asks[0][0]) if asks else None
    spread = round(best_ask - best_bid, 8) if (best_bid and best_ask) else None

    header = f"# Binance Order Book Depth for {symbol.upper()}\n"
    header += f"# Levels requested: {limit}\n"
    header += f"# Last update ID: {data.get('lastUpdateId')}\n"
    header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

    lines = [
        f"Best Bid: {best_bid}",
        f"Best Ask: {best_ask}",
        f"Spread:   {spread}",
        "",
        "Top 5 Bids (price, qty):",
    ]
    for price, qty in bids[:5]:
        lines.append(f"  {price}  {qty}")
    lines.append("")
    lines.append("Top 5 Asks (price, qty):")
    for price, qty in asks[:5]:
        lines.append(f"  {price}  {qty}")

    return header + "\n".join(lines)
