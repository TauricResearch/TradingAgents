from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional, Tuple

import yfinance as yf

logger = logging.getLogger(__name__)


def fetch_returns(
    ticker: str,
    trade_date: str,
    holding_days: int,
) -> Tuple[Optional[float], Optional[float], Optional[int]]:
    """Fetch (raw_return, alpha_vs_spy, actual_holding_days) via yfinance.

    Requires network access. Returns (None, None, None) when price data is
    unavailable — ticker too recent, delisted, or a network error occurred.
    When testing this function directly, patch tradingagents.backtesting.returns.yf.Ticker. When testing callers (e.g. BacktestReport), patch at the caller's import location.
    """
    try:
        start = datetime.strptime(trade_date, "%Y-%m-%d")
        end = start + timedelta(days=holding_days + 7)  # buffer for weekends/holidays
        end_str = end.strftime("%Y-%m-%d")

        stock = yf.Ticker(ticker).history(start=trade_date, end=end_str)
        spy = yf.Ticker("SPY").history(start=trade_date, end=end_str)

        if len(stock) < 2 or len(spy) < 2:
            return None, None, None

        actual_days = min(holding_days, len(stock) - 1, len(spy) - 1)
        raw = float(
            (stock["Close"].iloc[actual_days] - stock["Close"].iloc[0])
            / stock["Close"].iloc[0]
        )
        spy_ret = float(
            (spy["Close"].iloc[actual_days] - spy["Close"].iloc[0])
            / spy["Close"].iloc[0]
        )
        alpha = raw - spy_ret
        return raw, alpha, actual_days
    except Exception as exc:
        logger.warning(
            "Could not fetch returns for %s on %s: %s", ticker, trade_date, exc
        )
        return None, None, None
