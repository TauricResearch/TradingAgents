import json
from typing import Any

from .alpha_vantage_common import _make_api_request


def _filter_reports_by_date(result: dict[str, Any], curr_date: str | None) -> dict[str, Any]:
    """Filter annualReports/quarterlyReports to exclude entries after curr_date.

    Prevents look-ahead bias by removing fiscal periods that end after
    the simulation's current date.
    """
    if not curr_date:
        return result
    for key in ("annualReports", "quarterlyReports"):
        if key in result:
            result[key] = [
                r for r in result[key]
                if r.get("fiscalDateEnding", "") <= curr_date
            ]
    return result


def _filter_statement_response(response_text: str, curr_date: str | None) -> str:
    if not curr_date:
        return response_text
    try:
        result = json.loads(response_text)
    except json.JSONDecodeError:
        return response_text
    if not isinstance(result, dict):
        return response_text
    return json.dumps(_filter_reports_by_date(result, curr_date))


def get_fundamentals(ticker: str, curr_date: str | None = None) -> str:
    """
    Retrieve comprehensive fundamental data for a given ticker symbol using Alpha Vantage.

    Args:
        ticker (str): Ticker symbol of the company
        curr_date (str): Current date you are trading at, yyyy-mm-dd (not used for Alpha Vantage)

    Returns:
        str: Company overview data including financial ratios and key metrics
    """
    params = {
        "symbol": ticker,
    }

    return _make_api_request("OVERVIEW", params)


def get_balance_sheet(
    ticker: str, freq: str = "quarterly", curr_date: str | None = None
) -> str:
    """Retrieve balance sheet data for a given ticker symbol using Alpha Vantage."""
    response_text = _make_api_request("BALANCE_SHEET", {"symbol": ticker})
    return _filter_statement_response(response_text, curr_date)


def get_cashflow(ticker: str, freq: str = "quarterly", curr_date: str | None = None) -> str:
    """Retrieve cash flow statement data for a given ticker symbol using Alpha Vantage."""
    response_text = _make_api_request("CASH_FLOW", {"symbol": ticker})
    return _filter_statement_response(response_text, curr_date)


def get_income_statement(
    ticker: str, freq: str = "quarterly", curr_date: str | None = None
) -> str:
    """Retrieve income statement data for a given ticker symbol using Alpha Vantage."""
    response_text = _make_api_request("INCOME_STATEMENT", {"symbol": ticker})
    return _filter_statement_response(response_text, curr_date)

