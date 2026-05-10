import pandas as pd
from io import StringIO

from .twelve_data_common import _make_api_request, _filter_csv_by_date_range


def get_stock(symbol: str, start_date: str, end_date: str) -> str:
    """Retrieve daily OHLCV stock data from Twelve Data.

    Args:
        symbol: Stock ticker symbol
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)

    Returns:
        CSV string with stock data
    """
    params = {
        "symbol": symbol,
        "interval": "1day",
        "start_date": start_date,
        "end_date": end_date,
        "outputsize": 5000,
    }

    data = _make_api_request("time_series", params)

    if not data.get("values"):
        return f"# No stock data available for {symbol}"

    # Convert to DataFrame for CSV output
    df = pd.DataFrame(data["values"])
    df = df.rename(columns={"datetime": "time"})
    # Reorder columns to match expected format
    cols = ["time", "open", "high", "low", "close", "volume"]
    df = df[[c for c in cols if c in df.columns]]
    df = df.sort_values("time")

    header = f"# Stock data for {symbol.upper()} from {start_date} to {end_date}\n"
    return header + df.to_csv(index=False)
