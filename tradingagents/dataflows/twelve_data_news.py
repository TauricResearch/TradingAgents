from .twelve_data_common import TwelveDataRateLimitError


def get_news(ticker: str, start_date: str, end_date: str) -> str:
    """Twelve Data does not provide a news endpoint.
    Raise rate limit error to trigger fallback to next vendor."""
    raise TwelveDataRateLimitError(
        "Twelve Data does not provide a news endpoint. Falling back to next vendor."
    )


def get_global_news(curr_date: str, look_back_days: int = 7, limit: int = 50) -> str:
    """Twelve Data does not provide a global news endpoint.
    Raise rate limit error to trigger fallback to next vendor."""
    raise TwelveDataRateLimitError(
        "Twelve Data does not provide a global news endpoint. Falling back to next vendor."
    )


def get_insider_transactions(symbol: str) -> str:
    """Twelve Data does not provide insider transaction data.
    Raise rate limit error to trigger fallback to next vendor."""
    raise TwelveDataRateLimitError(
        "Twelve Data does not provide insider transactions. Falling back to next vendor."
    )
