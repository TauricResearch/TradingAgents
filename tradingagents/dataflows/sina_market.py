"""Sina Finance market-data vendor for A-share instruments.

Provides the two core market-data tools the pipeline needs:

  - ``get_stock_data``: daily OHLCV from Sina's public kline API
  - ``get_indicators``: technical indicators computed from the same Sina OHLCV

Non-A-share symbols raise :class:`NoMarketDataError` so the vendor router can
fall back to the next configured vendor (e.g. yfinance).
"""

from __future__ import annotations

import functools
import logging
import re
from datetime import datetime

import pandas as pd
import requests
from stockstats import wrap

from .errors import NoMarketDataError

logger = logging.getLogger(__name__)

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "Chrome/124 Safari/537.36"
)
_KLINE_URL = (
    "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/"
    "CN_MarketData.getKLineData"
)
_EM_KLINE_URL = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
_TX_KLINE_URL = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"

BEST_IND_PARAMS = {
    "close_50_sma": (
        "50 SMA: A medium-term trend indicator. "
        "Usage: Identify trend direction and serve as dynamic support/resistance. "
        "Tips: It lags price; combine with faster indicators for timely signals."
    ),
    "close_200_sma": (
        "200 SMA: A long-term trend benchmark. "
        "Usage: Confirm overall market trend and identify golden/death cross setups. "
        "Tips: It reacts slowly; best for strategic trend confirmation rather than frequent trading entries."
    ),
    "close_10_ema": (
        "10 EMA: A responsive short-term average. "
        "Usage: Capture quick shifts in momentum and potential entry points. "
        "Tips: Prone to noise in choppy markets; use alongside longer averages for filtering false signals."
    ),
    "macd": (
        "MACD: Computes momentum via differences of EMAs. "
        "Usage: Look for crossovers and divergence as signals of trend changes. "
        "Tips: Confirm with other indicators in low-volatility or sideways markets."
    ),
    "macds": (
        "MACD Signal: An EMA smoothing of the MACD line. "
        "Usage: Use crossovers with the MACD line to trigger trades. "
        "Tips: Should be part of a broader strategy to avoid false positives."
    ),
    "macdh": (
        "MACD Histogram: Shows the gap between the MACD line and its signal. "
        "Usage: Visualize momentum strength and spot divergence early. "
        "Tips: Can be volatile; complement with additional filters in fast-moving markets."
    ),
    "rsi": (
        "RSI: Measures momentum to flag overbought/oversold conditions. "
        "Usage: Apply 70/30 thresholds and watch for divergence to signal reversals. "
        "Tips: In strong trends, RSI may remain extreme; always cross-check with trend analysis."
    ),
    "boll": (
        "Bollinger Middle: A 20 SMA serving as the basis for Bollinger Bands. "
        "Usage: Acts as a dynamic benchmark for price movement. "
        "Tips: Combine with the upper and lower bands to effectively spot breakouts or reversals."
    ),
    "boll_ub": (
        "Bollinger Upper Band: Typically 2 standard deviations above the middle line. "
        "Usage: Signals potential overbought conditions and breakout zones. "
        "Tips: Confirm signals with other tools; prices may ride the band in strong trends."
    ),
    "boll_lb": (
        "Bollinger Lower Band: Typically 2 standard deviations below the middle line. "
        "Usage: Indicates potential oversold conditions. "
        "Tips: Use additional analysis to avoid false reversal signals."
    ),
    "atr": (
        "ATR: Averages true range to measure volatility. "
        "Usage: Set stop-loss levels and adjust position sizes based on current market volatility. "
        "Tips: It's a reactive measure, so use it as part of a broader risk management strategy."
    ),
    "vwma": (
        "VWMA: A moving average weighted by volume. "
        "Usage: Confirm trends by integrating price action with volume data. "
        "Tips: Watch for skewed results from volume spikes; use in combination with other volume analyses."
    ),
    "mfi": (
        "MFI: The Money Flow Index is a momentum indicator that uses both price and volume to measure buying and selling pressure. "
        "Usage: Identify overbought (>80) or oversold (<20) conditions and confirm the strength of trends or reversals. "
        "Tips: Use alongside RSI or MACD to confirm signals; divergence between price and MFI can indicate potential reversals."
    ),
}


def _sina_symbol(ticker: str) -> str | None:
    """Map an A-share ticker to Sina's ``sh600036`` / ``sz000021`` form."""
    match = re.search(r"(\d{6})", ticker)
    if not match:
        return None
    code = match.group(1)
    upper = ticker.upper()
    if upper.endswith(".SS") or upper.endswith(".SH"):
        prefix = "sh"
    elif upper.endswith(".SZ"):
        prefix = "sz"
    else:
        prefix = "sh" if code.startswith(("5", "6", "9")) else "sz"
    return f"{prefix}{code}"


