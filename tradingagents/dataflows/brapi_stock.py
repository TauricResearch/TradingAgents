"""brapi.dev OHLCV vendor for B3 tickers.

Mirrors the contract ``get_YFin_data_online`` (y_finance.py) and
``get_alpha_vantage_stock`` (alpha_vantage_stock.py) already provide: a
header comment block plus a CSV body with a ``Date`` column, so the router
and every downstream agent treat this vendor exactly like the others.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

import pandas as pd

from .brapi_common import brapi_request, strip_b3_suffix
from .errors import NoMarketDataError
from .stockstats_utils import _assert_ohlcv_not_stale
from .utils import vendor_reachable

_BRAPI_HOST = "https://brapi.dev"

# brapi's `range` accepts fixed buckets rather than an arbitrary start date, so
# request the smallest bucket that covers the requested window and filter
# client-side (same pattern alpha_vantage_common._filter_csv_by_date_range
# uses for Alpha Vantage's always-full series).
_RANGE_BUCKETS = [
    (7, "5d"), (30, "1mo"), (90, "3mo"), (180, "6mo"),
    (365, "1y"), (365 * 2, "2y"), (365 * 5, "5y"), (365 * 10, "10y"),
]


def _pick_range(start_date: str) -> str:
    """Pick the smallest brapi ``range`` bucket that reaches back to ``start_date``.

    brapi's buckets (``5d``, ``1mo``, ...) are windows ending *today*, not
    windows sized to the requested date range, so the bucket must cover
    "today minus start_date" rather than the span between start and end date.
    """
    age_days = (datetime.now() - datetime.strptime(start_date, "%Y-%m-%d")).days
    for max_days, bucket in _RANGE_BUCKETS:
        if age_days <= max_days:
            return bucket
    return "max"


def get_stock_data(
    symbol: Annotated[str, "ticker symbol of the company (e.g. PETR4 or PETR4.SA)"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
) -> str:
    """Retrieve daily OHLCV history for a B3 ticker via brapi.dev."""
    datetime.strptime(start_date, "%Y-%m-%d")
    datetime.strptime(end_date, "%Y-%m-%d")

    canonical = strip_b3_suffix(symbol)
    range_bucket = _pick_range(start_date)

    payload = brapi_request(
        f"quote/{canonical}",
        {"range": range_bucket, "interval": "1d"},
    )

    results = payload.get("results") or []
    if not results or not results[0].get("historicalDataPrice"):
        if not vendor_reachable(_BRAPI_HOST):
            from .errors import VendorRateLimitError
            raise VendorRateLimitError("brapi.dev is unreachable; no price history was retrieved")
        raise NoMarketDataError(symbol, canonical, "no historical price data")

    rows = results[0]["historicalDataPrice"]
    data = pd.DataFrame(rows)
    # brapi timestamps are Unix seconds; normalize to a plain Date column.
    data["Date"] = pd.to_datetime(data["date"], unit="s").dt.tz_localize(None)
    data = data.rename(columns={
        "open": "Open", "high": "High", "low": "Low",
        "close": "Close", "adjustedClose": "Adj Close", "volume": "Volume",
    })

    start_dt = pd.to_datetime(start_date)
    end_dt = pd.to_datetime(end_date)
    data = data[(data["Date"] >= start_dt) & (data["Date"] <= end_dt)]

    keep_cols = [c for c in ["Date", "Open", "High", "Low", "Close", "Adj Close", "Volume"] if c in data.columns]
    data = data[keep_cols].sort_values("Date")

    if data.empty:
        raise NoMarketDataError(symbol, canonical, f"no rows between {start_date} and {end_date}")

    _assert_ohlcv_not_stale(data.set_index("Date"), end_date, symbol, canonical)

    for col in ["Open", "High", "Low", "Close", "Adj Close"]:
        if col in data.columns:
            data[col] = data[col].round(2)

    csv_string = data.to_csv(index=False)

    label = canonical if canonical == symbol.upper() else f"{canonical} (from {symbol})"
    header = f"# Stock data for {label} from {start_date} to {end_date}\n"
    header += f"# Total records: {len(data)}\n"
    header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

    return header + csv_string
