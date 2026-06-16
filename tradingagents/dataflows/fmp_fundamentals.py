from .fmp_common import make_request
from .vendor_utils import format_json_section


def get_fundamentals(ticker: str, curr_date: str = None) -> str:
    profile = make_request("profile", {"symbol": ticker})
    metrics = make_request("key-metrics-ttm", {"symbol": ticker})
    ratios = make_request("ratios-ttm", {"symbol": ticker})
    return "\n\n".join(
        [
            format_json_section("FMP Company Profile", profile),
            format_json_section("FMP TTM Key Metrics", metrics),
            format_json_section("FMP TTM Ratios", ratios),
        ]
    )


def _statement(endpoint: str, ticker: str, freq: str, curr_date: str = None):
    period = "annual" if freq == "annual" else "quarter"
    return make_request(endpoint, {"symbol": ticker, "period": period, "limit": 8})


def get_balance_sheet(ticker: str, freq: str = "quarterly", curr_date: str = None):
    return _statement("balance-sheet-statement", ticker, freq, curr_date)


def get_cashflow(ticker: str, freq: str = "quarterly", curr_date: str = None):
    return _statement("cash-flow-statement", ticker, freq, curr_date)


def get_income_statement(ticker: str, freq: str = "quarterly", curr_date: str = None):
    return _statement("income-statement", ticker, freq, curr_date)
