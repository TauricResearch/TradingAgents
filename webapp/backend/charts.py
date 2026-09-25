"""Free live price series for the frontend's chart preview.

Deliberately separate from ``tradingagents.dataflows.y_finance`` (which
formats OHLCV as a CSV string for LLM prompts): this returns plain numeric
JSON for a browser chart, and only ever needs a closing-price line, not the
full agent-facing dataset.
"""

from __future__ import annotations

import yfinance as yf

from tradingagents.dataflows.stockstats_utils import yf_retry
from tradingagents.dataflows.symbol_utils import normalize_symbol

# yfinance's own accepted `period` values; validated against this allowlist
# before being forwarded, since an arbitrary string would otherwise surface
# as an opaque yfinance error.
ALLOWED_RANGES = ("5d", "1mo", "3mo", "6mo", "1y", "5y")


class ChartUnavailable(Exception):
    """No price data could be fetched for this ticker/range."""


def get_price_series(ticker: str, range_: str) -> list[dict]:
    if range_ not in ALLOWED_RANGES:
        raise ValueError(f"range must be one of {ALLOWED_RANGES}, got {range_!r}")

    canonical = normalize_symbol(ticker)
    yf_ticker = yf.Ticker(canonical)
    try:
        data = yf_retry(lambda: yf_ticker.history(period=range_))
    except Exception as exc:  # noqa: BLE001 - any yfinance/network failure
        raise ChartUnavailable(f"Could not fetch price data for {ticker}: {exc}") from exc

    if data.empty:
        raise ChartUnavailable(f"No price data available for {ticker}")

    if data.index.tz is not None:
        data.index = data.index.tz_localize(None)

    return [
        {"date": index.strftime("%Y-%m-%d"), "close": round(float(row["Close"]), 2)}
        for index, row in data.iterrows()
    ]
