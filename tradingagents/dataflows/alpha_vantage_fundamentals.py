from datetime import datetime, timedelta
from .alpha_vantage_common import _make_api_request
import json


def _filter_reports_by_date(data_str: str, curr_date: str, report_keys: list = None) -> str:
    """
    Filter Alpha Vantage fundamentals data to only include reports available as of curr_date.
    This ensures point-in-time accuracy for backtesting.

    Financial reports are typically published ~45 days after the fiscal date ending.
    We filter to only include reports that would have been published by curr_date.

    Args:
        data_str: JSON string from Alpha Vantage API
        curr_date: The backtest date in yyyy-mm-dd format
        report_keys: List of keys containing report arrays (e.g., ['quarterlyReports', 'annualReports'])

    Returns:
        Filtered JSON string with only point-in-time available reports
    """
    if curr_date is None:
        return data_str

    if report_keys is None:
        report_keys = ['quarterlyReports', 'annualReports']

    try:
        data = json.loads(data_str)
        curr_date_dt = datetime.strptime(curr_date, "%Y-%m-%d")
        # Financial reports typically published ~45 days after fiscal date ending
        publication_delay_days = 45

        for key in report_keys:
            if key in data and isinstance(data[key], list):
                filtered_reports = []
                for report in data[key]:
                    fiscal_date = report.get('fiscalDateEnding')
                    if fiscal_date:
                        try:
                            fiscal_date_dt = datetime.strptime(fiscal_date, "%Y-%m-%d")
                            # Estimate when this report would have been published
                            estimated_publish_date = fiscal_date_dt + timedelta(days=publication_delay_days)
                            if estimated_publish_date <= curr_date_dt:
                                filtered_reports.append(report)
                        except ValueError:
                            # If date parsing fails, keep the report
                            filtered_reports.append(report)
                    else:
                        # If no fiscal date, keep the report
                        filtered_reports.append(report)
                data[key] = filtered_reports

        # Add point-in-time metadata
        data['_point_in_time_date'] = curr_date
        data['_filtered_for_backtesting'] = True

        return json.dumps(data, indent=2)

    except (json.JSONDecodeError, Exception) as e:
        # If parsing fails, return original data with warning
        print(f"Warning: Could not filter Alpha Vantage data by date: {e}")
        return data_str


def get_fundamentals(ticker: str, curr_date: str = None) -> str:
    """
    Retrieve comprehensive fundamental data for a given ticker symbol using Alpha Vantage.

    Note: OVERVIEW endpoint returns current snapshot data only. For backtesting,
    this may not reflect the exact fundamentals as of the historical date.

    Args:
        ticker (str): Ticker symbol of the company
        curr_date (str): Current date you are trading at, yyyy-mm-dd (used for documentation)

    Returns:
        str: Company overview data including financial ratios and key metrics
    """
    params = {
        "symbol": ticker,
    }

    result = _make_api_request("OVERVIEW", params)

    # Add warning about point-in-time accuracy for OVERVIEW data
    if curr_date and result and not result.startswith("Error"):
        try:
            data = json.loads(result)
            data['_warning'] = (
                "OVERVIEW data is current snapshot only. For accurate backtesting, "
                "fundamental ratios may differ from actual values as of " + curr_date
            )
            data['_requested_date'] = curr_date
            return json.dumps(data, indent=2)
        except:
            pass

    return result


def get_balance_sheet(ticker: str, freq: str = "quarterly", curr_date: str = None) -> str:
    """
    Retrieve balance sheet data for a given ticker symbol using Alpha Vantage.
    Filtered by curr_date for point-in-time backtesting accuracy.

    Args:
        ticker (str): Ticker symbol of the company
        freq (str): Reporting frequency: annual/quarterly (default quarterly)
        curr_date (str): Current date you are trading at, yyyy-mm-dd (used for point-in-time filtering)

    Returns:
        str: Balance sheet data with normalized fields, filtered to only include
             reports that would have been published by curr_date
    """
    params = {
        "symbol": ticker,
    }

    result = _make_api_request("BALANCE_SHEET", params)

    # Filter reports to only include those available as of curr_date
    return _filter_reports_by_date(result, curr_date)


def get_cashflow(ticker: str, freq: str = "quarterly", curr_date: str = None) -> str:
    """
    Retrieve cash flow statement data for a given ticker symbol using Alpha Vantage.
    Filtered by curr_date for point-in-time backtesting accuracy.

    Args:
        ticker (str): Ticker symbol of the company
        freq (str): Reporting frequency: annual/quarterly (default quarterly)
        curr_date (str): Current date you are trading at, yyyy-mm-dd (used for point-in-time filtering)

    Returns:
        str: Cash flow statement data with normalized fields, filtered to only include
             reports that would have been published by curr_date
    """
    params = {
        "symbol": ticker,
    }

    result = _make_api_request("CASH_FLOW", params)

    # Filter reports to only include those available as of curr_date
    return _filter_reports_by_date(result, curr_date)


def get_income_statement(ticker: str, freq: str = "quarterly", curr_date: str = None) -> str:
    """
    Retrieve income statement data for a given ticker symbol using Alpha Vantage.
    Filtered by curr_date for point-in-time backtesting accuracy.

    Args:
        ticker (str): Ticker symbol of the company
        freq (str): Reporting frequency: annual/quarterly (default quarterly)
        curr_date (str): Current date you are trading at, yyyy-mm-dd (used for point-in-time filtering)

    Returns:
        str: Income statement data with normalized fields, filtered to only include
             reports that would have been published by curr_date
    """
    params = {
        "symbol": ticker,
    }

    result = _make_api_request("INCOME_STATEMENT", params)

    # Filter reports to only include those available as of curr_date
    return _filter_reports_by_date(result, curr_date)