def fetch_sina_kline(sina_symbol: str, datalen: int = 1023) -> pd.DataFrame:
    """Fetch daily OHLCV from Sina using a raw ``sh600036`` / ``sz000021`` symbol."""
    try:
        resp = requests.get(
            _KLINE_URL,
            params={
                "symbol": sina_symbol,
                "scale": 240,
                "ma": "no",
                "datalen": datalen,
            },
            headers={"User-Agent": _UA, "Referer": "https://finance.sina.com.cn"},
            timeout=15,
        )
        resp.raise_for_status()
        payload = resp.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning("Sina kline fetch failed for %s: %s", sina_symbol, exc)
        raise NoMarketDataError(
            sina_symbol, sina_symbol, f"Sina kline unavailable: {type(exc).__name__}"
        ) from exc

    if not isinstance(payload, list) or not payload:
        raise NoMarketDataError(sina_symbol, sina_symbol, "Sina returned no kline rows")

    frame = pd.DataFrame(payload)
    frame = frame.rename(
        columns={
            "day": "Date",
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "volume": "Volume",
        }
    )
    for col in ("Open", "High", "Low", "Close", "Volume"):
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    frame["Date"] = pd.to_datetime(frame["Date"], errors="coerce")
    frame["Dividends"] = 0.0
    frame["Stock Splits"] = 0.0
    frame = frame.dropna(subset=["Date", "Close"]).sort_values("Date")
    return frame[["Date", "Open", "High", "Low", "Close", "Volume", "Dividends", "Stock Splits"]]


def _fetch_eastmoney_kline(ticker: str, datalen: int = 1023) -> pd.DataFrame:
    """Fetch daily OHLCV from Eastmoney as a fallback source."""
    sina_symbol = _sina_symbol(ticker)
    if not sina_symbol:
        raise NoMarketDataError(ticker, ticker, "Eastmoney kline supports A-shares only")
    market = "1" if sina_symbol.startswith("sh") else "0"
    code = sina_symbol[2:]
    beg = (pd.Timestamp.today() - pd.Timedelta(days=datalen * 2)).strftime("%Y%m%d")
    try:
        resp = requests.get(
            _EM_KLINE_URL,
            params={
                "secid": f"{market}.{code}",
                "fields1": "f1,f2,f3,f4,f5,f6",
                "fields2": "f51,f52,f53,f54,f55,f56,f57,f58",
                "klt": "101",
                "fqt": "1",
                "beg": beg,
                "end": "20500101",
            },
            headers={"User-Agent": _UA, "Referer": "https://quote.eastmoney.com/"},
            timeout=15,
        )
        resp.raise_for_status()
        payload = resp.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning("Eastmoney kline fetch failed for %s: %s", ticker, exc)
        raise NoMarketDataError(ticker, ticker, "Eastmoney kline unavailable") from exc

    klines = ((payload.get("data") or {}).get("klines")) or []
    if not klines:
        raise NoMarketDataError(ticker, ticker, "Eastmoney returned no kline rows")

    rows = []
    for line in klines[-datalen:]:
        parts = line.split(",")
        if len(parts) < 6:
            continue
        rows.append(
            {
                "Date": pd.to_datetime(parts[0]),
                "Open": float(parts[1]),
                "Close": float(parts[2]),
                "High": float(parts[3]),
                "Low": float(parts[4]),
                "Volume": float(parts[5]) * 100,
            }
        )
    frame = pd.DataFrame(rows)
    if frame.empty:
        raise NoMarketDataError(ticker, ticker, "Eastmoney returned no usable rows")
    frame["Dividends"] = 0.0
    frame["Stock Splits"] = 0.0
    return frame[["Date", "Open", "High", "Low", "Close", "Volume", "Dividends", "Stock Splits"]]


def _fetch_tencent_kline(ticker: str, datalen: int = 1023) -> pd.DataFrame:
    """Fetch daily OHLCV from Tencent as the final domestic fallback."""
    sina_symbol = _sina_symbol(ticker)
    if not sina_symbol:
        raise NoMarketDataError(ticker, ticker, "Tencent kline supports A-shares only")
    count = min(datalen, 800)
    try:
        resp = requests.get(
            _TX_KLINE_URL,
            params={"param": f"{sina_symbol},day,2000-01-01,2050-01-01,{count},qfq"},
            headers={"User-Agent": _UA, "Referer": "https://gu.qq.com/"},
            timeout=15,
        )
        resp.raise_for_status()
        payload = resp.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning("Tencent kline fetch failed for %s: %s", ticker, exc)
        raise NoMarketDataError(ticker, ticker, "Tencent kline unavailable") from exc

    node = ((payload.get("data") or {}).get(sina_symbol)) or {}
    klines = node.get("qfqday") or node.get("day") or []
    if not klines:
        raise NoMarketDataError(ticker, ticker, "Tencent returned no kline rows")

    rows = []
    for item in klines[-datalen:]:
        if len(item) < 6:
            continue
        rows.append(
            {
                "Date": pd.to_datetime(item[0]),
                "Open": float(item[1]),
                "Close": float(item[2]),
                "High": float(item[3]),
                "Low": float(item[4]),
                "Volume": float(item[5]) * 100,
            }
        )
    frame = pd.DataFrame(rows)
    if frame.empty:
        raise NoMarketDataError(ticker, ticker, "Tencent returned no usable rows")
    frame["Dividends"] = 0.0
    frame["Stock Splits"] = 0.0
    return frame[["Date", "Open", "High", "Low", "Close", "Volume", "Dividends", "Stock Splits"]]


