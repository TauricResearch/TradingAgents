#!/usr/bin/env python3
"""Fetch current price and recent history for a single ticker via yfinance.

Usage: python3 scripts/get_price.py TICKER

Outputs a single JSON object to stdout:
{
  "ticker": "AAPL",
  "price": 192.50,
  "currency": "USD",
  "previousClose": 191.00,
  "dayHigh": 193.20,
  "dayLow": 191.50,
  "volume": 45000000,
  "history": [{"date": "2026-05-01", "close": 191.00}, ...]
}

Exits with code 1 on failure (ticker not found, network error, etc.).
"""
import json
import sys
from datetime import datetime, timedelta

import yfinance as yf


def get_price(ticker: str) -> dict:
    """Fetch price data for a single ticker."""
    try:
        stock = yf.Ticker(ticker)
        info = stock.fast_info

        # Get price history for the last 30 days
        end_date = datetime.now()
        start_date = end_date - timedelta(days=30)
        hist = stock.history(start=start_date, end=end_date)

        history = []
        if not hist.empty:
            for date, row in hist.iterrows():
                history.append({
                    "date": date.strftime("%Y-%m-%d"),
                    "close": round(float(row.get("Close", 0)), 2),
                })

        price = getattr(info, "last_price", None)
        if price is not None:
            price = float(price)

        return {
            "ticker": ticker,
            "price": price,
            "currency": getattr(info, "currency", "USD"),
            "previousClose": _safe_float(getattr(info, "previous_close", None)),
            "dayHigh": _safe_float(getattr(info, "day_high", None)),
            "dayLow": _safe_float(getattr(info, "day_low", None)),
            "volume": int(getattr(info, "last_volume", 0) or 0),
            "history": history,
        }
    except Exception as e:
        print(f"Error fetching {ticker}: {e}", file=sys.stderr)
        sys.exit(1)


def _safe_float(val) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: get_price.py TICKER", file=sys.stderr)
        sys.exit(1)

    result = get_price(sys.argv[1])
    print(json.dumps(result))
