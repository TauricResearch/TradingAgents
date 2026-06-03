"""AKShare market-data vendor.

Task 3 registers AKShare in the provider chain; Task 4 replaces these
fallback-compatible bodies with real daily OHLCV formatting.
"""

from .errors import DataVendorError


def get_stock_data(symbol: str, start_date: str, end_date: str) -> str:
    raise DataVendorError("akshare.get_stock_data unavailable before Task 4")


def get_market_snapshot(
    ticker: str,
    curr_date: str,
    lookback_days: int = 10,
    stale_after_seconds: int = 900,
) -> str:
    raise DataVendorError("akshare.get_market_snapshot unavailable before Task 4")
