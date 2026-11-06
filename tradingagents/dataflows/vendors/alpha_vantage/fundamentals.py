import json

import pandas as pd

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


def _statement(api_function: str, ticker: str, freq: str, as_of_date: str | None, title: str) -> str:
    """One Alpha Vantage statement as CSV, one row per period, for the asked frequency.

    The endpoint always serves both ``annualReports`` and ``quarterlyReports``;
    served raw as JSON, all of it reached the prompt: every field name repeated
    per period, both frequencies at once, dozens of periods, which put a run far
    past small models' context (#1625). The model asks for a frequency, that is
    what it gets — one CSV row per period, so a figure sits beside its own
    fiscal date.
    """
    canonical = ticker.upper()
    withheld = withhold_undated_statements(as_of_date, canonical, title)
    if withheld:
        return withheld

    freq = freq.lower()
    if freq not in ("annual", "quarterly"):
        return _reject_frequency(canonical, freq, title)
    key = "annualReports" if freq == "annual" else "quarterlyReports"

    response = _make_api_request(api_function, {"symbol": canonical})
    report = json.loads(response)
    rows = report.get(key)
    if rows is None:
        # Alpha Vantage reports problems inside a JSON body it returns too; the
        # request helpers catch their own, so a bare miss has nothing to serve.
        return report if isinstance(report, str) else json.dumps(report)

    period_column = "fiscalDateEnding"
    frame = pd.DataFrame(rows)
    if period_column in frame.columns and not frame.empty:
        frame = frame[[period_column, *sorted(c for c in frame.columns if c != period_column)]]
        # Company-published order; dates run newest first, oldest first reads
        # like every other statement vendor (#1517).
        frame = frame.iloc[::-1]
    return f"# {title} data for {canonical} ({freq})\n" + frame.to_csv(index=False)


def _reject_frequency(ticker: str, freq: str, title: str) -> str:
    """Send a frequency this endpoint does not serve back to the model (#1593)."""
    return (
        f"'{freq}' is not a frequency {ticker}'s Alpha Vantage {title.lower()} serves; "
        "it carries no figures under that word. Re-ask with 'annual' or 'quarterly'."
    )


def get_balance_sheet(ticker: str, freq: str = "quarterly", as_of_date: str = None):
    """Retrieve balance sheet data for a given ticker symbol using Alpha Vantage."""
    return _statement("BALANCE_SHEET", ticker, freq, as_of_date, "Balance Sheet")


def get_cashflow(ticker: str, freq: str = "quarterly", as_of_date: str = None):
    """Retrieve cash flow statement data for a given ticker symbol using Alpha Vantage."""
    return _statement("CASH_FLOW", ticker, freq, as_of_date, "Cash Flow")


def get_income_statement(ticker: str, freq: str = "quarterly", as_of_date: str = None):
    """Retrieve income statement data for a given ticker symbol using Alpha Vantage."""
    return _statement("INCOME_STATEMENT", ticker, freq, as_of_date, "Income Statement")

