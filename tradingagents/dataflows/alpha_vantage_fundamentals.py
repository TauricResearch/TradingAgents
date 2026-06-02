"""Alpha Vantage fundamental-data fetchers."""

from __future__ import annotations

from .alpha_vantage_common import _make_api_request
from .cache_utils import cache_text
from .point_in_time import historical_snapshot_caveat


def _filter_reports_by_date(result, curr_date: str):
    """Filter annualReports/quarterlyReports to exclude entries after curr_date.

    Prevents look-ahead bias by removing fiscal periods that end after
    the simulation's current date.
    """
    if not curr_date or not isinstance(result, dict):
        return result
    for key in ("annualReports", "quarterlyReports"):
        if key in result:
            result[key] = [
                r for r in result[key]
                if r.get("fiscalDateEnding", "") <= curr_date
            ]
    return result


def get_fundamentals(ticker: str, curr_date: str = None) -> str:
    """
    Retrieve Alpha Vantage company overview data.

    The OVERVIEW endpoint is a latest snapshot, not a point-in-time
    historical source. When ``curr_date`` is in the past, the response is
    prefixed with an explicit caveat so historical backtests do not treat
    the latest valuation metrics as if they existed on that date.
    """

    def fetch() -> str:
        payload = _make_api_request("OVERVIEW", {"symbol": ticker})
        return historical_snapshot_caveat(curr_date) + str(payload)

    return cache_text(
        "alpha_vantage_fundamentals",
        (str(ticker), str(curr_date or "latest")),
        fetch,
    )


def get_balance_sheet(ticker: str, freq: str = "quarterly", curr_date: str = None):
    """Retrieve balance sheet data for a given ticker symbol using Alpha Vantage."""
    result = _make_api_request("BALANCE_SHEET", {"symbol": ticker})
    return _filter_reports_by_date(result, curr_date)


def get_cashflow(ticker: str, freq: str = "quarterly", curr_date: str = None):
    """Retrieve cash flow statement data for a given ticker symbol using Alpha Vantage."""
    result = _make_api_request("CASH_FLOW", {"symbol": ticker})
    return _filter_reports_by_date(result, curr_date)


def get_income_statement(ticker: str, freq: str = "quarterly", curr_date: str = None):
    """Retrieve income statement data for a given ticker symbol using Alpha Vantage."""
    result = _make_api_request("INCOME_STATEMENT", {"symbol": ticker})
    return _filter_reports_by_date(result, curr_date)
