"""
Data vendor using jugaad-data library for Indian NSE stocks.
Provides historical OHLCV data, live quotes, and index data for NSE.

Note: jugaad-data requires network access to NSE India website which may be
slow or blocked from some locations. The implementation includes timeouts
and will raise exceptions to trigger fallback to yfinance.
"""

from typing import Annotated
from datetime import datetime, date
import pandas as pd
import signal

from .markets import normalize_symbol, is_nifty_50_stock


class JugaadDataTimeoutError(Exception):
    """Raised when jugaad-data request times out."""
    pass


def _timeout_handler(signum, frame):
    raise JugaadDataTimeoutError("jugaad-data request timed out")


def get_jugaad_stock_data(
    symbol: Annotated[str, "ticker symbol of the company"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
) -> str:
    """
    Fetch historical stock data from NSE using jugaad-data.

    Args:
        symbol: NSE stock symbol (e.g., 'RELIANCE', 'TCS')
        start_date: Start date in yyyy-mm-dd format
        end_date: End date in yyyy-mm-dd format

    Returns:
        CSV formatted string with OHLCV data

    Raises:
        ImportError: If jugaad-data is not installed
        JugaadDataTimeoutError: If request times out
        Exception: For other errors (triggers fallback)
    """
    try:
        from jugaad_data.nse import stock_df
    except ImportError:
        raise ImportError("jugaad-data library not installed. Please install it with: pip install jugaad-data")

    # Normalize symbol for NSE (remove .NS suffix if present)
    nse_symbol = normalize_symbol(symbol, target="nse")

    # Parse dates
    try:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
        end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
    except ValueError as e:
        raise ValueError(f"Error parsing dates: {e}. Please use yyyy-mm-dd format.")

    # Set a timeout for the request (15 seconds)
    # This helps avoid hanging when NSE website is slow
    timeout_seconds = 15
    old_handler = None

    try:
        # Set timeout using signal (only works on Unix)
        try:
            old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
            signal.alarm(timeout_seconds)
        except (AttributeError, ValueError):
            # signal.SIGALRM not available on Windows
            pass

        # Fetch data using jugaad-data
        # series='EQ' for equity stocks
        data = stock_df(
            symbol=nse_symbol,
            from_date=start_dt,
            to_date=end_dt,
            series="EQ"
        )

        # Cancel the alarm
        try:
            signal.alarm(0)
            if old_handler:
                signal.signal(signal.SIGALRM, old_handler)
        except (AttributeError, ValueError):
            pass

        if data.empty:
            raise ValueError(f"No data found for symbol '{nse_symbol}' between {start_date} and {end_date}")

        # Rename columns to match yfinance format for consistency
        column_mapping = {
            "DATE": "Date",
            "OPEN": "Open",
            "HIGH": "High",
            "LOW": "Low",
            "CLOSE": "Close",
            "LTP": "Last",
            "VOLUME": "Volume",
            "VALUE": "Value",
            "NO OF TRADES": "Trades",
            "PREV. CLOSE": "Prev Close",
        }

        # Rename columns that exist
        for old_name, new_name in column_mapping.items():
            if old_name in data.columns:
                data = data.rename(columns={old_name: new_name})

        # Select relevant columns (similar to yfinance output)
        available_cols = ["Date", "Open", "High", "Low", "Close", "Volume"]
        cols_to_use = [col for col in available_cols if col in data.columns]
        data = data[cols_to_use]

        # Round numerical values
        numeric_columns = ["Open", "High", "Low", "Close"]
        for col in numeric_columns:
            if col in data.columns:
                data[col] = data[col].round(2)

        # Sort by date
        if "Date" in data.columns:
            data = data.sort_values("Date")

        # Convert to CSV string
        csv_string = data.to_csv(index=False)

        # Add header information
        header = f"# Stock data for {nse_symbol} (NSE) from {start_date} to {end_date}\n"
        header += f"# Total records: {len(data)}\n"
        header += f"# Data source: NSE India via jugaad-data\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

        return header + csv_string

    except JugaadDataTimeoutError:
        # Re-raise timeout errors to trigger fallback
        raise
    except Exception as e:
        error_msg = str(e)
        # Raise exceptions to trigger fallback to yfinance
        if "No data" in error_msg or "empty" in error_msg.lower():
            raise ValueError(f"No data found for symbol '{nse_symbol}' between {start_date} and {end_date}. Please verify the symbol is listed on NSE.")
        raise RuntimeError(f"Error fetching data for {nse_symbol} from jugaad-data: {error_msg}")


def get_jugaad_live_quote(
    symbol: Annotated[str, "ticker symbol of the company"],
) -> str:
    """
    Fetch live quote for an NSE stock.

    Args:
        symbol: NSE stock symbol

    Returns:
        Formatted string with current quote information
    """
    try:
        from jugaad_data.nse import NSELive
    except ImportError:
        return "Error: jugaad-data library not installed. Please install it with: pip install jugaad-data"

    nse_symbol = normalize_symbol(symbol, target="nse")

    try:
        nse = NSELive()
        quote = nse.stock_quote(nse_symbol)

        if not quote:
            return f"No live quote available for '{nse_symbol}'"

        # Extract price info
        price_info = quote.get("priceInfo", {})
        trade_info = quote.get("tradeInfo", {})
        security_info = quote.get("securityInfo", {})

        result = f"# Live Quote for {nse_symbol} (NSE)\n"
        result += f"# Retrieved: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

        result += f"Last Price: {price_info.get('lastPrice', 'N/A')}\n"
        result += f"Change: {price_info.get('change', 'N/A')}\n"
        result += f"% Change: {price_info.get('pChange', 'N/A')}%\n"
        result += f"Open: {price_info.get('open', 'N/A')}\n"
        result += f"High: {price_info.get('intraDayHighLow', {}).get('max', 'N/A')}\n"
        result += f"Low: {price_info.get('intraDayHighLow', {}).get('min', 'N/A')}\n"
        result += f"Previous Close: {price_info.get('previousClose', 'N/A')}\n"
        result += f"Volume: {trade_info.get('totalTradedVolume', 'N/A')}\n"
        result += f"Value: {trade_info.get('totalTradedValue', 'N/A')}\n"

        return result

    except Exception as e:
        return f"Error fetching live quote for {nse_symbol}: {str(e)}"


def get_jugaad_index_data(
    index_name: Annotated[str, "Index name (e.g., 'NIFTY 50', 'NIFTY BANK')"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
) -> str:
    """
    Fetch historical index data from NSE.

    Args:
        index_name: NSE index name (e.g., 'NIFTY 50', 'NIFTY BANK')
        start_date: Start date in yyyy-mm-dd format
        end_date: End date in yyyy-mm-dd format

    Returns:
        CSV formatted string with index data
    """
    try:
        from jugaad_data.nse import index_df
    except ImportError:
        return "Error: jugaad-data library not installed. Please install it with: pip install jugaad-data"

    try:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
        end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
    except ValueError as e:
        return f"Error parsing dates: {e}. Please use yyyy-mm-dd format."

    try:
        data = index_df(
            symbol=index_name.upper(),
            from_date=start_dt,
            to_date=end_dt
        )

        if data.empty:
            return f"No data found for index '{index_name}' between {start_date} and {end_date}"

        # Sort by date
        if "HistoricalDate" in data.columns:
            data = data.sort_values("HistoricalDate")

        csv_string = data.to_csv(index=False)

        header = f"# Index data for {index_name} from {start_date} to {end_date}\n"
        header += f"# Total records: {len(data)}\n"
        header += f"# Data source: NSE India via jugaad-data\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

        return header + csv_string

    except Exception as e:
        return f"Error fetching index data for {index_name}: {str(e)}"


def get_jugaad_indicators(
    symbol: Annotated[str, "ticker symbol of the company"],
    indicator: Annotated[str, "technical indicator to calculate"],
    curr_date: Annotated[str, "The current trading date, YYYY-mm-dd"],
    look_back_days: Annotated[int, "how many days to look back"] = 30,
) -> str:
    """
    Calculate technical indicators for NSE stocks using jugaad-data.
    This fetches data and calculates indicators using stockstats.

    Args:
        symbol: NSE stock symbol
        indicator: Technical indicator name
        curr_date: Current date for calculation
        look_back_days: Number of days to look back

    Returns:
        Formatted string with indicator values

    Raises:
        ImportError: If required libraries not installed
        Exception: For other errors (triggers fallback)
    """
    try:
        from jugaad_data.nse import stock_df
        from stockstats import wrap
    except ImportError as e:
        raise ImportError(f"Required library not installed: {e}")

    nse_symbol = normalize_symbol(symbol, target="nse")

    # Set timeout for NSE request
    timeout_seconds = 15
    old_handler = None

    try:
        # Set timeout using signal (only works on Unix)
        try:
            old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
            signal.alarm(timeout_seconds)
        except (AttributeError, ValueError):
            pass

        # Calculate date range - need more history for indicator calculation
        curr_dt = datetime.strptime(curr_date, "%Y-%m-%d").date()
        # Fetch extra data for indicator calculation (e.g., 200-day SMA needs 200+ days)
        start_dt = date(curr_dt.year - 1, curr_dt.month, curr_dt.day)  # 1 year back

        data = stock_df(
            symbol=nse_symbol,
            from_date=start_dt,
            to_date=curr_dt,
            series="EQ"
        )

        # Cancel the alarm
        try:
            signal.alarm(0)
            if old_handler:
                signal.signal(signal.SIGALRM, old_handler)
        except (AttributeError, ValueError):
            pass

        if data.empty:
            raise ValueError(f"No data found for symbol '{nse_symbol}' to calculate {indicator}")

        # Prepare data for stockstats
        column_mapping = {
            "DATE": "date",
            "OPEN": "open",
            "HIGH": "high",
            "LOW": "low",
            "CLOSE": "close",
            "VOLUME": "volume",
        }

        for old_name, new_name in column_mapping.items():
            if old_name in data.columns:
                data = data.rename(columns={old_name: new_name})

        # Wrap with stockstats
        df = wrap(data)

        # Calculate the indicator
        df[indicator]  # This triggers stockstats calculation

        # Get the last N days of indicator values
        from dateutil.relativedelta import relativedelta
        result_data = []
        curr_date_dt = datetime.strptime(curr_date, "%Y-%m-%d")
        before = curr_date_dt - relativedelta(days=look_back_days)

        df["date_str"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")

        for _, row in df.iterrows():
            row_date = datetime.strptime(row["date_str"], "%Y-%m-%d")
            if before <= row_date <= curr_date_dt:
                ind_value = row[indicator]
                if pd.isna(ind_value):
                    result_data.append((row["date_str"], "N/A"))
                else:
                    result_data.append((row["date_str"], str(round(ind_value, 4))))

        result_data.sort(reverse=True)  # Most recent first

        result_str = f"## {indicator} values for {nse_symbol} (NSE) from {before.strftime('%Y-%m-%d')} to {curr_date}:\n\n"
        for date_str, value in result_data:
            result_str += f"{date_str}: {value}\n"

        return result_str

    except JugaadDataTimeoutError:
        # Re-raise timeout to trigger fallback
        raise
    except Exception as e:
        raise RuntimeError(f"Error calculating {indicator} for {nse_symbol}: {str(e)}")
