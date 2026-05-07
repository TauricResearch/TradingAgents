from __future__ import annotations

import datetime

from .alpha_vantage_common import _make_api_request


def _filter_reports_by_date(result: dict | str, curr_date: str | None) -> dict | str:
    """Filter Alpha Vantage report arrays to exclude entries after curr_date.

    Filters both 'annualReports' and 'quarterlyReports' keys by comparing
    each entry's 'fiscalDateEnding' field against curr_date.

    Args:
        result: Raw API response (dict with report arrays, or error string).
        curr_date: Cutoff date in YYYY-MM-DD format. If None, returns result unchanged.

    Returns:
        Filtered result dict, or original if curr_date is None or result is not a dict.

    Raises:
        ValueError: If curr_date is provided but not a valid calendar date.
    """
    if curr_date is None:
        return result
    if not isinstance(result, dict):
        return result

    # Validate curr_date is a real calendar date in strict YYYY-MM-DD format.
    # datetime.date.fromisoformat() in Python 3.11+ accepts YYYYMMDD and other
    # ISO variants, so we enforce the hyphenated format explicitly.
    try:
        parsed = datetime.date.fromisoformat(curr_date)
    except (ValueError, TypeError) as exc:
        raise ValueError(
            f"curr_date must be a valid YYYY-MM-DD date string, got: {curr_date!r}"
        ) from exc
    if curr_date != parsed.isoformat():
        raise ValueError(
            f"curr_date must be in YYYY-MM-DD format, got: {curr_date!r}"
        )

    for key in ("annualReports", "quarterlyReports"):
        if key in result:
            result[key] = [
                r
                for r in result[key]
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


def get_balance_sheet(ticker: str, freq: str = "quarterly", curr_date: str = None) -> str:
    """
    Retrieve balance sheet data for a given ticker symbol using Alpha Vantage.

    Args:
        ticker (str): Ticker symbol of the company
        freq (str): Reporting frequency: annual/quarterly (default quarterly) - not used for Alpha Vantage
        curr_date (str): Current date you are trading at, yyyy-mm-dd

    Returns:
        str: Balance sheet data with normalized fields
    """
    params = {
        "symbol": ticker,
    }

    result = _make_api_request("BALANCE_SHEET", params)
    return _filter_reports_by_date(result, curr_date)


def get_cashflow(ticker: str, freq: str = "quarterly", curr_date: str = None) -> str:
    """
    Retrieve cash flow statement data for a given ticker symbol using Alpha Vantage.

    Args:
        ticker (str): Ticker symbol of the company
        freq (str): Reporting frequency: annual/quarterly (default quarterly) - not used for Alpha Vantage
        curr_date (str): Current date you are trading at, yyyy-mm-dd

    Returns:
        str: Cash flow statement data with normalized fields
    """
    params = {
        "symbol": ticker,
    }

    result = _make_api_request("CASH_FLOW", params)
    return _filter_reports_by_date(result, curr_date)


def get_income_statement(ticker: str, freq: str = "quarterly", curr_date: str = None) -> str:
    """
    Retrieve income statement data for a given ticker symbol using Alpha Vantage.

    Args:
        ticker (str): Ticker symbol of the company
        freq (str): Reporting frequency: annual/quarterly (default quarterly) - not used for Alpha Vantage
        curr_date (str): Current date you are trading at, yyyy-mm-dd

    Returns:
        str: Income statement data with normalized fields
    """
    params = {
        "symbol": ticker,
    }

    result = _make_api_request("INCOME_STATEMENT", params)
    return _filter_reports_by_date(result, curr_date)
