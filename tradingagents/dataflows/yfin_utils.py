# gets data/stats

from collections.abc import Callable
from functools import wraps
from typing import Annotated, Any

import pandas as pd
import yfinance as yf
from pandas import DataFrame

from .utils import SavePathType, decorate_all_methods


def init_ticker(func: Callable) -> Callable:
    """Decorator to initialize yf.Ticker and pass it to the function."""

    @wraps(func)
    def wrapper(symbol: Annotated[str, "ticker symbol"], *args, **kwargs) -> Any:
        ticker = yf.Ticker(symbol)
        return func(ticker, *args, **kwargs)

    return wrapper


@decorate_all_methods(init_ticker)
class YFinanceUtils:

    def get_stock_data(
        self: Annotated[str, "ticker symbol"],
        start_date: Annotated[
            str,
            "start date for retrieving stock price data, YYYY-mm-dd",
        ],
        end_date: Annotated[
            str,
            "end date for retrieving stock price data, YYYY-mm-dd",
        ],
        save_path: SavePathType = None,
    ) -> DataFrame:
        """retrieve stock price data for designated ticker symbol"""
        ticker = self
        # add one day to the end_date so that the data range is inclusive
        end_date = pd.to_datetime(end_date) + pd.DateOffset(days=1)
        end_date = end_date.strftime("%Y-%m-%d")
        return ticker.history(start=start_date, end=end_date)
        # save_output(stock_data, f"Stock data for {ticker.ticker}", save_path)

    def get_stock_info(
        self: Annotated[str, "ticker symbol"],
    ) -> dict:
        """Fetches and returns latest stock information."""
        ticker = self
        return ticker.info

    def get_company_info(
        self: Annotated[str, "ticker symbol"],
        save_path: str | None = None,
    ) -> DataFrame:
        """Fetches and returns company information as a DataFrame."""
        ticker = self
        info = ticker.info
        company_info = {
            "Company Name": info.get("shortName", "N/A"),
            "Industry": info.get("industry", "N/A"),
            "Sector": info.get("sector", "N/A"),
            "Country": info.get("country", "N/A"),
            "Website": info.get("website", "N/A"),
        }
        company_info_df = DataFrame([company_info])
        if save_path:
            company_info_df.to_csv(save_path)
        return company_info_df

    def get_stock_dividends(
        self: Annotated[str, "ticker symbol"],
        save_path: str | None = None,
    ) -> DataFrame:
        """Fetches and returns the latest dividends data as a DataFrame."""
        ticker = self
        dividends = ticker.dividends
        if save_path:
            dividends.to_csv(save_path)
        return dividends

    def get_income_stmt(self: Annotated[str, "ticker symbol"]) -> DataFrame:
        """Fetches and returns the latest income statement of the company as a DataFrame."""
        ticker = self
        return ticker.financials

    def get_balance_sheet(self: Annotated[str, "ticker symbol"]) -> DataFrame:
        """Fetches and returns the latest balance sheet of the company as a DataFrame."""
        ticker = self
        return ticker.balance_sheet

    def get_cash_flow(self: Annotated[str, "ticker symbol"]) -> DataFrame:
        """Fetches and returns the latest cash flow statement of the company as a DataFrame."""
        ticker = self
        return ticker.cashflow

    def get_analyst_recommendations(self: Annotated[str, "ticker symbol"]) -> tuple:
        """Fetches the latest analyst recommendations and returns the most common recommendation and its count."""
        ticker = self
        recommendations = ticker.recommendations
        if recommendations.empty:
            return None, 0  # No recommendations available

        # Assuming 'period' column exists and needs to be excluded
        row_0 = recommendations.iloc[0, 1:]  # Exclude 'period' column if necessary

        # Find the maximum voting result
        max_votes = row_0.max()
        majority_voting_result = row_0[row_0 == max_votes].index.tolist()

        return majority_voting_result[0], max_votes
