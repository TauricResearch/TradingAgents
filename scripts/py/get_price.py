#!/usr/bin/env python3
"""
Get current price for a ticker using yfinance.
Outputs JSON: {"ticker": "...", "price": ..., "currency": "..."}

Currency semantics:
  - USD ticker (AAPL, BTC-USD): currency = "USD" → route converts via GBPUSD
  - EUR ticker (VWCE.DE):        currency = "EUR" → route converts via GBPEUR
  - GBP ticker (.L):             currency = "GBP" → route uses directly
  - FX pair (GBPEUR=X):          returns GBP-per-unit, currency = "GBP"
"""
import sys
import json

try:
    import yfinance as yf
except ImportError:
    print(json.dumps({"error": "yfinance not installed"}))
    sys.exit(1)

# Map common tickers to yfinance symbols
TICKER_MAP = {
    "BTC": "BTC-USD",
    "ETH": "ETH-USD",
    "SOL": "SOL-USD",
    "XRP": "XRP-USD",
}

# Map exchange/prefix to quote currency
QUOTE_CURRENCY = {
    ".DE": "EUR",
    ".L":  "GBP",
    "CRYPTO": "USD",
}


def get_price(ticker: str) -> dict:
    """Fetch current price for a ticker, return price + quote currency."""
    # Map to yfinance symbol
    yf_ticker = TICKER_MAP.get(ticker, ticker)

    try:
        stock = yf.Ticker(yf_ticker)
        hist = stock.history(period="1d", auto_adjust=True)
        if hist.empty:
            return {"ticker": ticker, "price": None, "currency": "USD", "note": "no data"}
        price = float(hist["Close"].iloc[-1])
    except Exception as e:
        return {"ticker": ticker, "price": None, "currency": "USD", "error": str(e)}

    # Determine quote currency from ticker pattern
    if ticker.endswith("=X"):
        # FX pair: GBPEUR=X, GBPUSD=X — price is in GBP per unit
        return {"ticker": ticker, "price": price, "currency": "GBP"}
    elif ".DE" in ticker:
        return {"ticker": ticker, "price": price, "currency": "EUR"}
    elif ".L" in ticker:
        return {"ticker": ticker, "price": price, "currency": "GBP"}
    elif ticker in TICKER_MAP:
        # Crypto (BTC, ETH, etc.)
        return {"ticker": ticker, "price": price, "currency": "USD"}
    else:
        return {"ticker": ticker, "price": price, "currency": "USD"}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: get_price.py TICKER"}))
        sys.exit(1)

    ticker = sys.argv[1].strip().upper()
    result = get_price(ticker)
    print(json.dumps(result))