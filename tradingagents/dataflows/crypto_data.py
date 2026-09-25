"""Crypto market data provider backed by Binance through ccxt."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

import pandas as pd
from stockstats import wrap

from tradingagents.dataflows.config import get_config

logger = logging.getLogger(__name__)

_SUPPORTED_INDICATORS = {
    "close_50_sma",
    "close_200_sma",
    "close_10_ema",
    "macd",
    "macds",
    "macdh",
    "rsi",
    "boll",
    "boll_ub",
    "boll_lb",
    "atr",
    "vwma",
}


def _load_ccxt():
    try:
        import ccxt  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "ccxt is required for crypto data. Install the project again or run `pip install ccxt`."
        ) from exc
    return ccxt


def _exchange():
    cfg = get_config()
    ccxt = _load_ccxt()
    exchange_id = cfg.get("crypto_exchange", "binance")
    exchange_cls = getattr(ccxt, exchange_id)
    return exchange_cls(
        {
            "enableRateLimit": True,
            "options": {"defaultType": cfg.get("crypto_market_type", "spot")},
        }
    )


def _parse_since(value: Optional[str]) -> Optional[int]:
    if not value:
        return None
    dt = pd.to_datetime(value, utc=True, errors="coerce")
    if pd.isna(dt):
        return None
    return int(dt.timestamp() * 1000)


def _fetch_ohlcv(symbol: str, since: Optional[str] = None, limit: Optional[int] = None, timeframe: Optional[str] = None) -> pd.DataFrame:
    cfg = get_config()
    timeframe = timeframe or cfg.get("crypto_timeframe", "15m")
    limit = int(limit or cfg.get("crypto_ohlcv_limit", 240))
    exchange = _exchange()
    rows = exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=_parse_since(since), limit=limit)
    if not rows:
        return pd.DataFrame(columns=["Date", "Open", "High", "Low", "Close", "Volume"])

    df = pd.DataFrame(rows, columns=["timestamp", "Open", "High", "Low", "Close", "Volume"])
    df["Date"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df = df.drop(columns=["timestamp"])
    return df[["Date", "Open", "High", "Low", "Close", "Volume"]]


def get_crypto_ohlcv(symbol: str, start_date: str, end_date: str, timeframe: Optional[str] = None) -> str:
    """Return compact Binance OHLCV data for a crypto pair."""
    try:
        cfg = get_config()
        active_timeframe = timeframe or cfg.get("crypto_timeframe", "15m")
        df = _fetch_ohlcv(symbol, since=start_date, timeframe=active_timeframe)
        end_ts = pd.to_datetime(end_date, utc=True, errors="coerce")
        if not pd.isna(end_ts):
            df = df[df["Date"] <= end_ts]
        if df.empty:
            return f"No Binance OHLCV data returned for {symbol}."

        rows = int(cfg.get("crypto_report_rows", 80))
        display = df.tail(rows).copy()
        display["Date"] = display["Date"].dt.strftime("%Y-%m-%d %H:%M UTC")
        display[["Open", "High", "Low", "Close", "Volume"]] = display[
            ["Open", "High", "Low", "Close", "Volume"]
        ].round(6)
        generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        return (
            f"Binance {symbol} OHLCV ({active_timeframe}), latest {len(display)} candles, "
            f"generated {generated}:\n"
            + display.to_string(index=False)
        )
    except Exception as exc:  # keep tool failure observable to the agent
        logger.warning("Crypto OHLCV fetch failed for %s: %s", symbol, exc)
        return f"Crypto OHLCV fetch failed for {symbol}: {exc}"


def get_crypto_indicator(
    symbol: str,
    indicator: str,
    curr_date: str,
    look_back_days: int = 30,
    timeframe: Optional[str] = None,
) -> str:
    """Return a compact technical indicator series for Binance crypto data."""
    indicator = indicator.strip().lower()
    if indicator not in _SUPPORTED_INDICATORS:
        return f"Unsupported crypto indicator: {indicator}. Supported: {', '.join(sorted(_SUPPORTED_INDICATORS))}"

    try:
        cfg = get_config()
        active_timeframe = timeframe or cfg.get("crypto_timeframe", "15m")
        # For intraday crypto, a fixed candle limit is safer than date-only backtests.
        limit = max(int(cfg.get("crypto_ohlcv_limit", 240)), int(look_back_days) * 24)
        df = _fetch_ohlcv(symbol, limit=limit, timeframe=active_timeframe)
        if df.empty:
            return f"No Binance OHLCV data returned for {symbol}; cannot compute {indicator}."

        stock_df = df.rename(
            columns={"Date": "date", "Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"}
        )
        stats = wrap(stock_df)
        stats[indicator]
        out = pd.DataFrame(
            {
                "date": stock_df["date"].values,
                "close": pd.to_numeric(stats["close"], errors="coerce"),
                indicator: pd.to_numeric(stats[indicator], errors="coerce"),
            }
        ).tail(int(cfg.get("crypto_indicator_rows", 40))).copy()
        out["date"] = pd.to_datetime(out["date"], utc=True).dt.strftime("%Y-%m-%d %H:%M UTC")
        out["close"] = out["close"].round(6)
        out[indicator] = out[indicator].round(6)
        return f"Binance {symbol} {indicator} ({active_timeframe}):\n" + out.to_string(index=False)
    except Exception as exc:
        logger.warning("Crypto indicator fetch failed for %s %s: %s", symbol, indicator, exc)
        return f"Crypto indicator fetch failed for {symbol} {indicator}: {exc}"
