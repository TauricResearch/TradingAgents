import json

from tradingagents.dataflows.date_window import withhold_live_profile
from tradingagents.dataflows.vendors.alpha_vantage.common import _make_api_request


def _filter_reports_by_date(result, as_of_date: str):
    """Drop annual/quarterly reports dated after as_of_date to prevent look-ahead.

    ``_make_api_request`` returns the fundamentals payload as a JSON string, so
    parse, filter, and re-serialize. A non-JSON body or an unset ``as_of_date`` is
    returned unchanged.
    """
    if not as_of_date or not isinstance(result, str):
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
                if r.get("fiscalDateEnding", "") <= as_of_date
            ]
    return json.dumps(payload)


def get_fundamentals(ticker: str, as_of_date: str = None) -> str:
    """
    Retrieve comprehensive fundamental data for a given ticker symbol using Alpha Vantage.

    OVERVIEW serves only present-day values and carries no historical vintage, so
    a past ``as_of_date`` withholds it rather than leaking post-decision figures
    into a backtest (#1300); the statement endpoints below stay point-in-time via
    ``_filter_reports_by_date``.

    Args:
        ticker (str): Ticker symbol of the company
        as_of_date (str): Analysis date, yyyy-mm-dd

    Returns:
        str: Company overview data including financial ratios and key metrics
    """
    withheld = withhold_live_profile(as_of_date, ticker)
    if withheld:
        return withheld

    params = {
        "symbol": ticker,
    }

    return _make_api_request("OVERVIEW", params)


def get_balance_sheet(ticker: str, freq: str = "quarterly", as_of_date: str = None):
    """Retrieve balance sheet data for a given ticker symbol using Alpha Vantage."""
    result = _make_api_request("BALANCE_SHEET", {"symbol": ticker})
    return _filter_reports_by_date(result, as_of_date)


def get_cashflow(ticker: str, freq: str = "quarterly", as_of_date: str = None):
    """Retrieve cash flow statement data for a given ticker symbol using Alpha Vantage."""
    result = _make_api_request("CASH_FLOW", {"symbol": ticker})
    return _filter_reports_by_date(result, as_of_date)


def get_income_statement(ticker: str, freq: str = "quarterly", as_of_date: str = None):
    """Retrieve income statement data for a given ticker symbol using Alpha Vantage."""
    result = _make_api_request("INCOME_STATEMENT", {"symbol": ticker})
    return _filter_reports_by_date(result, as_of_date)

