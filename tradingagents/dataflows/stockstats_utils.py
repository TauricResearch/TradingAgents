import time
import logging

import pandas as pd
import yfinance as yf
from yfinance.exceptions import YFRateLimitError
from stockstats import wrap
from typing import Annotated
import os
from .config import get_config

logger = logging.getLogger(__name__)


def yf_retry(func, max_retries=3, base_delay=2.0):
    """Execute a yfinance call with exponential backoff on rate limits.

    yfinance raises YFRateLimitError on HTTP 429 responses but does not
    retry them internally. This wrapper adds retry logic specifically
    for rate limits. Other exceptions propagate immediately.
    """
    for attempt in range(max_retries + 1):
        try:
            return func()
        except YFRateLimitError:
            if attempt < max_retries:
                delay = base_delay * (2 ** attempt)
                logger.warning(f"Yahoo Finance rate limited, retrying in {delay:.0f}s (attempt {attempt + 1}/{max_retries})")
                time.sleep(delay)
            else:
                raise


def _clean_dataframe(data: pd.DataFrame) -> pd.DataFrame:
    """Normalize a stock DataFrame for stockstats: parse dates, drop invalid rows, fill price gaps."""
    data["Date"] = pd.to_datetime(data["Date"], errors="coerce")
    data = data.dropna(subset=["Date"])

    price_cols = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in data.columns]
    data[price_cols] = data[price_cols].apply(pd.to_numeric, errors="coerce")
    data = data.dropna(subset=["Close"])
    data[price_cols] = data[price_cols].ffill().bfill()

    return data


def _load_ohlcv_polygon(symbol: str, curr_date_dt: pd.Timestamp) -> pd.DataFrame:
    """Fetch OHLCV bars from Polygon for the cached historical window.

    Returns a DataFrame in the same shape as yfinance: ``Date, Open, High,
    Low, Close, Volume`` columns. Bars are split-adjusted; bars on or after
    ``curr_date_dt`` are filtered by the caller.
    """
    from .polygon_common import _make_request, PolygonError

    today_date = pd.Timestamp.today()
    start_date = today_date - pd.DateOffset(years=5)
    start_str = start_date.strftime("%Y-%m-%d")
    end_str = today_date.strftime("%Y-%m-%d")

    payload = _make_request(
        f"/v2/aggs/ticker/{symbol.upper()}/range/1/day/{start_str}/{end_str}",
        {"adjusted": "true", "sort": "asc", "limit": 50000},
    )
    bars = payload.get("results") or []

    rows = []
    for bar in bars:
        ts = bar.get("t")
        if ts is None:
            continue
        rows.append({
            "Date": pd.Timestamp(ts, unit="ms"),
            "Open": bar.get("o"),
            "High": bar.get("h"),
            "Low": bar.get("l"),
            "Close": bar.get("c"),
            "Volume": bar.get("v"),
        })
    return pd.DataFrame(rows)


def load_ohlcv(symbol: str, curr_date: str) -> pd.DataFrame:
    """Fetch OHLCV data with caching, filtered to prevent look-ahead bias.

    Dispatches on the configured ``core_stock_apis`` vendor: ``polygon`` uses
    Polygon's split-adjusted aggregates endpoint, ``yfinance`` uses
    ``yf.download``. Both paths cache to disk per ``(symbol, vendor)`` and
    filter rows after ``curr_date`` so backtests never see future prices.
    """
    config = get_config()
    curr_date_dt = pd.to_datetime(curr_date)

    # Determine vendor for bars. Tool-level override takes precedence, then
    # the core_stock_apis category.
    vendor = (
        config.get("tool_vendors", {}).get("get_stock_data")
        or config.get("data_vendors", {}).get("core_stock_apis", "yfinance")
    )
    primary_vendor = vendor.split(",")[0].strip() if isinstance(vendor, str) else "yfinance"

    today_date = pd.Timestamp.today()
    start_date = today_date - pd.DateOffset(years=5)
    start_str = start_date.strftime("%Y-%m-%d")
    end_str = today_date.strftime("%Y-%m-%d")

    os.makedirs(config["data_cache_dir"], exist_ok=True)
    # Cache key includes vendor so switching providers doesn't return stale
    # files written by the other one.
    cache_tag = "Polygon" if primary_vendor == "polygon" else "YFin"
    data_file = os.path.join(
        config["data_cache_dir"],
        f"{symbol}-{cache_tag}-data-{start_str}-{end_str}.csv",
    )

    if os.path.exists(data_file):
        data = pd.read_csv(data_file, on_bad_lines="skip", encoding="utf-8")
    else:
        if primary_vendor == "polygon":
            try:
                data = _load_ohlcv_polygon(symbol, curr_date_dt)
            except Exception as exc:
                logger.warning(
                    f"Polygon bar fetch failed for {symbol} ({exc}); falling back to yfinance"
                )
                data = yf_retry(lambda: yf.download(
                    symbol,
                    start=start_str,
                    end=end_str,
                    multi_level_index=False,
                    progress=False,
                    auto_adjust=True,
                ))
                data = data.reset_index()
        else:
            data = yf_retry(lambda: yf.download(
                symbol,
                start=start_str,
                end=end_str,
                multi_level_index=False,
                progress=False,
                auto_adjust=True,
            ))
            data = data.reset_index()
        data.to_csv(data_file, index=False, encoding="utf-8")

    data = _clean_dataframe(data)

    # Filter to curr_date to prevent look-ahead bias in backtesting
    data = data[data["Date"] <= curr_date_dt]

    return data


def filter_financials_by_date(data: pd.DataFrame, curr_date: str) -> pd.DataFrame:
    """Drop financial statement columns (fiscal period timestamps) after curr_date.

    yfinance financial statements use fiscal period end dates as columns.
    Columns after curr_date represent future data and are removed to
    prevent look-ahead bias.
    """
    if not curr_date or data.empty:
        return data
    cutoff = pd.Timestamp(curr_date)
    mask = pd.to_datetime(data.columns, errors="coerce") <= cutoff
    return data.loc[:, mask]


class StockstatsUtils:
    @staticmethod
    def get_stock_stats(
        symbol: Annotated[str, "ticker symbol for the company"],
        indicator: Annotated[
            str, "quantitative indicators based off of the stock data for the company"
        ],
        curr_date: Annotated[
            str, "curr date for retrieving stock price data, YYYY-mm-dd"
        ],
    ):
        data = load_ohlcv(symbol, curr_date)
        df = wrap(data)
        df["Date"] = df["Date"].dt.strftime("%Y-%m-%d")
        curr_date_str = pd.to_datetime(curr_date).strftime("%Y-%m-%d")

        df[indicator]  # trigger stockstats to calculate the indicator
        matching_rows = df[df["Date"].str.startswith(curr_date_str)]

        if not matching_rows.empty:
            indicator_value = matching_rows[indicator].values[0]
            return indicator_value
        else:
            return "N/A: Not a trading day (weekend or holiday)"
