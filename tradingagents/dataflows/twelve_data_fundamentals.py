import json

from .twelve_data_common import _make_api_request


def get_fundamentals(ticker: str, curr_date: str = None) -> str:
    """Retrieve company overview/profile from Twelve Data."""
    data = _make_api_request("profile", {"symbol": ticker})
    return json.dumps(data, indent=2)


def get_balance_sheet(ticker: str, freq: str = "quarterly", curr_date: str = None) -> str:
    """Retrieve balance sheet data from Twelve Data."""
    period = "quarterly" if freq == "quarterly" else "annual"
    data = _make_api_request("balance_sheet", {"symbol": ticker, "period": period})
    data = _filter_statements_by_date(data, curr_date)
    return json.dumps(data, indent=2)


def get_cashflow(ticker: str, freq: str = "quarterly", curr_date: str = None) -> str:
    """Retrieve cash flow data from Twelve Data."""
    period = "quarterly" if freq == "quarterly" else "annual"
    data = _make_api_request("cash_flow", {"symbol": ticker, "period": period})
    data = _filter_statements_by_date(data, curr_date)
    return json.dumps(data, indent=2)


def get_income_statement(ticker: str, freq: str = "quarterly", curr_date: str = None) -> str:
    """Retrieve income statement data from Twelve Data."""
    period = "quarterly" if freq == "quarterly" else "annual"
    data = _make_api_request("income_statement", {"symbol": ticker, "period": period})
    data = _filter_statements_by_date(data, curr_date)
    return json.dumps(data, indent=2)


def _filter_statements_by_date(result: dict, curr_date: str) -> dict:
    """Filter financial statements to exclude future-dated entries."""
    if not curr_date or not isinstance(result, (dict, list)):
        return result
    for key in ("statements", "balance_sheet", "cash_flow", "income_statement"):
        if key in result and isinstance(result[key], list):
            result[key] = [
                s for s in result[key]
                if s.get("fiscal_date_ending", s.get("date", "")) <= curr_date
            ]
    # Also check if result itself is a list of statements
    if isinstance(result, list):
        result = [
            s for s in result
            if isinstance(s, dict) and s.get("fiscal_date_ending", s.get("date", "")) <= curr_date
        ]
    return result
