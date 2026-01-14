from langchain_core.tools import tool
from typing import Annotated
from tradingagents.dataflows.interface import route_to_vendor
from tradingagents.utils.anonymizer import TickerAnonymizer

@tool
def get_indicators(
    symbol: Annotated[str, "ticker symbol of the company"],
    indicator: Annotated[str, "technical indicator to get the analysis and report of"],
    curr_date: Annotated[str, "The current trading date you are trading on, YYYY-mm-dd"],
    look_back_days: Annotated[int, "how many days to look back"] = 30,
) -> str:
    """
    Retrieve technical indicators for a given ticker symbol.
    Uses the configured technical_indicators vendor.
    Args:
        symbol (str): Ticker symbol of the company, e.g. AAPL, TSM
        indicator (str): Technical indicator to get the analysis and report of
        curr_date (str): The current trading date you are trading on, YYYY-mm-dd
        look_back_days (int): How many days to look back, default is 30
    Returns:
        str: A formatted dataframe containing the technical indicators for the specified ticker symbol and indicator.
    """
    # Initialize anonymizer locally to ensure fresh state loading
    anonymizer = TickerAnonymizer()

    # 1. Deanonymize ticker
    real_ticker = anonymizer.deanonymize_ticker(symbol)
    if not real_ticker:
        real_ticker = symbol

    
    try:
        # 2. Get Data
        raw_data = route_to_vendor("get_indicators", real_ticker, indicator, curr_date, look_back_days)

        # 3. Anonymize Output
        anonymized_data = anonymizer.anonymize_text(raw_data, real_ticker)
        
        return anonymized_data
    except Exception as e:
        return f"Error executing tool get_indicators: {str(e)}"
    
    return anonymized_data