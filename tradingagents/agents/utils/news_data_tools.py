from langchain_core.tools import tool
from typing import Annotated
from tradingagents.dataflows.interface import route_to_vendor
from tradingagents.utils.anonymizer import TickerAnonymizer

def _process_vendor_call(func_name, ticker=None, *args):
    """Helper to handle anonymization for vendor calls"""
    try:
        # Initialize locally to ensure fresh state
        anonymizer = TickerAnonymizer()
        
        real_ticker = None
        if ticker:
            # 1. Deanonymize ticker
            real_ticker = anonymizer.deanonymize_ticker(ticker)
            if not real_ticker:
                real_ticker = ticker
                
        # 2. Get Data
        # Handle optional ticker for global_news
        call_args = [real_ticker] + list(args) if ticker else list(args)
        raw_data = route_to_vendor(func_name, *call_args)
        
        # 3. Anonymize Output
        return anonymizer.anonymize_text(raw_data, real_ticker) if real_ticker else raw_data
    except Exception as e:
        return f"Error executing tool {func_name}: {str(e)}"

@tool
def get_news(
    ticker: Annotated[str, "Ticker symbol"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
) -> str:
    """
    Retrieve news data for a given ticker symbol.
    Uses the configured news_data vendor.
    Args:
        ticker (str): Ticker symbol
        start_date (str): Start date in yyyy-mm-dd format
        end_date (str): End date in yyyy-mm-dd format
    Returns:
        str: A formatted string containing news data
    """
    return _process_vendor_call("get_news", ticker, start_date, end_date)

@tool
def get_global_news(
    curr_date: Annotated[str, "Current date in yyyy-mm-dd format"],
    look_back_days: Annotated[int, "Number of days to look back"] = 7,
    limit: Annotated[int, "Maximum number of articles to return"] = 5,
) -> str:
    """
    Retrieve global news data.
    Uses the configured news_data vendor.
    Args:
        curr_date (str): Current date in yyyy-mm-dd format
        look_back_days (int): Number of days to look back (default 7)
        limit (int): Maximum number of articles to return (default 5)
    Returns:
        str: A formatted string containing global news data
    """
    # Global news doesn't take a ticker as input, so pass None as ticker
    # We rely on the vendor call just taking args.
    # Note: route_to_vendor expects func_name, *args.
    # Our helper expects func_name, ticker, *args.
    # So we call route_to_vendor directly here but still might want to anonymize output?
    # Global news might mention "Apple". If we are analyzing "ASSET_042" (Apple), we typically want to mask it.
    # But without a specific target ticker in context, it's hard.
    # For now, let's just return raw global news or we'd need to mask ALL known mapped tickers.
    # The current Anonymizer is context-aware (one ticker).
    # Ideally, get_global_news should probably stay raw or be masked for the 'current company of interest' 
    # but tools don't know the agent's context unless passed.
    # Leaving global news RAW for now as it provides macro context.
    # However, for now we pass real_ticker if available.
    # Leaving global news RAW for now as it provides macro context.
    try:
        return route_to_vendor("get_global_news", curr_date, look_back_days, limit)
    except Exception as e:
        return f"Error executing tool get_global_news: {str(e)}"

@tool
def get_insider_sentiment(
    ticker: Annotated[str, "ticker symbol for the company"],
    curr_date: Annotated[str, "current date you are trading at, yyyy-mm-dd"],
) -> str:
    """
    Retrieve insider sentiment information about a company.
    Uses the configured news_data vendor.
    Args:
        ticker (str): Ticker symbol of the company
        curr_date (str): Current date in yyyy-mm-dd format
    Returns:
        str: A report of insider sentiment data
    """
    return _process_vendor_call("get_insider_sentiment", ticker, curr_date)

@tool
def get_insider_transactions(
    ticker: Annotated[str, "ticker symbol"],
    curr_date: Annotated[str, "current date you are trading at, yyyy-mm-dd"],
) -> str:
    """
    Retrieve insider transaction information about a company.
    Uses the configured news_data vendor.
    Args:
        ticker (str): Ticker symbol of the company
        curr_date (str): Current date in yyyy-mm-dd format
    Returns:
        str: A report of insider transaction data
    """
    return _process_vendor_call("get_insider_transactions", ticker, curr_date)
