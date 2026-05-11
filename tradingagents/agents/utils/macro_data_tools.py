from langchain_core.tools import tool
from typing import Annotated, Optional
from tradingagents.dataflows.interface import route_to_vendor

@tool
def get_macro_data(
    series_id: Annotated[str, "FRED series ID (e.g., 'GDP', 'FEDFUNDS', 'CPIAUCSL', 'UNRATE')"],
    start_date: Annotated[Optional[str], "Start date in YYYY-MM-DD format"] = None,
    end_date: Annotated[Optional[str], "End date in YYYY-MM-DD format"] = None,
    limit: Annotated[int, "Maximum number of observations to retrieve (latest first)"] = 24
) -> str:
    """
    Retrieve macroeconomic indicators from the Federal Reserve Economic Data (FRED).
    Useful for gathering data on inflation, interest rates, GDP, unemployment, and other macro factors.
    
    Args:
        series_id (str): The specific FRED series ID to query. Common IDs include:
            - GDP: Gross Domestic Product
            - FEDFUNDS: Federal Funds Effective Rate
            - CPIAUCSL: Consumer Price Index (Inflation)
            - UNRATE: Unemployment Rate
        start_date (str, optional): Start date for data (YYYY-MM-DD).
        end_date (str, optional): End date for data (YYYY-MM-DD).
        limit (int): Maximum number of entries to return (default 24).
    Returns:
        str: A formatted string containing the chronological macro data observations.
    """
    return route_to_vendor("get_macro_data", series_id, start_date, end_date, limit)
