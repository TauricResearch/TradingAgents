"""Alpaca Market Data API client for the equity ranking engine.

Provides price bars, snapshots, and news. Fundamentals still come from yfinance.
Free tier: 10,000 requests/min, up to 7 years of historical data.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Client setup (lazy init)
# ---------------------------------------------------------------------------

_stock_client = None
_news_client = None


def _get_stock_client():
    global _stock_client
    if _stock_client is None:
        from alpaca.data.historical import StockHistoricalDataClient

        key = os.environ.get("ALPACA_API_KEY", "")
        secret = os.environ.get("ALPACA_API_SECRET", "")
        if not key or not secret:
            raise RuntimeError(
                "ALPACA_API_KEY and ALPACA_API_SECRET must be set"
            )
        _stock_client = StockHistoricalDataClient(key, secret)
    return _stock_client


def _get_news_client():
    global _news_client
    if _news_client is None:
        from alpaca.data.historical.news import NewsClient

        key = os.environ.get("ALPACA_API_KEY", "")
        secret = os.environ.get("ALPACA_API_SECRET", "")
        _news_client = NewsClient(key, secret)
    return _news_client


def alpaca_available() -> bool:
    """Check if Alpaca credentials are configured."""
    return bool(
        os.environ.get("ALPACA_API_KEY")
        and os.environ.get("ALPACA_API_SECRET")
    )


# ---------------------------------------------------------------------------
# Price / Bar data
# ---------------------------------------------------------------------------

def get_bars(
    symbol: str,
    start_date: str,
    end_date: str,
    timeframe: str = "1Day",
) -> pd.DataFrame:
    """Fetch historical bars from Alpaca.

    Args:
        symbol: Ticker symbol (e.g., "AAPL")
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format
        timeframe: "1Min", "5Min", "15Min", "1Hour", "1Day", "1Week", "1Month"

    Returns:
        DataFrame with OHLCV columns.
    """
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

    tf_map = {
        "1Min": TimeFrame(1, TimeFrameUnit.Minute),
        "5Min": TimeFrame(5, TimeFrameUnit.Minute),
        "15Min": TimeFrame(15, TimeFrameUnit.Minute),
        "1Hour": TimeFrame(1, TimeFrameUnit.Hour),
        "1Day": TimeFrame(1, TimeFrameUnit.Day),
        "1Week": TimeFrame(1, TimeFrameUnit.Week),
        "1Month": TimeFrame(1, TimeFrameUnit.Month),
    }
    tf = tf_map.get(timeframe, TimeFrame(1, TimeFrameUnit.Day))

    client = _get_stock_client()
    request = StockBarsRequest(
        symbol_or_symbols=symbol.upper(),
        timeframe=tf,
        start=datetime.strptime(start_date, "%Y-%m-%d"),
        end=datetime.strptime(end_date, "%Y-%m-%d"),
        feed="iex",
    )
    bars = client.get_stock_bars(request)
    df = bars.df
    if isinstance(df.index, pd.MultiIndex):
        df = df.droplevel("symbol")
    return df


def get_bars_csv(symbol: str, start_date: str, end_date: str) -> str:
    """Fetch historical bars and return as CSV string (drop-in for get_YFin_data_online)."""
    try:
        df = get_bars(symbol, start_date, end_date)
        if df.empty:
            return f"No data found for '{symbol}' between {start_date} and {end_date}"

        # Rename columns to match yfinance output format
        df = df.rename(columns={
            "open": "Open", "high": "High", "low": "Low",
            "close": "Close", "volume": "Volume",
            "trade_count": "Trade Count", "vwap": "VWAP",
        })
        for col in ["Open", "High", "Low", "Close"]:
            if col in df.columns:
                df[col] = df[col].round(2)

        if df.index.tz is not None:
            df.index = df.index.tz_localize(None)

        csv = df.to_csv()
        header = (
            f"# Stock data for {symbol.upper()} from {start_date} to {end_date}\n"
            f"# Source: Alpaca Markets (IEX feed)\n"
            f"# Total records: {len(df)}\n\n"
        )
        return header + csv
    except Exception as e:
        logger.warning("Alpaca bars failed for %s: %s", symbol, e)
        return f"Error fetching Alpaca data for {symbol}: {e}"


# ---------------------------------------------------------------------------
# Snapshots (latest quote/trade)
# ---------------------------------------------------------------------------

def get_snapshot(symbol: str) -> Dict[str, Any]:
    """Get the latest snapshot (quote + trade + bar) for a symbol."""
    from alpaca.data.requests import StockSnapshotRequest

    client = _get_stock_client()
    request = StockSnapshotRequest(symbol_or_symbols=symbol.upper(), feed="iex")
    snapshots = client.get_stock_snapshot(request)
    snap = snapshots.get(symbol.upper())
    if not snap:
        return {}

    result = {
        "ticker": symbol.upper(),
        "latest_trade_price": snap.latest_trade.price if snap.latest_trade else None,
        "latest_trade_size": snap.latest_trade.size if snap.latest_trade else None,
        "latest_trade_time": str(snap.latest_trade.timestamp) if snap.latest_trade else None,
    }
    if snap.latest_quote:
        result["bid"] = snap.latest_quote.bid_price
        result["ask"] = snap.latest_quote.ask_price
        result["bid_size"] = snap.latest_quote.bid_size
        result["ask_size"] = snap.latest_quote.ask_size
    if snap.daily_bar:
        result["daily_open"] = snap.daily_bar.open
        result["daily_high"] = snap.daily_bar.high
        result["daily_low"] = snap.daily_bar.low
        result["daily_close"] = snap.daily_bar.close
        result["daily_volume"] = snap.daily_bar.volume
        result["daily_vwap"] = snap.daily_bar.vwap
    if snap.previous_daily_bar:
        result["prev_close"] = snap.previous_daily_bar.close
        result["prev_volume"] = snap.previous_daily_bar.volume

    return result


def get_multi_snapshots(symbols: List[str]) -> Dict[str, Dict[str, Any]]:
    """Get snapshots for multiple symbols at once."""
    from alpaca.data.requests import StockSnapshotRequest

    client = _get_stock_client()
    request = StockSnapshotRequest(
        symbol_or_symbols=[s.upper() for s in symbols],
        feed="iex",
    )
    snapshots = client.get_stock_snapshot(request)
    result = {}
    for sym, snap in snapshots.items():
        entry = {"ticker": sym}
        if snap.latest_trade:
            entry["price"] = snap.latest_trade.price
        if snap.daily_bar:
            entry["daily_open"] = snap.daily_bar.open
            entry["daily_high"] = snap.daily_bar.high
            entry["daily_low"] = snap.daily_bar.low
            entry["daily_close"] = snap.daily_bar.close
            entry["daily_volume"] = snap.daily_bar.volume
            entry["daily_vwap"] = snap.daily_bar.vwap
        if snap.previous_daily_bar:
            entry["prev_close"] = snap.previous_daily_bar.close
        result[sym] = entry
    return result


# ---------------------------------------------------------------------------
# Computed indicators from bars
# ---------------------------------------------------------------------------

def get_moving_averages(symbol: str) -> Dict[str, Any]:
    """Compute 50-day and 200-day moving averages from Alpaca bars."""
    end = datetime.now()
    start = end - timedelta(days=300)  # ~200 trading days + buffer

    try:
        df = get_bars(symbol, start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
        if df.empty or len(df) < 50:
            return {}

        close = df["close"] if "close" in df.columns else df["Close"]
        result = {
            "current_price": float(close.iloc[-1]),
            "fifty_day_avg": float(close.tail(50).mean()),
        }
        if len(close) >= 200:
            result["two_hundred_day_avg"] = float(close.tail(200).mean())

        # 52-week high/low (approx 252 trading days)
        year_data = close.tail(252) if len(close) >= 252 else close
        result["fifty_two_week_high"] = float(year_data.max())
        result["fifty_two_week_low"] = float(year_data.min())

        hi = result["fifty_two_week_high"]
        lo = result["fifty_two_week_low"]
        price = result["current_price"]
        if (hi - lo) > 0:
            result["vs_52w_range_pct"] = round((price - lo) / (hi - lo) * 100, 1)

        return result
    except Exception as e:
        logger.warning("Alpaca moving averages failed for %s: %s", symbol, e)
        return {}


def get_sector_etf_performance(etf_symbols: List[str]) -> Dict[str, Dict[str, float]]:
    """Compute 1M and 3M returns for a list of sector ETFs."""
    end = datetime.now()
    start_3m = end - timedelta(days=100)

    result = {}
    for sym in etf_symbols:
        try:
            df = get_bars(sym, start_3m.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
            if df.empty or len(df) < 5:
                continue
            close = df["close"] if "close" in df.columns else df["Close"]
            current = float(close.iloc[-1])

            ret_1m = None
            if len(close) >= 22:
                price_1m = float(close.iloc[-22])
                ret_1m = round((current - price_1m) / price_1m * 100, 2)

            ret_3m = None
            if len(close) >= 63:
                price_3m = float(close.iloc[-63])
                ret_3m = round((current - price_3m) / price_3m * 100, 2)

            result[sym] = {
                "return_1m": ret_1m,
                "return_3m": ret_3m,
                "price": current,
            }
        except Exception as e:
            logger.warning("Alpaca ETF perf failed for %s: %s", sym, e)

    return result


# ---------------------------------------------------------------------------
# News
# ---------------------------------------------------------------------------

def get_news(
    symbols: Optional[List[str]] = None,
    limit: int = 10,
    start_date: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Fetch news articles from Alpaca News API."""
    try:
        from alpaca.data.requests import NewsRequest

        client = _get_news_client()
        kwargs: Dict[str, Any] = {"limit": limit}
        if symbols:
            kwargs["symbols"] = [s.upper() for s in symbols]
        if start_date:
            kwargs["start"] = datetime.strptime(start_date, "%Y-%m-%d")

        request = NewsRequest(**kwargs)
        news = client.get_news(request)

        return [
            {
                "title": n.headline,
                "summary": n.summary or "",
                "url": n.url,
                "source": n.source,
                "created_at": str(n.created_at),
                "symbols": n.symbols or [],
            }
            for n in news.news
        ]
    except Exception as e:
        logger.warning("Alpaca news failed: %s", e)
        return []
