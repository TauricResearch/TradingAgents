import json

from .alpha_vantage_common import _make_api_request
from .stockstats_utils import is_historical_date

# OVERVIEW is a live snapshot: valuation ratios, the 52-week range and the
# 50/200-day averages describe today, not the date being analyzed. Only these
# descriptive keys are safe to serve while replaying the past.
# "Description" is excluded on purpose: Alpha Vantage rewrites that prose over
# time, so it can describe acquisitions or product lines that postdate curr_date.
_POINT_IN_TIME_SAFE_KEYS = frozenset({
    "Symbol", "AssetType", "Name", "CIK",
    "Exchange", "Currency", "Country", "Sector", "Industry", "Address",
})

_STALE_SNAPSHOT_NOTE = (
    "{curr_date} is in the past and Alpha Vantage OVERVIEW has no point-in-time "
    "equivalent, so live-quote metrics (market cap, PE, 52-week range, "
    "50/200-day averages) are omitted here to avoid look-ahead bias. Use "
    "get_income_statement / get_balance_sheet / get_cashflow for as-of-date "
    "financials, and get_indicators for as-of-date price statistics."
)


def _strip_snapshot_fields(result, curr_date: str):
    """Drop live-snapshot OVERVIEW keys when curr_date is historical.

    Mirrors ``_filter_reports_by_date``: a non-JSON body or a present-day
    ``curr_date`` is returned unchanged.
    """
    if not is_historical_date(curr_date) or not isinstance(result, str):
        return result
    try:
        payload = json.loads(result)
    except json.JSONDecodeError:
        return result
    if not isinstance(payload, dict):
        return result
    filtered = {k: v for k, v in payload.items() if k in _POINT_IN_TIME_SAFE_KEYS}
    filtered["Note"] = _STALE_SNAPSHOT_NOTE.format(curr_date=curr_date)
    return json.dumps(filtered)


def _filter_reports_by_date(result, curr_date: str):
    """Drop annual/quarterly reports dated after curr_date to prevent look-ahead.

    ``_make_api_request`` returns the fundamentals payload as a JSON string, so
    parse, filter, and re-serialize. A non-JSON body or an unset ``curr_date`` is
    returned unchanged.
    """
    if not curr_date or not isinstance(result, str):
        return result
    try:
        payload = json.loads(result)
    except json.JSONDecodeError:
        return result
    if not isinstance(payload, dict):
        return result
    for key in ("annualReports", "quarterlyReports"):
        if isinstance(payload.get(key), list):
            payload[key] = [
                r for r in payload[key]
                if r.get("fiscalDateEnding", "") <= curr_date
            ]
    return json.dumps(payload)


def get_fundamentals(ticker: str, curr_date: str = None) -> str:
    """
    Retrieve comprehensive fundamental data for a given ticker symbol using Alpha Vantage.

    Args:
        ticker (str): Ticker symbol of the company
        curr_date (str): Current date you are trading at, yyyy-mm-dd. When it is
            in the past, live-snapshot metrics are withheld to avoid look-ahead.

    Returns:
        str: Company overview data including financial ratios and key metrics
    """
    params = {
        "symbol": ticker,
    }

    return _strip_snapshot_fields(_make_api_request("OVERVIEW", params), curr_date)


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

