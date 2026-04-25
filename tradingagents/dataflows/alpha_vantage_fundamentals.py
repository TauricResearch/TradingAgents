from .alpha_vantage_common import _make_api_request

_CRYPTO_QUOTE_SUFFIXES = ("USDT", "USDC", "BUSD", "FDUSD", "TUSD", "BTC", "ETH", "BNB")

_CRYPTO_NOT_AVAILABLE = (
    "Fundamental data is not available for crypto assets ({ticker}). "
    "Cryptocurrencies do not have company fundamentals such as "
    "earnings, balance sheets, or income statements."
)


def _is_crypto(ticker: str) -> bool:
    t = ticker.upper()
    return "." not in t and any(t.endswith(s) for s in _CRYPTO_QUOTE_SUFFIXES)


def get_fundamentals(ticker: str, curr_date: str = None) -> str:
    """Retrieve comprehensive fundamental data for a given ticker symbol using Alpha Vantage."""
    if _is_crypto(ticker):
        return _CRYPTO_NOT_AVAILABLE.format(ticker=ticker)
    return _make_api_request("OVERVIEW", {"symbol": ticker})


def get_balance_sheet(ticker: str, freq: str = "quarterly", curr_date: str = None) -> str:
    """Retrieve balance sheet data for a given ticker symbol using Alpha Vantage."""
    if _is_crypto(ticker):
        return f"Balance sheet data is not available for crypto assets ({ticker})."
    return _make_api_request("BALANCE_SHEET", {"symbol": ticker})


def get_cashflow(ticker: str, freq: str = "quarterly", curr_date: str = None) -> str:
    """Retrieve cash flow statement data for a given ticker symbol using Alpha Vantage."""
    if _is_crypto(ticker):
        return f"Cash flow data is not available for crypto assets ({ticker})."
    return _make_api_request("CASH_FLOW", {"symbol": ticker})


def get_income_statement(ticker: str, freq: str = "quarterly", curr_date: str = None) -> str:
    """Retrieve income statement data for a given ticker symbol using Alpha Vantage."""
    if _is_crypto(ticker):
        return f"Income statement data is not available for crypto assets ({ticker})."
    return _make_api_request("INCOME_STATEMENT", {"symbol": ticker})
