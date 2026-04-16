import time
import logging

import pandas as pd
import yfinance as yf
import requests
from yfinance.exceptions import YFRateLimitError
from stockstats import wrap
from typing import Annotated
import os
from .config import get_config

logger = logging.getLogger(__name__)


def _symbol_to_tencent_code(symbol: str) -> str:
    code, exchange = symbol.upper().split(".")
    if exchange == "SS":
        return f"sh{code}"
    if exchange == "SZ":
        return f"sz{code}"
    raise ValueError(f"Unsupported A-share symbol for Tencent fallback: {symbol}")


def _fetch_tencent_ohlcv(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    """Fallback daily OHLCV fetch for A-shares via Tencent."""
    session = requests.Session()
    session.trust_env = False
    response = session.get(
        "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get",
        params={
            "param": f"{_symbol_to_tencent_code(symbol)},day,{start_date},{end_date},320,qfq"
        },
        headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://gu.qq.com/",
        },
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    data = ((payload or {}).get("data") or {}).get(_symbol_to_tencent_code(symbol)) or {}
    rows = data.get("qfqday") or data.get("day") or []
    if not rows:
        raise ValueError(f"No Tencent OHLCV data returned for {symbol}")

    parsed = []
    for line in rows:
        # [date, open, close, high, low, volume]
        date_str, open_p, close_p, high_p, low_p, volume = line[:6]
        parsed.append(
            {
                "Date": date_str,
                "Open": float(open_p),
                "High": float(high_p),
                "Low": float(low_p),
                "Close": float(close_p),
                "Volume": float(volume),
            }
        )
    return pd.DataFrame(parsed)


def _symbol_to_eastmoney_secid(symbol: str) -> str:
    code, exchange = symbol.upper().split(".")
    if exchange == "SS":
        return f"1.{code}"
    if exchange in {"SZ", "BJ"}:
        return f"0.{code}"
    raise ValueError(f"Unsupported A-share symbol for Eastmoney fallback: {symbol}")


def _fetch_eastmoney_ohlcv(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    """Fallback daily OHLCV fetch for A-shares via Eastmoney."""
    session = requests.Session()
    session.trust_env = False
    url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
    response = session.get(
        url,
        params={
            "secid": _symbol_to_eastmoney_secid(symbol),
            "fields1": "f1,f2,f3,f4,f5,f6",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
            "klt": "101",
            "fqt": "1",
            "beg": start_date.replace("-", ""),
            "end": end_date.replace("-", ""),
            "ut": "fa5fd1943c7b386f172d6893dbfba10b",
        },
        headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://quote.eastmoney.com/",
        },
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    klines = ((payload or {}).get("data") or {}).get("klines") or []
    if not klines:
        raise ValueError(f"No Eastmoney OHLCV data returned for {symbol}")

    rows = []
    for line in klines:
        date_str, open_p, close_p, high_p, low_p, volume, amount, *_rest = line.split(",")
        rows.append(
            {
                "Date": date_str,
                "Open": float(open_p),
                "High": float(high_p),
                "Low": float(low_p),
                "Close": float(close_p),
                "Volume": float(volume),
                "Amount": float(amount),
            }
        )
    return pd.DataFrame(rows)


def _is_transient_yfinance_error(exc: Exception) -> bool:
    """Heuristic for flaky yfinance transport/parser failures."""
    if isinstance(exc, YFRateLimitError):
        return True
    message = str(exc)
    return isinstance(exc, TypeError) and "'NoneType' object is not subscriptable" in message


def yf_retry(func, max_retries=3, base_delay=2.0):
    """Execute a yfinance call with exponential backoff on rate limits.

    yfinance raises YFRateLimitError on HTTP 429 responses but does not
    retry them internally. This wrapper adds retry logic specifically
    for rate limits and observed transient parser failures. Other
    exceptions propagate immediately.
    """
    for attempt in range(max_retries + 1):
        try:
            return func()
        except Exception as exc:
            if not _is_transient_yfinance_error(exc):
                raise
            if attempt < max_retries:
                delay = base_delay * (2 ** attempt)
                logger.warning(
                    "Yahoo Finance transient failure (%s), retrying in %.0fs (attempt %s/%s)",
                    exc,
                    delay,
                    attempt + 1,
                    max_retries,
                )
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


def load_ohlcv(symbol: str, curr_date: str) -> pd.DataFrame:
    """Fetch OHLCV data with caching, filtered to prevent look-ahead bias.

    Downloads 15 years of data up to today and caches per symbol. On
    subsequent calls the cache is reused. Rows after curr_date are
    filtered out so backtests never see future prices.
    """
    config = get_config()
    curr_date_dt = pd.to_datetime(curr_date)
    min_acceptable_date = curr_date_dt - pd.Timedelta(days=1)

    # Cache uses a fixed window (15y to today) so one file per symbol
    today_date = pd.Timestamp.today()
    start_date = today_date - pd.DateOffset(years=5)
    start_str = start_date.strftime("%Y-%m-%d")
    end_str = today_date.strftime("%Y-%m-%d")

    os.makedirs(config["data_cache_dir"], exist_ok=True)
    data_file = os.path.join(
        config["data_cache_dir"],
        f"{symbol}-YFin-data-{start_str}-{end_str}.csv",
    )

    need_refresh = True
    data = None
    if os.path.exists(data_file):
        cached = pd.read_csv(data_file, on_bad_lines="skip")
        if "Date" in cached.columns:
            parsed_dates = pd.to_datetime(cached["Date"], errors="coerce")
            latest_cached = parsed_dates.dropna().max()
            if (
                latest_cached is not pd.NaT
                and latest_cached is not None
                and latest_cached >= min_acceptable_date
            ):
                data = cached
                need_refresh = False

    if need_refresh:
        try:
            data = yf_retry(lambda: yf.download(
                symbol,
                start=start_str,
                end=end_str,
                multi_level_index=False,
                progress=False,
                auto_adjust=True,
            ))
            data = data.reset_index()
            latest_downloaded = pd.to_datetime(data.get("Date"), errors="coerce").dropna().max()
            if latest_downloaded is pd.NaT or latest_downloaded is None or latest_downloaded < min_acceptable_date:
                raise ValueError(
                    f"yfinance returned stale data for {symbol}: latest={latest_downloaded}"
                )
        except Exception as exc:
            logger.warning(
                "yfinance download failed for %s, falling back to Tencent/Eastmoney OHLCV: %s",
                symbol,
                exc,
            )
            try:
                data = _fetch_tencent_ohlcv(symbol, start_str, end_str)
            except Exception:
                data = _fetch_eastmoney_ohlcv(symbol, start_str, end_str)
        data.to_csv(data_file, index=False)

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
