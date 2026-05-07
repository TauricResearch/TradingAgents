import datetime

from .alpha_vantage_common import _make_api_request


def _filter_reports_by_date(result, curr_date: str | None):
    """Filter Alpha Vantage report arrays to exclude entries after curr_date.

    Prevents look-ahead bias by removing fiscal periods that end after
    the simulation's current date.

    Args:
        result: Raw API response (dict with report arrays, or error string).
        curr_date: Cutoff date in YYYY-MM-DD format. If None, returns result unchanged.

    Returns:
        A new filtered result dict, or original if curr_date is None or result is not a dict.
        The original dict is never mutated.

    Raises:
        ValueError: If curr_date is provided but not a valid calendar date in YYYY-MM-DD format
                    (e.g. "2025-99-99" is rejected even though it matches the digit pattern).
    """
    if curr_date is None or not isinstance(result, dict):
        return result

    # Parse curr_date to reject both malformed strings and invalid calendar dates
    # (e.g. "2025-99-99" passes a regex but fromisoformat raises ValueError).
    try:
        cutoff = datetime.date.fromisoformat(curr_date)
    except ValueError as exc:
        raise ValueError(
            f"_filter_reports_by_date: curr_date={curr_date!r} is not in YYYY-MM-DD format"
        ) from exc

    result = {**result}  # shallow-copy to avoid mutating the caller's dict
    for key in ("annualReports", "quarterlyReports"):
        if key in result:
            result[key] = [
                r
                for r in result[key]
                if r.get("fiscalDateEnding") and r["fiscalDateEnding"] <= cutoff.isoformat()
            ]
    return result


def get_fundamentals(ticker: str, curr_date: str = None) -> str:
    """
    Retrieve comprehensive fundamental data for a given ticker symbol using Alpha Vantage.

    Args:
        ticker (str): Ticker symbol of the company
        curr_date (str): Current date you are trading at, yyyy-mm-dd (not used for Alpha Vantage OVERVIEW)

    Returns:
        str: Company overview data including financial ratios and key metrics

    Note:
        The OVERVIEW endpoint returns a flat dict of key-value pairs (e.g. EPS,
        PERatio, 52WeekHigh) rather than date-indexed report arrays. Because
        there are no annualReports/quarterlyReports arrays to filter,
        _filter_reports_by_date is intentionally not applied here. The values
        reflect the latest available snapshot from Alpha Vantage and cannot be
        reliably date-filtered without a historical API.
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
