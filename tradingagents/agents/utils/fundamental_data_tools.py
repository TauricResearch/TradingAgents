from langchain_core.tools import tool
from typing import Annotated
from tradingagents.dataflows.interface import route_to_vendor
from tradingagents.dataflows.ttm_analysis import compute_ttm_metrics, format_ttm_report
from tradingagents.dataflows.peer_comparison import get_peer_comparison_report, get_sector_relative_report
from tradingagents.dataflows.macro_regime import classify_macro_regime, format_macro_report


@tool
def get_fundamentals(
    ticker: Annotated[str, "ticker symbol"],
    curr_date: Annotated[str, "current date you are trading at, yyyy-mm-dd"],
) -> str:
    """
    Retrieve comprehensive fundamental data for a given ticker symbol.
    Uses the configured fundamental_data vendor.
    Args:
        ticker (str): Ticker symbol of the company
        curr_date (str): Current date you are trading at, yyyy-mm-dd
    Returns:
        str: A formatted report containing comprehensive fundamental data
    """
    return route_to_vendor("get_fundamentals", ticker, curr_date)


@tool
def get_balance_sheet(
    ticker: Annotated[str, "ticker symbol"],
    freq: Annotated[str, "reporting frequency: annual/quarterly"] = "quarterly",
    curr_date: Annotated[str, "current date you are trading at, yyyy-mm-dd"] = None,
) -> str:
    """
    Retrieve balance sheet data for a given ticker symbol.
    Uses the configured fundamental_data vendor.
    Args:
        ticker (str): Ticker symbol of the company
        freq (str): Reporting frequency: annual/quarterly (default quarterly)
        curr_date (str): Current date you are trading at, yyyy-mm-dd
    Returns:
        str: A formatted report containing balance sheet data
    """
    return route_to_vendor("get_balance_sheet", ticker, freq, curr_date)


@tool
def get_cashflow(
    ticker: Annotated[str, "ticker symbol"],
    freq: Annotated[str, "reporting frequency: annual/quarterly"] = "quarterly",
    curr_date: Annotated[str, "current date you are trading at, yyyy-mm-dd"] = None,
) -> str:
    """
    Retrieve cash flow statement data for a given ticker symbol.
    Uses the configured fundamental_data vendor.
    Args:
        ticker (str): Ticker symbol of the company
        freq (str): Reporting frequency: annual/quarterly (default quarterly)
        curr_date (str): Current date you are trading at, yyyy-mm-dd
    Returns:
        str: A formatted report containing cash flow statement data
    """
    return route_to_vendor("get_cashflow", ticker, freq, curr_date)


@tool
def get_income_statement(
    ticker: Annotated[str, "ticker symbol"],
    freq: Annotated[str, "reporting frequency: annual/quarterly"] = "quarterly",
    curr_date: Annotated[str, "current date you are trading at, yyyy-mm-dd"] = None,
) -> str:
    """
    Retrieve income statement data for a given ticker symbol.
    Uses the configured fundamental_data vendor.
    Args:
        ticker (str): Ticker symbol of the company
        freq (str): Reporting frequency: annual/quarterly (default quarterly)
        curr_date (str): Current date you are trading at, yyyy-mm-dd
    Returns:
        str: A formatted report containing income statement data
    """
    return route_to_vendor("get_income_statement", ticker, freq, curr_date)


@tool
def get_ttm_analysis(
    ticker: Annotated[str, "ticker symbol"],
    curr_date: Annotated[str, "current date you are trading at, yyyy-mm-dd"] = None,
) -> str:
    """
    Retrieve an 8-quarter Trailing Twelve Months (TTM) trend analysis for a company.
    Computes revenue growth (QoQ and YoY), margin trajectories (gross, operating, net),
    return on equity trend, debt/equity trend, and free cash flow trend across up to
    8 quarterly periods.
    Args:
        ticker (str): Ticker symbol of the company
        curr_date (str): Current date you are trading at, yyyy-mm-dd
    Returns:
        str: Formatted Markdown report with TTM summary and quarterly trend table
    """
    income_csv = route_to_vendor("get_income_statement", ticker, "quarterly", curr_date)
    balance_csv = route_to_vendor("get_balance_sheet", ticker, "quarterly", curr_date)
    cashflow_csv = route_to_vendor("get_cashflow", ticker, "quarterly", curr_date)
    metrics = compute_ttm_metrics(income_csv, balance_csv, cashflow_csv, n_quarters=8)
    return format_ttm_report(metrics, ticker)


@tool
def get_peer_comparison(
    ticker: Annotated[str, "ticker symbol"],
    curr_date: Annotated[str, "current date you are trading at, yyyy-mm-dd"] = None,
) -> str:
    """
    Compare a stock's performance vs its sector peers over 1-week, 1-month, 3-month,
    6-month and YTD periods. Returns a ranked table and alpha vs sector ETF.
    Args:
        ticker (str): Ticker symbol of the company
        curr_date (str): Current date you are trading at, yyyy-mm-dd
    Returns:
        str: Formatted Markdown report with peer ranking table
    """
    return get_peer_comparison_report(ticker, curr_date)


@tool
def get_sector_relative(
    ticker: Annotated[str, "ticker symbol"],
    curr_date: Annotated[str, "current date you are trading at, yyyy-mm-dd"] = None,
) -> str:
    """
    Compare a stock's return vs its sector ETF benchmark over multiple time horizons.
    Shows 1-week, 1-month, 3-month, 6-month, and YTD alpha.
    Args:
        ticker (str): Ticker symbol of the company
        curr_date (str): Current date you are trading at, yyyy-mm-dd
    Returns:
        str: Formatted Markdown report with outperformance/underperformance metrics
    """
    return get_sector_relative_report(ticker, curr_date)


@tool
def get_macro_regime(
    curr_date: Annotated[str, "current date you are trading at, yyyy-mm-dd"] = None,
) -> str:
    """
    Classify the current macro market regime as risk-on, risk-off, or transition.
    Uses 6 signals: VIX level, VIX trend, credit spread proxy (HYG/LQD),
    yield curve proxy (TLT/SHY), S&P 500 market breadth, and sector rotation
    (defensive vs cyclical). Returns a composite score and actionable interpretation.
    Args:
        curr_date (str): Current date you are trading at, yyyy-mm-dd (informational)
    Returns:
        str: Formatted Markdown report with regime classification and signal breakdown
    """
    regime_data = classify_macro_regime(curr_date)
    return format_macro_report(regime_data)