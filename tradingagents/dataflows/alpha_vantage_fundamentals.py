"""Alpha Vantage fundamentals wrappers.

Each function prepends a small header that surfaces the reporting currency
(if present in the upstream response) so downstream analysis can spot
ADR-style currency mismatches before computing per-share figures in USD.
"""

import json

from .alpha_vantage_common import _make_api_request


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


def _extract_reported_currency(result) -> str | None:
    """Return the reportedCurrency from the most recent period if present.

    Alpha Vantage's INCOME_STATEMENT / BALANCE_SHEET / CASH_FLOW each fiscal
    period entry carries a reportedCurrency field; we surface it so the
    LLM doesn't silently treat CNY/JPY/EUR values as USD.
    """
    if not isinstance(result, dict):
        return None
    if result.get("Currency"):  # OVERVIEW
        return result["Currency"]
    for key in ("annualReports", "quarterlyReports"):
        reports = result.get(key) or []
        for r in reports:
            ccy = r.get("reportedCurrency")
            if ccy:
                return ccy
    return None


def _wrap_with_currency_header(result, ticker: str, label: str) -> str:
    """Serialize an Alpha Vantage response with a currency header on top.

    Returns the original payload unmodified when the upstream call failed
    (already a string, e.g. an error message) so callers see vendor errors
    verbatim rather than wrapped in misleading currency wording.
    """
    if not isinstance(result, dict):
        return result if isinstance(result, str) else str(result)
    ccy = _extract_reported_currency(result)
    header_lines = [f"# {label} for {ticker.upper()} (Alpha Vantage)"]
    if ccy:
        header_lines.append(
            f"# Reporting Currency: {ccy} (all absolute values below are in {ccy})"
        )
    header = "\n".join(header_lines) + "\n\n"
    return header + json.dumps(result, indent=2, default=str)


def get_fundamentals(ticker: str, curr_date: str = None) -> str:
    """Retrieve comprehensive fundamental data for a given ticker symbol using Alpha Vantage."""
    params = {"symbol": ticker}
    result = _make_api_request("OVERVIEW", params)
    return _wrap_with_currency_header(result, ticker, "Company Fundamentals")


def get_balance_sheet(ticker: str, freq: str = "quarterly", curr_date: str = None):
    """Retrieve balance sheet data for a given ticker symbol using Alpha Vantage."""
    result = _make_api_request("BALANCE_SHEET", {"symbol": ticker})
    result = _filter_reports_by_date(result, curr_date)
    return _wrap_with_currency_header(result, ticker, "Balance Sheet")


def get_cashflow(ticker: str, freq: str = "quarterly", curr_date: str = None):
    """Retrieve cash flow statement data for a given ticker symbol using Alpha Vantage."""
    result = _make_api_request("CASH_FLOW", {"symbol": ticker})
    result = _filter_reports_by_date(result, curr_date)
    return _wrap_with_currency_header(result, ticker, "Cash Flow Statement")


def get_income_statement(ticker: str, freq: str = "quarterly", curr_date: str = None):
    """Retrieve income statement data for a given ticker symbol using Alpha Vantage."""
    result = _make_api_request("INCOME_STATEMENT", {"symbol": ticker})
    result = _filter_reports_by_date(result, curr_date)
    return _wrap_with_currency_header(result, ticker, "Income Statement")
