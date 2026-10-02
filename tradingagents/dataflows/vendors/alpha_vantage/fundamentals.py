from tradingagents.dataflows.date_window import withhold_live_profile, withhold_undated_statements
from tradingagents.dataflows.vendors.alpha_vantage.common import _make_api_request


def get_fundamentals(ticker: str, as_of_date: str = None) -> str:
    """
    Retrieve comprehensive fundamental data for a given ticker symbol using Alpha Vantage.

    OVERVIEW serves only present-day values and carries no historical vintage, so
    a past ``as_of_date`` withholds it rather than leaking post-decision figures
    into a backtest (#1300); so are the statement endpoints below, which carry
    no filing date.

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
    withheld = withhold_undated_statements(as_of_date, ticker, "Balance Sheet")
    if withheld:
        return withheld
    return _make_api_request("BALANCE_SHEET", {"symbol": ticker})


def get_cashflow(ticker: str, freq: str = "quarterly", as_of_date: str = None):
    """Retrieve cash flow statement data for a given ticker symbol using Alpha Vantage."""
    withheld = withhold_undated_statements(as_of_date, ticker, "Cash Flow")
    if withheld:
        return withheld
    return _make_api_request("CASH_FLOW", {"symbol": ticker})


def get_income_statement(ticker: str, freq: str = "quarterly", as_of_date: str = None):
    """Retrieve income statement data for a given ticker symbol using Alpha Vantage."""
    withheld = withhold_undated_statements(as_of_date, ticker, "Income Statement")
    if withheld:
        return withheld
    return _make_api_request("INCOME_STATEMENT", {"symbol": ticker})
