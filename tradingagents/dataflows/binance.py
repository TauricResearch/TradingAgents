"""Binance public REST API data fetcher.

Covers three endpoints as per Task 3 design:
  - klines:  https://fapi.binance.com/fapi/v1/klines
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
from .config import get_config

logger = logging.getLogger(__name__)

_BASE_URL = "https://fapi.binance.com"

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
    return int(dt.timestamp() * 100)


def _fetch_klines_range(params: KlineParams) -> list[Kline]:
    """Fetch all klines for the given params, auto-paginating if needed."""
    query: dict = {
        "symbol": params.symbol.upper(),
        "interval": params.interval.value,
        "limit": min(params.limit, 200),
    }
#     if params.start_time is not None:
#         query["startTime"] = params.start_time
#     if params.end_time is not None:
#         query["endTime"] = params.end_time

    all_klines: list[Kline] = []
    while True:
        raw: list = _get("/fapi/v1/klines", query)  # type: ignore[assignment]
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

def _resolve_kline_interval(override: KlineInterval | None = None) -> KlineInterval:
    """Return the KlineInterval to use, preferring config then falling back to 1d."""
    if override is not None:
        return override
    cfg_value = get_config().get("kline_interval")
    if cfg_value:
        try:
            return KlineInterval(cfg_value)
        except ValueError:
            logger.warning("Unknown kline_interval '%s' in config, using 1d.", cfg_value)
    return KlineInterval.ONE_DAY


def get_binance_klines(
    symbol: Annotated[str, "Binance trading pair, e.g. BTCUSDT"],
    start_date: Annotated[str, "Start date in YYYY-MM-DD format"],
    end_date: Annotated[str, "End date in YYYY-MM-DD format"],
    interval: KlineInterval | None = None,
) -> str:
    """Fetch OHLCV candlestick data from Binance for the given symbol and date range.

    Returns a CSV string with a descriptive header.
    """
    from datetime import timedelta as _timedelta

    cfg = get_config()
    _today = datetime.now().strftime("%Y-%m-%d")
    _two_months_ago = (datetime.now() - _timedelta(days=60)).strftime("%Y-%m-%d")

    # User-configured dates always take precedence over agent-inferred dates.
    # Without this, `start_date or cfg_value` never reaches the config because
    # the agent always passes a non-empty string.
    cfg_start = cfg.get("kline_start_date")
    cfg_end = cfg.get("kline_end_date")
    start_date = cfg_start or start_date or _two_months_ago
    end_date = cfg_end or end_date or _today
    resolved_interval = _resolve_kline_interval(interval)

    try:
        datetime.strptime(start_date, "%Y-%m-%d")
        datetime.strptime(end_date, "%Y-%m-%d")
    except ValueError as exc:
        return f"Invalid date format (expected YYYY-MM-DD): {exc}"

    params = KlineParams(
        symbol=symbol.upper(),
        interval=resolved_interval,
        start_time=_date_to_ms(start_date),
        end_time=_date_to_ms(end_date),
        limit=200,
    )
    klines = _fetch_klines_range(params)
    if not klines:
        return f"No kline data found for symbol '{symbol}' between {start_date} and {end_date}"

    df = _klines_to_dataframe(klines, symbol)
    for col in ["Open", "High", "Low", "Close"]:
        df[col] = df[col].round(2)

    header = f"# Binance kline data for {symbol.upper()} from {start_date} to {end_date}\n"
    header += f"# Interval: {resolved_interval.value}\n"
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
    interval: KlineInterval | None = None,
) -> str:
    """Calculate a technical indicator over a look-back window using Binance kline data."""
    from dateutil.relativedelta import relativedelta
    from stockstats import wrap

    resolved_interval = _resolve_kline_interval(interval)

    INDICATOR_DESCRIPTIONS: dict[str, str] = {
        "close_34_sma": "34 SMA: Short-to-medium-term Fibonacci trend indicator.",
        "close_56_sma": "56 SMA: Medium-term trend indicator.",
        "close_89_sma": "89 SMA: Long-term Fibonacci trend benchmark.",
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

    # Honor user-configured end date if set; otherwise use agent-provided curr_date
    cfg = get_config()
    cfg_end = cfg.get("kline_end_date")
    if cfg_end:
        curr_date = cfg_end

    curr_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    before_dt = curr_dt - relativedelta(days=look_back_days)

    # Honor user-configured start date if set; otherwise look back 1 year for warm-up
    cfg_start = cfg.get("kline_start_date")
    fetch_start = datetime.strptime(cfg_start, "%Y-%m-%d") if cfg_start else curr_dt - relativedelta(years=1)

    params = KlineParams(
        symbol=symbol.upper(),
        interval=resolved_interval,
        start_time=_date_to_ms(fetch_start.strftime("%Y-%m-%d")),
        end_time=_date_to_ms(curr_date),
        limit=200,
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
    limit: Annotated[int, "Number of price levels to return (max 200)"] = 100,
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


# ---------------------------------------------------------------------------
# Public API — Fibonacci retracement
# ---------------------------------------------------------------------------

_FIB_LEVELS = [0.0, 0.236, 0.382, 0.5, 0.618, 1.0]


def get_fibonacci_retracement(
    symbol: Annotated[str, "Binance trading pair, e.g. BTCUSDT"],
    start_date: Annotated[str, "Start date in YYYY-MM-DD format"],
    end_date: Annotated[str, "End date in YYYY-MM-DD format"],
    interval: KlineInterval | None = None,
) -> str:
    """Calculate Fibonacci retracement levels from Binance kline data.

    Finds the highest high and lowest low over the date range, then computes
    retracement levels at 0, 0.236, 0.382, 0.5, 0.618, and 1.0.

    Returns a formatted report including the price levels, the last closing
    price, and which zone it currently occupies.
    """
    from datetime import timedelta as _timedelta

    cfg = get_config()
    _today = datetime.now().strftime("%Y-%m-%d")
    _two_months_ago = (datetime.now() - _timedelta(days=60)).strftime("%Y-%m-%d")

    cfg_start = cfg.get("kline_start_date")
    cfg_end = cfg.get("kline_end_date")
    start_date = cfg_start or start_date or _two_months_ago
    end_date = cfg_end or end_date or _today

    resolved_interval = _resolve_kline_interval(interval)

    params = KlineParams(
        symbol=symbol.upper(),
        interval=resolved_interval,
        start_time=_date_to_ms(start_date),
        end_time=_date_to_ms(end_date),
        limit=200,
    )
    klines = _fetch_klines_range(params)
    if not klines:
        return f"No kline data available for '{symbol}' between {start_date} and {end_date}"

    swing_high = max(k.high for k in klines)
    swing_low = min(k.low for k in klines)
    last_close = klines[-1].close
    diff = swing_high - swing_low

    levels: dict[float, float] = {
        lvl: round(swing_high - diff * lvl, 8) for lvl in _FIB_LEVELS
    }

    # Determine which Fibonacci zone the current price occupies
    sorted_prices = sorted(levels.values(), reverse=True)
    zone = "below all levels"
    for i in range(len(sorted_prices) - 1):
        upper = sorted_prices[i]
        lower = sorted_prices[i + 1]
        if lower <= last_close <= upper:
            upper_lvl = [k for k, v in levels.items() if v == upper][0]
            lower_lvl = [k for k, v in levels.items() if v == lower][0]
            zone = f"between {lower_lvl} ({lower:.2f}) and {upper_lvl} ({upper:.2f})"
            break

    header = (
        f"# Fibonacci Retracement for {symbol.upper()}\n"
        f"# Period: {start_date} to {end_date}  |  Interval: {resolved_interval.value}\n"
        f"# Swing High: {swing_high:.2f}  |  Swing Low: {swing_low:.2f}\n"
        f"# Last Close: {last_close:.2f}  |  Zone: {zone}\n\n"
    )

    rows = ["Level  | Price"]
    rows.append("-------|----------")
    for lvl in _FIB_LEVELS:
        rows.append(f"{lvl:<6} | {levels[lvl]:.2f}")

    # Trend signal based on symbol type
    mid_level = levels[0.5]
    golden_level = levels[0.618]
    sym = symbol.upper()
    rows.append("")
    if sym == "BTCUSDT":
        signal = "SHORT UPTREND" if last_close > mid_level else "DOWNTREND / CONSOLIDATION"
        rows.append(
            f"## BTC Signal (0.5 rule): price {'above' if last_close > mid_level else 'below'} "
            f"0.5 level ({mid_level:.2f}) → {signal}"
        )
    else:
        signal = "SHORT UPTREND" if last_close > golden_level else "DOWNTREND / CONSOLIDATION"
        rows.append(
            f"## Altcoin Signal (0.618 rule): price {'above' if last_close > golden_level else 'below'} "
            f"0.618 level ({golden_level:.2f}) → {signal}"
        )

    return header + "\n".join(rows)
