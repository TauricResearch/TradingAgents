"""Phase 4 LangChain @tool wrappers for Jintel-only capabilities.

These three tools have no yfinance or Alpha Vantage equivalent in the repo;
``route_to_vendor`` dispatches them straight to ``tradingagents/dataflows/
jintel.py``. If Jintel rate-limits or returns no data the dispatcher exhausts
the (single-vendor) chain and surfaces ``RuntimeError`` -- the analyst will
see that as a tool error and continue without the data.
"""

from langchain_core.tools import tool
from typing import Annotated
from tradingagents.dataflows.interface import route_to_vendor


@tool
def get_filings(
    ticker: Annotated[str, "ticker symbol"],
    curr_date: Annotated[str, "current date you are trading at, yyyy-mm-dd"] = None,
) -> str:
    """Retrieve recent SEC periodic filings (10-K, 10-Q, 8-K) for a ticker.

    Useful for grounding analyst commentary in primary sources -- each row
    carries the form type, filing date, report date, and a filing_url that
    Claude can cite directly.
    """
    return route_to_vendor("get_filings", ticker, curr_date)


@tool
def get_macro_series(
    series_id: Annotated[str, "FRED-style series id, e.g. UNRATE / CPIAUCSL / GDPC1 / FEDFUNDS"],
    curr_date: Annotated[str, "current date you are trading at, yyyy-mm-dd"] = None,
    look_back_days: Annotated[int, "how many days of history to fetch"] = 365,
) -> str:
    """Retrieve a US macro time series (FRED-style) ending at curr_date.

    Common series: ``UNRATE`` (unemployment), ``CPIAUCSL`` (CPI),
    ``GDPC1`` (real GDP), ``FEDFUNDS`` (fed funds rate). Returns CSV with
    ``date,value`` rows.
    """
    return route_to_vendor("get_macro_series", series_id, curr_date, look_back_days)


@tool
def get_top_holders(
    ticker: Annotated[str, "ticker symbol"],
) -> str:
    """Retrieve top institutional holders (13F) of a ticker.

    Returns the largest filer-by-value rows: filer name + CIK, value held,
    shares held, report date, filing date.
    """
    return route_to_vendor("get_top_holders", ticker)


@tool
def get_stock_data_intraday(
    symbol: Annotated[str, "ticker symbol of the company"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
) -> str:
    """Retrieve **hourly** OHLCV bars for a US equity / ETF / index.

    Jintel's intraday index covers roughly the last 12 months at hourly
    resolution. Sub-hour intervals are not currently available; for daily
    bars use ``get_stock_data`` instead. Out-of-window requests raise so
    the analyst sees a clean error rather than an empty CSV.

    Returns CSV with ``Date,Open,High,Low,Close,Volume`` rows in
    chronological order.
    """
    return route_to_vendor("get_stock_data_intraday", symbol, start_date, end_date)
