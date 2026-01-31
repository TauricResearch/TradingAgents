"""
Market configuration and stock lists for different markets.
Supports US and Indian NSE (Nifty 50) stocks.
"""

from enum import Enum
from typing import Optional


class Market(Enum):
    """Supported markets."""
    US = "us"
    INDIA_NSE = "india_nse"


# Nifty 50 stocks with company names
NIFTY_50_STOCKS = {
    "RELIANCE": "Reliance Industries Ltd",
    "TCS": "Tata Consultancy Services Ltd",
    "HDFCBANK": "HDFC Bank Ltd",
    "INFY": "Infosys Ltd",
    "ICICIBANK": "ICICI Bank Ltd",
    "HINDUNILVR": "Hindustan Unilever Ltd",
    "ITC": "ITC Ltd",
    "SBIN": "State Bank of India",
    "BHARTIARTL": "Bharti Airtel Ltd",
    "KOTAKBANK": "Kotak Mahindra Bank Ltd",
    "LT": "Larsen & Toubro Ltd",
    "AXISBANK": "Axis Bank Ltd",
    "ASIANPAINT": "Asian Paints Ltd",
    "MARUTI": "Maruti Suzuki India Ltd",
    "HCLTECH": "HCL Technologies Ltd",
    "SUNPHARMA": "Sun Pharmaceutical Industries Ltd",
    "TITAN": "Titan Company Ltd",
    "BAJFINANCE": "Bajaj Finance Ltd",
    "WIPRO": "Wipro Ltd",
    "ULTRACEMCO": "UltraTech Cement Ltd",
    "NESTLEIND": "Nestle India Ltd",
    "NTPC": "NTPC Ltd",
    "POWERGRID": "Power Grid Corporation of India Ltd",
    "M&M": "Mahindra & Mahindra Ltd",
    "TATAMOTORS": "Tata Motors Ltd",
    "ONGC": "Oil & Natural Gas Corporation Ltd",
    "JSWSTEEL": "JSW Steel Ltd",
    "TATASTEEL": "Tata Steel Ltd",
    "ADANIENT": "Adani Enterprises Ltd",
    "ADANIPORTS": "Adani Ports and SEZ Ltd",
    "COALINDIA": "Coal India Ltd",
    "BAJAJFINSV": "Bajaj Finserv Ltd",
    "TECHM": "Tech Mahindra Ltd",
    "HDFCLIFE": "HDFC Life Insurance Company Ltd",
    "SBILIFE": "SBI Life Insurance Company Ltd",
    "GRASIM": "Grasim Industries Ltd",
    "DIVISLAB": "Divi's Laboratories Ltd",
    "DRREDDY": "Dr. Reddy's Laboratories Ltd",
    "CIPLA": "Cipla Ltd",
    "BRITANNIA": "Britannia Industries Ltd",
    "EICHERMOT": "Eicher Motors Ltd",
    "APOLLOHOSP": "Apollo Hospitals Enterprise Ltd",
    "INDUSINDBK": "IndusInd Bank Ltd",
    "HEROMOTOCO": "Hero MotoCorp Ltd",
    "TATACONSUM": "Tata Consumer Products Ltd",
    "BPCL": "Bharat Petroleum Corporation Ltd",
    "UPL": "UPL Ltd",
    "HINDALCO": "Hindalco Industries Ltd",
    "BAJAJ-AUTO": "Bajaj Auto Ltd",
    "LTIM": "LTIMindtree Ltd",
}


def is_nifty_50_stock(symbol: str) -> bool:
    """
    Check if a symbol is a Nifty 50 stock.

    Args:
        symbol: Stock symbol (with or without .NS suffix)

    Returns:
        True if the symbol is in the Nifty 50 list
    """
    # Remove .NS suffix if present
    clean_symbol = symbol.upper().replace(".NS", "")
    return clean_symbol in NIFTY_50_STOCKS


def get_nifty_50_company_name(symbol: str) -> Optional[str]:
    """
    Get the company name for a Nifty 50 stock symbol.

    Args:
        symbol: Stock symbol (with or without .NS suffix)

    Returns:
        Company name if found, None otherwise
    """
    clean_symbol = symbol.upper().replace(".NS", "")
    return NIFTY_50_STOCKS.get(clean_symbol)


def detect_market(symbol: str, config_market: str = "auto") -> Market:
    """
    Detect the market for a given symbol.

    Args:
        symbol: Stock symbol
        config_market: Market setting from config ("auto", "us", "india_nse")

    Returns:
        Market enum indicating the detected market
    """
    if config_market == "india_nse":
        return Market.INDIA_NSE
    elif config_market == "us":
        return Market.US

    # Auto-detection
    # Check if symbol has .NS suffix (yfinance format for NSE)
    if symbol.upper().endswith(".NS"):
        return Market.INDIA_NSE

    # Check if symbol is in Nifty 50 list
    if is_nifty_50_stock(symbol):
        return Market.INDIA_NSE

    # Default to US market
    return Market.US


def normalize_symbol(symbol: str, target: str = "yfinance") -> str:
    """
    Normalize a symbol for a specific data source.

    Args:
        symbol: Stock symbol
        target: Target format ("yfinance", "jugaad", "nse")

    Returns:
        Normalized symbol for the target
    """
    clean_symbol = symbol.upper().replace(".NS", "")

    if target == "yfinance":
        # yfinance requires .NS suffix for NSE stocks
        if is_nifty_50_stock(clean_symbol):
            return f"{clean_symbol}.NS"
        return clean_symbol

    elif target in ("jugaad", "nse"):
        # jugaad-data and NSE use symbols without suffix
        return clean_symbol

    return symbol.upper()


def get_nifty_50_list() -> list:
    """
    Get list of all Nifty 50 stock symbols.

    Returns:
        List of Nifty 50 stock symbols
    """
    return list(NIFTY_50_STOCKS.keys())


def get_nifty_50_with_names() -> dict:
    """
    Get dictionary of Nifty 50 stocks with company names.

    Returns:
        Dictionary mapping symbols to company names
    """
    return NIFTY_50_STOCKS.copy()
