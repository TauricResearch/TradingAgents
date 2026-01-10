from langchain_core.tools import tool
from typing import Annotated
from tradingagents.dataflows.interface import route_to_vendor
from tradingagents.utils.anonymizer import TickerAnonymizer

@tool
def get_stock_data(
    symbol: Annotated[str, "ticker symbol of the company"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
    format: Annotated[str, "Output format 'csv' or 'string' (default: 'string')"] = "string"
) -> str:
    """
    Retrieve stock price data (OHLCV) for a given ticker symbol.
    Uses the configured core_stock_apis vendor.
    Args:
        symbol (str): Ticker symbol of the company, e.g. AAPL, TSM
        start_date (str): Start date in yyyy-mm-dd format
        end_date (str): End date in yyyy-mm-dd format
        format (str): 'csv' or 'string'
    Returns:
        str: A formatted dataframe containing the stock price data for the specified ticker symbol in the specified date range.
    """
    # Initialize anonymizer locally to ensure fresh state loading
    anonymizer = TickerAnonymizer()
    
    # 1. Deanonymize ticker (ASSET_XXX -> AAPL)
    real_ticker = anonymizer.deanonymize_ticker(symbol)
    if not real_ticker:
        real_ticker = symbol  # Fallback if not anonymized

    # 2. Get Data using Real Ticker
    raw_data = route_to_vendor("get_stock_data", real_ticker, start_date, end_date, format=format)

    # 3. Anonymize Output (AAPL -> ASSET_XXX)
    anonymized_data = anonymizer.anonymize_text(raw_data, real_ticker)
    
    return anonymized_data
