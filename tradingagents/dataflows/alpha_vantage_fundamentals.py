from typing import Union

from .alpha_vantage_common import _make_api_request


def _filter_reports_by_date(result: dict, curr_date: str) -> dict:
    """Remove annualReports/quarterlyReports whose fiscalDateEnding exceeds curr_date.

    Mutates *result* in-place and returns it so callers can chain the call.
    """
    if not (curr_date and isinstance(result, dict)):
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
    ticker: str, freq: str = "quarterly", curr_date: str = None
) -> Union[dict, str]:
    """
    Retrieve balance sheet data for a given ticker symbol using Alpha Vantage.

    Args:
        ticker (str): Ticker symbol of the company
        freq (str): Reporting frequency: annual/quarterly (default quarterly) - not used for Alpha Vantage
        curr_date (str): Current date you are trading at, yyyy-mm-dd

    Returns:
        dict | str: Balance sheet data dict, or an error string.
    """
    params = {
        "symbol": ticker,
    }

    result = _make_api_request("BALANCE_SHEET", params)
    return _filter_reports_by_date(result, curr_date)


def get_cashflow(
    ticker: str, freq: str = "quarterly", curr_date: str = None
) -> Union[dict, str]:
    """
    Retrieve cash flow statement data for a given ticker symbol using Alpha Vantage.

    Args:
        ticker (str): Ticker symbol of the company
        freq (str): Reporting frequency: annual/quarterly (default quarterly) - not used for Alpha Vantage
        curr_date (str): Current date you are trading at, yyyy-mm-dd

    Returns:
        dict | str: Cash flow statement data dict, or an error string.
    """
    params = {
        "symbol": ticker,
    }

    result = _make_api_request("CASH_FLOW", params)
    return _filter_reports_by_date(result, curr_date)


def get_income_statement(
    ticker: str, freq: str = "quarterly", curr_date: str = None
) -> Union[dict, str]:
    """
    Retrieve income statement data for a given ticker symbol using Alpha Vantage.

    Args:
        ticker (str): Ticker symbol of the company
        freq (str): Reporting frequency: annual/quarterly (default quarterly) - not used for Alpha Vantage
        curr_date (str): Current date you are trading at, yyyy-mm-dd

    Returns:
        dict | str: Income statement data dict, or an error string.
    """
    params = {
        "symbol": ticker,
    }

    result = _make_api_request("INCOME_STATEMENT", params)
    return _filter_reports_by_date(result, curr_date)