@functools.lru_cache(maxsize=256)
def _fetch_kline(symbol: str, datalen: int = 1023) -> pd.DataFrame:
    """Fetch daily OHLCV for an A-share ticker with domestic multi-source fallback.

    Cached per process: get_stock_data, every get_indicators call, and the
    verified-market-snapshot path all need the same 1023-row kline, and each
    previously triggered a separate network fetch. Callers only filter/slice
    the returned frame, so sharing one immutable-by-convention frame is safe.
    """
    sina_symbol = _sina_symbol(symbol)
    if not sina_symbol:
        raise NoMarketDataError(symbol, symbol, "Sina vendor supports A-shares only")
    errors = []
    for fetcher in (
        lambda: fetch_sina_kline(sina_symbol, datalen=datalen),
        lambda: _fetch_eastmoney_kline(symbol, datalen=datalen),
        lambda: _fetch_tencent_kline(symbol, datalen=datalen),
    ):
        try:
            return fetcher()
        except NoMarketDataError as exc:
            errors.append(str(exc))
            continue
    raise NoMarketDataError(
        symbol,
        symbol,
        "all domestic kline sources failed: " + " | ".join(errors),
    )


def load_sina_ohlcv(symbol: str, curr_date: str, datalen: int = 1023) -> pd.DataFrame:
    """Sina OHLCV on or before ``curr_date``, sorted ascending."""
    frame = _fetch_kline(symbol, datalen=datalen)
    frame = frame[frame["Date"] <= pd.to_datetime(curr_date)]
    if frame.empty:
        raise NoMarketDataError(symbol, symbol, f"No Sina rows on or before {curr_date}")
    return frame


def get_stock_data(symbol: str, start_date: str, end_date: str) -> str:
    """Return daily OHLCV for an A-share in the same CSV format as yfinance."""
    datetime.strptime(start_date, "%Y-%m-%d")
    datetime.strptime(end_date, "%Y-%m-%d")

    frame = _fetch_kline(symbol, datalen=1023)
    start = pd.to_datetime(start_date)
    end = pd.to_datetime(end_date)
    frame = frame[(frame["Date"] >= start) & (frame["Date"] <= end)]
    if frame.empty:
        raise NoMarketDataError(
            symbol,
            symbol,
            f"no Sina rows between {start_date} and {end_date}",
        )

    for col in ("Open", "High", "Low", "Close"):
        frame[col] = frame[col].round(2)

    header = f"# Stock data for {symbol.upper()} from {start_date} to {end_date}\n"
    header += f"# Total records: {len(frame)}\n"
    header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    return header + frame.to_csv(index=False)


def _indicator_series(symbol: str, indicator: str, curr_date: str) -> dict[str, str]:
    """Compute an indicator for every available day up to ``curr_date``."""
    frame = _fetch_kline(symbol, datalen=1023)
    frame = frame[frame["Date"] <= pd.to_datetime(curr_date)]
    if frame.empty:
        raise NoMarketDataError(symbol, symbol, f"No Sina rows on or before {curr_date}")

    stock_df = wrap(frame)
    stock_df["Date"] = stock_df["Date"].dt.strftime("%Y-%m-%d")
    stock_df[indicator]  # stockstats lazy-computes on access

    result: dict[str, str] = {}
    for _, row in stock_df.iterrows():
        value = row[indicator]
        result[row["Date"]] = "N/A" if pd.isna(value) else str(value)
    return result


def get_indicators(
    symbol: str,
    indicator: str,
    curr_date: str,
    look_back_days: int,
) -> str:
    """Return a date-stamped indicator series, mirroring the yfinance format."""
    if indicator not in BEST_IND_PARAMS:
        raise ValueError(
            f"Indicator {indicator} is not supported. Please choose from: "
            f"{list(BEST_IND_PARAMS.keys())}"
        )

    curr_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    before = curr_dt - pd.Timedelta(days=look_back_days)
    series = _indicator_series(symbol, indicator, curr_date)

    lines = []
    current = curr_dt
    while current >= before:
        date_str = current.strftime("%Y-%m-%d")
        value = series.get(date_str, "N/A: Not a trading day (weekend or holiday)")
        lines.append(f"{date_str}: {value}")
        current = current - pd.Timedelta(days=1)

    return (
        f"## {indicator} values from {before.strftime('%Y-%m-%d')} to {curr_date}:\n\n"
        + "\n".join(lines)
        + "\n\n"
        + BEST_IND_PARAMS[indicator]
    )
