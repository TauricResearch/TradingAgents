from .alpha_vantage_common import _make_api_request


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
    # Filter out reports whose fiscalDateEnding is after curr_date to prevent look-ahead bias.
    if curr_date and isinstance(result, dict):
        for key in ("annualReports", "quarterlyReports"):
            if key in result:
                result[key] = [r for r in result[key]
                               if r.get("fiscalDateEnding", "") <= curr_date]
    return result


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
    # Filter out reports whose fiscalDateEnding is after curr_date to prevent look-ahead bias.
    if curr_date and isinstance(result, dict):
        for key in ("annualReports", "quarterlyReports"):
            if key in result:
                result[key] = [r for r in result[key]
                               if r.get("fiscalDateEnding", "") <= curr_date]
    return result


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
    # Filter out reports whose fiscalDateEnding is after curr_date to prevent look-ahead bias.
    if curr_date and isinstance(result, dict):
        for key in ("annualReports", "quarterlyReports"):
            if key in result:
                result[key] = [r for r in result[key]
                               if r.get("fiscalDateEnding", "") <= curr_date]
    return result

