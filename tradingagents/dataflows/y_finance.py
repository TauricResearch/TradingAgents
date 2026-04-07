import os
import warnings
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Annotated, Any, Dict, List, Optional, Union

import pandas as pd
import yfinance as yf
from dateutil.relativedelta import relativedelta

from tradingagents.dataflows.technical_analyst import TechnicalAnalyst
from tradingagents.utils.logger import get_logger

from .stockstats_utils import StockstatsUtils

logger = get_logger(__name__)


@contextmanager
def suppress_yfinance_warnings():
    """Suppress yfinance log and warning output in a thread-safe way.

    Previous implementation redirected sys.stderr to /dev/null, but that is
    NOT thread-safe: concurrent scanner threads each mutate the process-global
    sys.stderr, causing race conditions where one thread closes a file descriptor
    that another thread is still writing to ("I/O operation on closed file").

    This implementation suppresses at the Python logging level, which is
    protected by internal locks and therefore safe to call from many threads.
    """
    import logging

    yf_logger_names = [
        "yfinance",
        "yfinance.base",
        "yfinance.utils",
        "peewee",
        "urllib3.connectionpool",
        "urllib3",
    ]
    saved_levels = {}
    for name in yf_logger_names:
        lgr = logging.getLogger(name)
        saved_levels[name] = lgr.level
        lgr.setLevel(logging.CRITICAL)

    with warnings.catch_warnings():
        warnings.filterwarnings("ignore")
        try:
            yield
        finally:
            for name, level in saved_levels.items():
                logging.getLogger(name).setLevel(level)


def get_ticker_info(symbol: str) -> dict:
    """Get ticker info dict with warning suppression. Returns {} on error."""
    with suppress_yfinance_warnings():
        try:
            return yf.Ticker(symbol.upper()).info or {}
        except Exception:
            return {}


def download_history(symbol: str, **kwargs) -> pd.DataFrame:
    """Download historical data via yf.download() with warning suppression."""
    with suppress_yfinance_warnings():
        try:
            return yf.download(symbol.upper(), **kwargs)
        except Exception:
            return pd.DataFrame()


def get_ticker_history(symbol: str, **kwargs) -> pd.DataFrame:
    """Get ticker history via Ticker.history() with warning suppression."""
    with suppress_yfinance_warnings():
        try:
            return yf.Ticker(symbol.upper()).history(**kwargs)
        except Exception:
            return pd.DataFrame()


def get_ticker_options(symbol: str) -> tuple:
    """Get available option expiration dates. Returns () on error."""
    with suppress_yfinance_warnings():
        try:
            return yf.Ticker(symbol.upper()).options
        except Exception:
            return ()


def get_option_chain(symbol: str, expiration: str):
    """Get option chain for a specific expiration. Returns None on error."""
    with suppress_yfinance_warnings():
        try:
            return yf.Ticker(symbol.upper()).option_chain(expiration)
        except Exception:
            return None


def get_YFin_data_online(
    symbol: Annotated[str, "ticker symbol of the company"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
):

    datetime.strptime(start_date, "%Y-%m-%d")
    datetime.strptime(end_date, "%Y-%m-%d")

    # Create ticker object
    ticker = yf.Ticker(symbol.upper())

    # Fetch historical data for the specified date range
    data = ticker.history(start=start_date, end=end_date)

    # Check if data is empty
    if data.empty:
        return f"No data found for symbol '{symbol}' between {start_date} and {end_date}"

    # Remove timezone info from index for cleaner output
    if data.index.tz is not None:
        data.index = data.index.tz_localize(None)

    # Round numerical values to 2 decimal places for cleaner display
    numeric_columns = ["Open", "High", "Low", "Close", "Adj Close"]
    for col in numeric_columns:
        if col in data.columns:
            data[col] = data[col].round(2)

    # Convert DataFrame to CSV string
    csv_string = data.to_csv()

    # Add header information
    header = f"# Stock data for {symbol.upper()} from {start_date} to {end_date}\n"
    header += f"# Total records: {len(data)}\n"
    header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

    return header + csv_string


def get_average_volume(
    symbol: Annotated[str, "ticker symbol of the company"],
    lookback_days: Annotated[int, "number of trading days to average"] = 20,
    curr_date: Annotated[str, "current date (YYYY-mm-dd) for reference"] = None,
) -> dict:
    """Get average volume over a recent window for liquidity filtering."""
    try:
        if curr_date:
            end_dt = datetime.strptime(curr_date, "%Y-%m-%d")
        else:
            end_dt = datetime.now()
        start_dt = end_dt - timedelta(days=lookback_days * 2)

        with suppress_yfinance_warnings():
            data = yf.download(
                symbol,
                start=start_dt.strftime("%Y-%m-%d"),
                end=end_dt.strftime("%Y-%m-%d"),
                multi_level_index=False,
                progress=False,
                auto_adjust=True,
            )

        if data.empty or "Volume" not in data.columns:
            return {
                "symbol": symbol.upper(),
                "average_volume": None,
                "latest_volume": None,
                "lookback_days": lookback_days,
                "error": "No volume data found",
            }

        volume_series = data["Volume"].dropna()
        if volume_series.empty:
            return {
                "symbol": symbol.upper(),
                "average_volume": None,
                "latest_volume": None,
                "lookback_days": lookback_days,
                "error": "No volume data found",
            }

        average_volume = float(volume_series.tail(lookback_days).mean())
        latest_volume = float(volume_series.iloc[-1])

        return {
            "symbol": symbol.upper(),
            "average_volume": average_volume,
            "latest_volume": latest_volume,
            "lookback_days": lookback_days,
        }
    except Exception as e:
        return {
            "symbol": symbol.upper(),
            "average_volume": None,
            "latest_volume": None,
            "lookback_days": lookback_days,
            "error": f"{e}",
        }


def get_stock_stats_indicators_window(
    symbol: Annotated[str, "ticker symbol of the company"],
    indicator: Annotated[str, "technical indicator to get the analysis and report of"],
    curr_date: Annotated[str, "The current trading date you are trading on, YYYY-mm-dd"],
    look_back_days: Annotated[int, "how many days to look back"],
) -> str:

    best_ind_params = {
        # Moving Averages
        "close_50_sma": (
            "50 SMA: A medium-term trend indicator. "
            "Usage: Identify trend direction and serve as dynamic support/resistance. "
            "Tips: It lags price; combine with faster indicators for timely signals."
        ),
        "close_200_sma": (
            "200 SMA: A long-term trend benchmark. "
            "Usage: Confirm overall market trend and identify golden/death cross setups. "
            "Tips: It reacts slowly; best for strategic trend confirmation rather than frequent trading entries."
        ),
        "close_10_ema": (
            "10 EMA: A responsive short-term average. "
            "Usage: Capture quick shifts in momentum and potential entry points. "
            "Tips: Prone to noise in choppy markets; use alongside longer averages for filtering false signals."
        ),
        # MACD Related
        "macd": (
            "MACD: Computes momentum via differences of EMAs. "
            "Usage: Look for crossovers and divergence as signals of trend changes. "
            "Tips: Confirm with other indicators in low-volatility or sideways markets."
        ),
        "macds": (
            "MACD Signal: An EMA smoothing of the MACD line. "
            "Usage: Use crossovers with the MACD line to trigger trades. "
            "Tips: Should be part of a broader strategy to avoid false positives."
        ),
        "macdh": (
            "MACD Histogram: Shows the gap between the MACD line and its signal. "
            "Usage: Visualize momentum strength and spot divergence early. "
            "Tips: Can be volatile; complement with additional filters in fast-moving markets."
        ),
        # Momentum Indicators
        "rsi": (
            "RSI: Measures momentum to flag overbought/oversold conditions. "
            "Usage: Apply 70/30 thresholds and watch for divergence to signal reversals. "
            "Tips: In strong trends, RSI may remain extreme; always cross-check with trend analysis."
        ),
        # Volatility Indicators
        "boll": (
            "Bollinger Middle: A 20 SMA serving as the basis for Bollinger Bands. "
            "Usage: Acts as a dynamic benchmark for price movement. "
            "Tips: Combine with the upper and lower bands to effectively spot breakouts or reversals."
        ),
        "boll_ub": (
            "Bollinger Upper Band: Typically 2 standard deviations above the middle line. "
            "Usage: Signals potential overbought conditions and breakout zones. "
            "Tips: Confirm signals with other tools; prices may ride the band in strong trends."
        ),
        "boll_lb": (
            "Bollinger Lower Band: Typically 2 standard deviations below the middle line. "
            "Usage: Indicates potential oversold conditions. "
            "Tips: Use additional analysis to avoid false reversal signals."
        ),
        "atr": (
            "ATR: Averages true range to measure volatility. "
            "Usage: Set stop-loss levels and adjust position sizes based on current market volatility. "
            "Tips: It's a reactive measure, so use it as part of a broader risk management strategy."
        ),
        # Volume-Based Indicators
        "vwma": (
            "VWMA: A moving average weighted by volume. "
            "Usage: Confirm trends by integrating price action with volume data. "
            "Tips: Watch for skewed results from volume spikes; use in combination with other volume analyses."
        ),
        "mfi": (
            "MFI: The Money Flow Index is a momentum indicator that uses both price and volume to measure buying and selling pressure. "
            "Usage: Identify overbought (>80) or oversold (<20) conditions and confirm the strength of trends or reversals. "
            "Tips: Use alongside RSI or MACD to confirm signals; divergence between price and MFI can indicate potential reversals."
        ),
    }

    if indicator not in best_ind_params:
        raise ValueError(
            f"Indicator {indicator} is not supported. Please choose from: {list(best_ind_params.keys())}"
        )

    end_date = curr_date
    curr_date_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    before = curr_date_dt - relativedelta(days=look_back_days)

    # Optimized: Get stock data once and calculate indicators for all dates
    try:
        indicator_data = _get_stock_stats_bulk(symbol, indicator, curr_date)

        # Generate the date range we need
        current_dt = curr_date_dt
        date_values = []

        while current_dt >= before:
            date_str = current_dt.strftime("%Y-%m-%d")

            # Look up the indicator value for this date
            if date_str in indicator_data:
                indicator_value = indicator_data[date_str]
            else:
                indicator_value = "N/A: Not a trading day (weekend or holiday)"

            date_values.append((date_str, indicator_value))
            current_dt = current_dt - relativedelta(days=1)

        # Build the result string
        ind_string = ""
        for date_str, value in date_values:
            ind_string += f"{date_str}: {value}\n"

    except Exception as e:
        logger.error(f"Error getting bulk stockstats data: {e}")
        # Fallback to original implementation if bulk method fails
        ind_string = ""
        curr_date_dt = datetime.strptime(curr_date, "%Y-%m-%d")
        while curr_date_dt >= before:
            indicator_value = get_stockstats_indicator(
                symbol, indicator, curr_date_dt.strftime("%Y-%m-%d")
            )
            ind_string += f"{curr_date_dt.strftime('%Y-%m-%d')}: {indicator_value}\n"
            curr_date_dt = curr_date_dt - relativedelta(days=1)

    result_str = (
        f"## {indicator} values from {before.strftime('%Y-%m-%d')} to {end_date}:\n\n"
        + ind_string
        + "\n\n"
        + best_ind_params.get(indicator, "No description available.")
    )

    return result_str


def _get_stock_stats_bulk(
    symbol: Annotated[str, "ticker symbol of the company"],
    indicator: Annotated[str, "technical indicator to calculate"],
    curr_date: Annotated[str, "current date for reference"],
) -> dict:
    """
    Optimized bulk calculation of stock stats indicators.
    Fetches data once and calculates indicator for all available dates.
    Returns dict mapping date strings to indicator values.
    """
    import pandas as pd
    from stockstats import wrap

    from .config import get_config

    config = get_config()
    online = config["data_vendors"]["technical_indicators"] != "local"

    if not online:
        # Local data path
        try:
            data = pd.read_csv(
                os.path.join(
                    config.get("data_cache_dir", "data"),
                    f"{symbol}-YFin-data-2015-01-01-2025-03-25.csv",
                )
            )
            df = wrap(data)
        except FileNotFoundError:
            raise Exception("Stockstats fail: Yahoo Finance data not fetched yet!")
    else:
        # Online data fetching with caching
        today_date = pd.Timestamp.today()
        curr_date_dt = pd.to_datetime(curr_date)

        end_date = today_date
        start_date = today_date - pd.DateOffset(years=2)
        start_date_str = start_date.strftime("%Y-%m-%d")
        end_date_str = end_date.strftime("%Y-%m-%d")

        os.makedirs(config["data_cache_dir"], exist_ok=True)

        data_file = os.path.join(
            config["data_cache_dir"],
            f"{symbol}-YFin-data-{start_date_str}-{end_date_str}.csv",
        )

        if os.path.exists(data_file):
            data = pd.read_csv(data_file)
            data["Date"] = pd.to_datetime(data["Date"])
        else:
            data = yf.download(
                symbol,
                start=start_date_str,
                end=end_date_str,
                multi_level_index=False,
                progress=False,
                auto_adjust=True,
            )
            data = data.reset_index()
            data.to_csv(data_file, index=False)

        df = wrap(data)
        df["Date"] = df["Date"].dt.strftime("%Y-%m-%d")

    # Calculate the indicator for all rows at once
    df[indicator]  # This triggers stockstats to calculate the indicator

    # Create a dictionary mapping date strings to indicator values
    result_dict = {}
    for _, row in df.iterrows():
        date_str = row["Date"]
        indicator_value = row[indicator]

        # Handle NaN/None values
        if pd.isna(indicator_value):
            result_dict[date_str] = "N/A"
        else:
            result_dict[date_str] = str(indicator_value)

    return result_dict


def get_stockstats_indicator(
    symbol: Annotated[str, "ticker symbol of the company"],
    indicator: Annotated[str, "technical indicator to get the analysis and report of"],
    curr_date: Annotated[str, "The current trading date you are trading on, YYYY-mm-dd"],
) -> str:

    curr_date_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    curr_date = curr_date_dt.strftime("%Y-%m-%d")

    try:
        indicator_value = StockstatsUtils.get_stock_stats(
            symbol,
            indicator,
            curr_date,
        )
    except Exception as e:
        logger.error(
            f"Error getting stockstats indicator data for indicator {indicator} on {curr_date}: {e}"
        )
        return ""

    return str(indicator_value)


def get_technical_analysis(
    symbol: Annotated[str, "ticker symbol of the company"],
    curr_date: Annotated[str, "The current trading date, YYYY-mm-dd"],
) -> str:
    """
    Get a concise technical analysis summary with key indicators, signals, and trend interpretation.

    Returns analysis-ready output instead of verbose day-by-day data.
    """
    from stockstats import wrap

    # Fetch price data (last 200 days for indicator calculation)
    curr_date_dt = pd.to_datetime(curr_date)
    start_date = curr_date_dt - pd.DateOffset(days=300)  # Need enough history for 200 SMA

    try:
        with suppress_yfinance_warnings():
            data = yf.download(
                symbol,
                start=start_date.strftime("%Y-%m-%d"),
                end=curr_date_dt.strftime("%Y-%m-%d"),
                multi_level_index=False,
                progress=False,
                auto_adjust=True,
            )

        if data.empty:
            return f"No data found for {symbol}"

        data = data.reset_index()
        df = wrap(data)

        # Get latest values
        latest = df.iloc[-1]
        current_price = float(latest["close"])

        # Instantiate analyst and generate report
        analyst = TechnicalAnalyst(df, current_price)
        return analyst.generate_report(symbol, curr_date)

    except Exception as e:
        logger.error(f"Error analyzing {symbol}: {str(e)}")
        return f"Error analyzing {symbol}: {str(e)}"


def _get_financial_statement(ticker: str, statement_type: str, freq: str) -> str:
    """Helper to retrieve financial statements from yfinance."""
    try:
        ticker_obj = yf.Ticker(ticker.upper())

        if statement_type == "balance_sheet":
            data = (
                ticker_obj.quarterly_balance_sheet
                if freq.lower() == "quarterly"
                else ticker_obj.balance_sheet
            )
            name = "Balance Sheet"
        elif statement_type == "cashflow":
            data = (
                ticker_obj.quarterly_cashflow
                if freq.lower() == "quarterly"
                else ticker_obj.cashflow
            )
            name = "Cash Flow"
        elif statement_type == "income_statement":
            data = (
                ticker_obj.quarterly_income_stmt
                if freq.lower() == "quarterly"
                else ticker_obj.income_stmt
            )
            name = "Income Statement"
        else:
            return f"Error: Unknown statement type '{statement_type}'"

        if data.empty:
            return f"No {name.lower()} data found for symbol '{ticker}'"

        # Convert to CSV string for consistency with other functions
        csv_string = data.to_csv()

        # Add header information
        header = f"# {name} data for {ticker.upper()} ({freq})\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

        return header + csv_string

    except Exception as e:
        return f"Error retrieving {name.lower()} for {ticker}: {str(e)}"


def get_balance_sheet(
    ticker: Annotated[str, "ticker symbol of the company"],
    freq: Annotated[str, "frequency of data: 'annual' or 'quarterly'"] = "quarterly",
    curr_date: Annotated[str, "current date (not used for yfinance)"] = None,
):
    """Get balance sheet data from yfinance."""
    return _get_financial_statement(ticker, "balance_sheet", freq)


def get_cashflow(
    ticker: Annotated[str, "ticker symbol of the company"],
    freq: Annotated[str, "frequency of data: 'annual' or 'quarterly'"] = "quarterly",
    curr_date: Annotated[str, "current date (not used for yfinance)"] = None,
):
    """Get cash flow data from yfinance."""
    return _get_financial_statement(ticker, "cashflow", freq)


def get_income_statement(
    ticker: Annotated[str, "ticker symbol of the company"],
    freq: Annotated[str, "frequency of data: 'annual' or 'quarterly'"] = "quarterly",
    curr_date: Annotated[str, "current date (not used for yfinance)"] = None,
):
    """Get income statement data from yfinance."""
    return _get_financial_statement(ticker, "income_statement", freq)


def get_insider_transactions(
    ticker: Annotated[str, "ticker symbol of the company"],
    curr_date: Annotated[str, "current date (not used for yfinance)"] = None,
):
    """Get insider transactions data from yfinance with parsed transaction types."""
    try:
        ticker_obj = yf.Ticker(ticker.upper())
        data = ticker_obj.insider_transactions

        if data is None or data.empty:
            return f"No insider transactions data found for symbol '{ticker}'"

        # Parse the Text column to populate Transaction type
        def classify_transaction(text):
            if pd.isna(text) or text == "":
                return "Unknown"
            text_lower = str(text).lower()
            if "sale" in text_lower:
                return "Sale"
            elif "purchase" in text_lower or "buy" in text_lower:
                return "Purchase"
            elif "gift" in text_lower:
                return "Gift"
            elif "exercise" in text_lower or "option" in text_lower:
                return "Option Exercise"
            elif "award" in text_lower or "grant" in text_lower:
                return "Award/Grant"
            elif "conversion" in text_lower:
                return "Conversion"
            else:
                return "Other"

        # Apply classification
        data["Transaction"] = data["Text"].apply(classify_transaction)

        # Limit to the last 3 months to keep output focused and small
        if curr_date:
            curr_dt = datetime.strptime(curr_date, "%Y-%m-%d")
        else:
            curr_dt = datetime.now()
        cutoff_dt = curr_dt - relativedelta(months=1)

        if "Start Date" in data.columns:
            data["Start Date"] = pd.to_datetime(data["Start Date"], errors="coerce")
            data = data[data["Start Date"].notna()]
            data = data[data["Start Date"] >= cutoff_dt]
            data = data.sort_values(by="Start Date", ascending=False)

        if data.empty:
            return f"No insider transactions found for {ticker.upper()} in the last 3 months."

        # Calculate summary statistics
        transaction_counts = data["Transaction"].value_counts().to_dict()
        total_sales_value = data[data["Transaction"] == "Sale"]["Value"].sum()
        total_purchases_value = data[data["Transaction"] == "Purchase"]["Value"].sum()

        # Determine insider sentiment
        sales_count = transaction_counts.get("Sale", 0)
        purchases_count = transaction_counts.get("Purchase", 0)

        if purchases_count > sales_count:
            sentiment = "BULLISH ⚡ (more buying than selling)"
        elif sales_count > purchases_count * 2:
            sentiment = "BEARISH ⚠️ (significant insider selling)"
        elif sales_count > purchases_count:
            sentiment = "Slightly bearish (more selling than buying)"
        else:
            sentiment = "Neutral"

        # Build summary header
        header = f"# Insider Transactions for {ticker.upper()}\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        header += "## Summary\n"
        header += f"- **Insider Sentiment:** {sentiment}\n"
        for tx_type, count in sorted(transaction_counts.items(), key=lambda x: -x[1]):
            header += f"- **{tx_type}:** {count} transactions\n"
        if total_sales_value > 0:
            header += f"- **Total Sales Value:** ${total_sales_value:,.0f}\n"
        if total_purchases_value > 0:
            header += f"- **Total Purchases Value:** ${total_purchases_value:,.0f}\n"

        def _coerce_numeric(series: pd.Series) -> pd.Series:
            return pd.to_numeric(
                series.astype(str).str.replace(r"[^0-9.\\-]", "", regex=True),
                errors="coerce",
            )

        def _format_txn(row: pd.Series) -> str:
            date_val = row.get("Start Date", "")
            if isinstance(date_val, pd.Timestamp):
                date_val = date_val.strftime("%Y-%m-%d")
            insider = row.get("Insider", "N/A")
            position = row.get("Position", "N/A")
            shares = row.get("Shares", "N/A")
            value = row.get("Value", "N/A")
            ownership = row.get("Ownership", "N/A")
            return f"{date_val} | {insider} ({position}) | {shares} shares | ${value} | Ownership: {ownership}"

        # Highlight largest purchase/sale by value in the last 3 months
        if "Value" in data.columns:
            value_numeric = _coerce_numeric(data["Value"])
            data = data.assign(_value_numeric=value_numeric)

            purchases = data[data["Transaction"] == "Purchase"]
            sales = data[data["Transaction"] == "Sale"]

            if not purchases.empty and purchases["_value_numeric"].notna().any():
                top_purchase = purchases.loc[purchases["_value_numeric"].idxmax()]
                header += f"- **Largest Purchase (3mo):** {_format_txn(top_purchase)}\n"
            if not sales.empty and sales["_value_numeric"].notna().any():
                top_sale = sales.loc[sales["_value_numeric"].idxmax()]
                header += f"- **Largest Sale (3mo):** {_format_txn(top_sale)}\n"
        header += "\n## Transaction Details\n\n"

        # Select key columns for output
        output_cols = [
            "Start Date",
            "Insider",
            "Position",
            "Transaction",
            "Shares",
            "Value",
            "Ownership",
        ]
        available_cols = [c for c in output_cols if c in data.columns]

        csv_string = data[available_cols].to_csv(index=False)

        return header + csv_string

    except Exception as e:
        return f"Error retrieving insider transactions for {ticker}: {str(e)}"


def get_stock_price(
    ticker: Annotated[str, "ticker symbol of the company"],
    curr_date: Annotated[str, "current date (for reference)"] = None,
) -> float:
    """
    Get the current/latest stock price for a ticker.

    Args:
        ticker: Stock symbol
        curr_date: Optional date (not used, included for API consistency)

    Returns:
        Current stock price as a float, or None if unavailable
    """
    try:
        with suppress_yfinance_warnings():
            stock = yf.Ticker(ticker.upper())
            # Try fast_info first (more efficient)
            try:
                price = stock.fast_info.get("lastPrice")
                if price is not None:
                    return float(price)
            except Exception:
                pass

            # Fallback to history
            hist = stock.history(period="1d")
            if not hist.empty:
                return float(hist["Close"].iloc[-1])

        return None
    except Exception as e:
        logger.error(f"Error getting stock price for {ticker}: {e}")
        return None


def validate_ticker(symbol: str) -> bool:
    """
    Validate if a ticker symbol exists and has trading data.
    """
    try:
        ticker = yf.Ticker(symbol.upper())
        # Use fast_info for lighter validation (no historical download needed)
        # fast_info attributes are lazy-loaded
        _ = ticker.fast_info.get("lastPrice")
        return True

    except Exception:
        # Fallback to older method if fast_info fails or is missing
        try:
            return not ticker.history(period="1d", progress=False).empty
        except Exception:
            return False


def validate_tickers_batch(symbols: Annotated[List[str], "list of ticker symbols"]) -> dict:
    """Validate multiple tickers by downloading minimal recent data."""
    if not symbols:
        return {"valid": [], "invalid": []}

    cleaned = []
    for symbol in symbols:
        if not symbol:
            continue
        cleaned.append(str(symbol).strip().upper())
    cleaned = [s for s in cleaned if s]
    if not cleaned:
        return {"valid": [], "invalid": []}

    data = yf.download(
        cleaned,
        period="1d",
        group_by="ticker",
        progress=False,
        auto_adjust=False,
    )
    valid = []
    if isinstance(data.columns, pd.MultiIndex):
        available = set(data.columns.get_level_values(0))
        valid = [s for s in cleaned if s in available and not data[s].dropna(how="all").empty]
    else:
        # Single ticker case
        if not data.empty:
            valid = [cleaned[0]]
    invalid = [s for s in cleaned if s not in valid]
    return {"valid": valid, "invalid": invalid}


def get_fundamentals(
    ticker: Annotated[str, "ticker symbol of the company"],
    curr_date: Annotated[str, "current date (for reference)"] = None,
) -> str:
    """
    Get comprehensive fundamental data for a ticker using yfinance.
    Returns data in a format similar to Alpha Vantage's OVERVIEW endpoint.

    This is a FREE alternative to Alpha Vantage with no rate limits.
    """
    import json

    try:
        with suppress_yfinance_warnings():
            ticker_obj = yf.Ticker(ticker.upper())
            info = ticker_obj.info

        if not info or info.get("regularMarketPrice") is None:
            return f"No fundamental data found for symbol '{ticker}'"

        # Build a structured response similar to Alpha Vantage
        fundamentals = {
            # Company Info
            "Symbol": ticker.upper(),
            "AssetType": info.get("quoteType", "N/A"),
            "Name": info.get("longName", info.get("shortName", "N/A")),
            "Description": info.get("longBusinessSummary", "N/A"),
            "Exchange": info.get("exchange", "N/A"),
            "Currency": info.get("currency", "USD"),
            "Country": info.get("country", "N/A"),
            "Sector": info.get("sector", "N/A"),
            "Industry": info.get("industry", "N/A"),
            "Address": f"{info.get('address1', '')} {info.get('city', '')}, {info.get('state', '')} {info.get('zip', '')}".strip(),
            "OfficialSite": info.get("website", "N/A"),
            "FiscalYearEnd": info.get("fiscalYearEnd", "N/A"),
            # Valuation
            "MarketCapitalization": str(info.get("marketCap", "N/A")),
            "EBITDA": str(info.get("ebitda", "N/A")),
            "PERatio": str(info.get("trailingPE", "N/A")),
            "ForwardPE": str(info.get("forwardPE", "N/A")),
            "PEGRatio": str(info.get("pegRatio", "N/A")),
            "BookValue": str(info.get("bookValue", "N/A")),
            "PriceToBookRatio": str(info.get("priceToBook", "N/A")),
            "PriceToSalesRatioTTM": str(info.get("priceToSalesTrailing12Months", "N/A")),
            "EVToRevenue": str(info.get("enterpriseToRevenue", "N/A")),
            "EVToEBITDA": str(info.get("enterpriseToEbitda", "N/A")),
            # Earnings & Revenue
            "EPS": str(info.get("trailingEps", "N/A")),
            "ForwardEPS": str(info.get("forwardEps", "N/A")),
            "RevenueTTM": str(info.get("totalRevenue", "N/A")),
            "RevenuePerShareTTM": str(info.get("revenuePerShare", "N/A")),
            "GrossProfitTTM": str(info.get("grossProfits", "N/A")),
            "QuarterlyRevenueGrowthYOY": str(info.get("revenueGrowth", "N/A")),
            "QuarterlyEarningsGrowthYOY": str(info.get("earningsGrowth", "N/A")),
            # Margins & Returns
            "ProfitMargin": str(info.get("profitMargins", "N/A")),
            "OperatingMarginTTM": str(info.get("operatingMargins", "N/A")),
            "GrossMargins": str(info.get("grossMargins", "N/A")),
            "ReturnOnAssetsTTM": str(info.get("returnOnAssets", "N/A")),
            "ReturnOnEquityTTM": str(info.get("returnOnEquity", "N/A")),
            # Dividend
            "DividendPerShare": str(info.get("dividendRate", "N/A")),
            "DividendYield": str(info.get("dividendYield", "N/A")),
            "ExDividendDate": str(info.get("exDividendDate", "N/A")),
            "PayoutRatio": str(info.get("payoutRatio", "N/A")),
            # Balance Sheet
            "TotalCash": str(info.get("totalCash", "N/A")),
            "TotalDebt": str(info.get("totalDebt", "N/A")),
            "CurrentRatio": str(info.get("currentRatio", "N/A")),
            "QuickRatio": str(info.get("quickRatio", "N/A")),
            "DebtToEquity": str(info.get("debtToEquity", "N/A")),
            "FreeCashFlow": str(info.get("freeCashflow", "N/A")),
            "OperatingCashFlow": str(info.get("operatingCashflow", "N/A")),
            # Trading Info
            "Beta": str(info.get("beta", "N/A")),
            "52WeekHigh": str(info.get("fiftyTwoWeekHigh", "N/A")),
            "52WeekLow": str(info.get("fiftyTwoWeekLow", "N/A")),
            "50DayMovingAverage": str(info.get("fiftyDayAverage", "N/A")),
            "200DayMovingAverage": str(info.get("twoHundredDayAverage", "N/A")),
            "SharesOutstanding": str(info.get("sharesOutstanding", "N/A")),
            "SharesFloat": str(info.get("floatShares", "N/A")),
            "SharesShort": str(info.get("sharesShort", "N/A")),
            "ShortRatio": str(info.get("shortRatio", "N/A")),
            "ShortPercentOfFloat": str(info.get("shortPercentOfFloat", "N/A")),
            # Ownership
            "PercentInsiders": str(info.get("heldPercentInsiders", "N/A")),
            "PercentInstitutions": str(info.get("heldPercentInstitutions", "N/A")),
            # Analyst
            "AnalystTargetPrice": str(info.get("targetMeanPrice", "N/A")),
            "AnalystTargetHigh": str(info.get("targetHighPrice", "N/A")),
            "AnalystTargetLow": str(info.get("targetLowPrice", "N/A")),
            "NumberOfAnalysts": str(info.get("numberOfAnalystOpinions", "N/A")),
            "RecommendationKey": info.get("recommendationKey", "N/A"),
            "RecommendationMean": str(info.get("recommendationMean", "N/A")),
        }

        # Return as formatted JSON string
        return json.dumps(fundamentals, indent=4)

    except Exception as e:
        return f"Error retrieving fundamentals for {ticker}: {str(e)}"


def get_options_activity(
    ticker: Annotated[str, "ticker symbol of the company"],
    num_expirations: Annotated[int, "number of nearest expiration dates to analyze"] = 3,
    curr_date: Annotated[str, "current date (for reference)"] = None,
) -> str:
    """
    Get options activity for a specific ticker using yfinance.
    Analyzes volume, open interest, and put/call ratios.

    This is a FREE alternative to Tradier with no API key required.
    """
    try:
        ticker_obj = yf.Ticker(ticker.upper())

        # Get available expiration dates
        expirations = ticker_obj.options
        if not expirations:
            return f"No options data available for {ticker}"

        # Analyze the nearest N expiration dates
        expirations_to_analyze = expirations[: min(num_expirations, len(expirations))]

        report = f"## Options Activity for {ticker.upper()}\n\n"
        report += f"**Available Expirations:** {len(expirations)} dates\n"
        report += f"**Analyzing:** {', '.join(expirations_to_analyze)}\n\n"

        total_call_volume = 0
        total_put_volume = 0
        total_call_oi = 0
        total_put_oi = 0

        unusual_activity = []

        for exp_date in expirations_to_analyze:
            try:
                opt = ticker_obj.option_chain(exp_date)
                calls = opt.calls
                puts = opt.puts

                if calls.empty and puts.empty:
                    continue

                # Calculate totals for this expiration
                call_vol = calls["volume"].sum() if "volume" in calls.columns else 0
                put_vol = puts["volume"].sum() if "volume" in puts.columns else 0
                call_oi = calls["openInterest"].sum() if "openInterest" in calls.columns else 0
                put_oi = puts["openInterest"].sum() if "openInterest" in puts.columns else 0

                # Handle NaN values
                call_vol = 0 if pd.isna(call_vol) else int(call_vol)
                put_vol = 0 if pd.isna(put_vol) else int(put_vol)
                call_oi = 0 if pd.isna(call_oi) else int(call_oi)
                put_oi = 0 if pd.isna(put_oi) else int(put_oi)

                total_call_volume += call_vol
                total_put_volume += put_vol
                total_call_oi += call_oi
                total_put_oi += put_oi

                # Find unusual activity (high volume relative to OI)
                for _, row in calls.iterrows():
                    vol = row.get("volume", 0)
                    oi = row.get("openInterest", 0)
                    if pd.notna(vol) and pd.notna(oi) and oi > 0 and vol > oi * 0.5 and vol > 100:
                        unusual_activity.append(
                            {
                                "type": "CALL",
                                "expiration": exp_date,
                                "strike": row["strike"],
                                "volume": int(vol),
                                "openInterest": int(oi),
                                "vol_oi_ratio": round(vol / oi, 2) if oi > 0 else 0,
                                "impliedVolatility": round(
                                    row.get("impliedVolatility", 0) * 100, 1
                                ),
                            }
                        )

                for _, row in puts.iterrows():
                    vol = row.get("volume", 0)
                    oi = row.get("openInterest", 0)
                    if pd.notna(vol) and pd.notna(oi) and oi > 0 and vol > oi * 0.5 and vol > 100:
                        unusual_activity.append(
                            {
                                "type": "PUT",
                                "expiration": exp_date,
                                "strike": row["strike"],
                                "volume": int(vol),
                                "openInterest": int(oi),
                                "vol_oi_ratio": round(vol / oi, 2) if oi > 0 else 0,
                                "impliedVolatility": round(
                                    row.get("impliedVolatility", 0) * 100, 1
                                ),
                            }
                        )

            except Exception as e:
                report += f"*Error fetching {exp_date}: {str(e)}*\n"
                continue

        # Calculate put/call ratios
        pc_volume_ratio = (
            round(total_put_volume / total_call_volume, 3) if total_call_volume > 0 else 0
        )
        pc_oi_ratio = round(total_put_oi / total_call_oi, 3) if total_call_oi > 0 else 0

        # Summary
        report += "### Summary\n"
        report += "| Metric | Calls | Puts | Put/Call Ratio |\n"
        report += "|--------|-------|------|----------------|\n"
        report += f"| Volume | {total_call_volume:,} | {total_put_volume:,} | {pc_volume_ratio} |\n"
        report += f"| Open Interest | {total_call_oi:,} | {total_put_oi:,} | {pc_oi_ratio} |\n\n"

        # Sentiment interpretation
        report += "### Sentiment Analysis\n"
        if pc_volume_ratio < 0.7:
            report += "- **Volume P/C Ratio:** Bullish (more call volume)\n"
        elif pc_volume_ratio > 1.3:
            report += "- **Volume P/C Ratio:** Bearish (more put volume)\n"
        else:
            report += "- **Volume P/C Ratio:** Neutral\n"

        if pc_oi_ratio < 0.7:
            report += "- **OI P/C Ratio:** Bullish positioning\n"
        elif pc_oi_ratio > 1.3:
            report += "- **OI P/C Ratio:** Bearish positioning\n"
        else:
            report += "- **OI P/C Ratio:** Neutral positioning\n"

        # Unusual activity
        if unusual_activity:
            # Sort by volume/OI ratio
            unusual_activity.sort(key=lambda x: x["vol_oi_ratio"], reverse=True)
            top_unusual = unusual_activity[:10]

            report += "\n### Unusual Activity (High Volume vs Open Interest)\n"
            report += "| Type | Expiry | Strike | Volume | OI | Vol/OI | IV |\n"
            report += "|------|--------|--------|--------|----|---------|----|---|\n"
            for item in top_unusual:
                report += f"| {item['type']} | {item['expiration']} | ${item['strike']} | {item['volume']:,} | {item['openInterest']:,} | {item['vol_oi_ratio']}x | {item['impliedVolatility']}% |\n"
        else:
            report += "\n*No unusual options activity detected.*\n"

        return report

    except Exception as e:
        return f"Error retrieving options activity for {ticker}: {str(e)}"


def analyze_options_flow(
    ticker: Annotated[str, "ticker symbol of the company"],
    num_expirations: Annotated[int, "number of nearest expiration dates to analyze"] = 3,
) -> Dict[str, Any]:
    """
    Analyze options flow to detect unusual activity that signals informed trading.

    Returns structured data for filtering/ranking decisions.

    Signals:
    - very_bullish: P/C ratio < 0.5 (heavy call buying)
    - bullish: P/C ratio 0.5-0.7
    - neutral: P/C ratio 0.7-1.3
    - bearish: P/C ratio 1.3-2.0
    - very_bearish: P/C ratio > 2.0 (heavy put buying)

    Returns:
        Dict with signal, ratios, unusual activity flags
    """
    result = {
        "ticker": ticker.upper(),
        "signal": "neutral",
        "pc_volume_ratio": None,
        "pc_oi_ratio": None,
        "total_call_volume": 0,
        "total_put_volume": 0,
        "unusual_calls": 0,
        "unusual_puts": 0,
        "has_unusual_activity": False,
        "is_bullish_flow": False,
        "error": None,
    }

    try:
        ticker_obj = yf.Ticker(ticker.upper())
        expirations = ticker_obj.options

        if not expirations:
            result["error"] = "No options data"
            return result

        expirations_to_analyze = expirations[: min(num_expirations, len(expirations))]

        total_call_volume = 0
        total_put_volume = 0
        total_call_oi = 0
        total_put_oi = 0
        unusual_calls = 0
        unusual_puts = 0

        for exp_date in expirations_to_analyze:
            try:
                opt = ticker_obj.option_chain(exp_date)
                calls = opt.calls
                puts = opt.puts

                if calls.empty and puts.empty:
                    continue

                # Calculate totals
                call_vol = calls["volume"].sum() if "volume" in calls.columns else 0
                put_vol = puts["volume"].sum() if "volume" in puts.columns else 0
                call_oi = calls["openInterest"].sum() if "openInterest" in calls.columns else 0
                put_oi = puts["openInterest"].sum() if "openInterest" in puts.columns else 0

                call_vol = 0 if pd.isna(call_vol) else int(call_vol)
                put_vol = 0 if pd.isna(put_vol) else int(put_vol)
                call_oi = 0 if pd.isna(call_oi) else int(call_oi)
                put_oi = 0 if pd.isna(put_oi) else int(put_oi)

                total_call_volume += call_vol
                total_put_volume += put_vol
                total_call_oi += call_oi
                total_put_oi += put_oi

                # Count unusual activity (volume > 50% of OI and volume > 100)
                for _, row in calls.iterrows():
                    vol = row.get("volume", 0)
                    oi = row.get("openInterest", 0)
                    if pd.notna(vol) and pd.notna(oi) and oi > 0 and vol > oi * 0.5 and vol > 100:
                        unusual_calls += 1

                for _, row in puts.iterrows():
                    vol = row.get("volume", 0)
                    oi = row.get("openInterest", 0)
                    if pd.notna(vol) and pd.notna(oi) and oi > 0 and vol > oi * 0.5 and vol > 100:
                        unusual_puts += 1

            except Exception:
                continue

        # Calculate ratios
        pc_volume_ratio = (
            round(total_put_volume / total_call_volume, 3) if total_call_volume > 0 else None
        )
        pc_oi_ratio = round(total_put_oi / total_call_oi, 3) if total_call_oi > 0 else None

        # Determine signal based on P/C ratio
        signal = "neutral"
        if pc_volume_ratio is not None:
            if pc_volume_ratio < 0.5:
                signal = "very_bullish"
            elif pc_volume_ratio < 0.7:
                signal = "bullish"
            elif pc_volume_ratio > 2.0:
                signal = "very_bearish"
            elif pc_volume_ratio > 1.3:
                signal = "bearish"

        # Determine if there's unusual bullish flow
        has_unusual = (unusual_calls + unusual_puts) > 0
        is_bullish_flow = has_unusual and unusual_calls > unusual_puts * 2

        result.update(
            {
                "signal": signal,
                "pc_volume_ratio": pc_volume_ratio,
                "pc_oi_ratio": pc_oi_ratio,
                "total_call_volume": total_call_volume,
                "total_put_volume": total_put_volume,
                "unusual_calls": unusual_calls,
                "unusual_puts": unusual_puts,
                "has_unusual_activity": has_unusual,
                "is_bullish_flow": is_bullish_flow,
            }
        )

        return result

    except Exception as e:
        result["error"] = str(e)
        return result


def _get_ticker_universe(
    tickers: Optional[Union[str, List[str]]] = None, max_tickers: Optional[int] = None
) -> List[str]:
    """
    Get a list of ticker symbols.

    Args:
        tickers: List of ticker symbols, or None to load from config file
        max_tickers: Maximum number of tickers to return (None = all)

    Returns:
        List of ticker symbols
    """
    # If custom list provided, use it
    if isinstance(tickers, list):
        ticker_list = [t.upper().strip() for t in tickers if t and isinstance(t, str)]
        return ticker_list[:max_tickers] if max_tickers else ticker_list

    # Load from config file
    from tradingagents.default_config import DEFAULT_CONFIG

    ticker_file = DEFAULT_CONFIG.get("tickers_file")

    if not ticker_file:
        logger.warning("tickers_file not configured, using fallback list")
        return _get_default_tickers()[:max_tickers] if max_tickers else _get_default_tickers()

    # Load tickers from file
    try:
        ticker_path = Path(ticker_file)
        if ticker_path.exists():
            with open(ticker_path, "r") as f:
                ticker_list = [line.strip().upper() for line in f if line.strip()]
            # Remove duplicates while preserving order
            seen = set()
            ticker_list = [t for t in ticker_list if t and t not in seen and not seen.add(t)]
            return ticker_list[:max_tickers] if max_tickers else ticker_list
        else:
            logger.warning(f"Ticker file not found at {ticker_file}, using fallback list")
            return _get_default_tickers()[:max_tickers] if max_tickers else _get_default_tickers()
    except Exception as e:
        logger.warning(f"Could not load ticker list from file: {e}, using fallback")
        return _get_default_tickers()[:max_tickers] if max_tickers else _get_default_tickers()


def _get_default_tickers() -> List[str]:
    """Fallback list of major US stocks if ticker file is not found."""
    return [
        "AAPL",
        "MSFT",
        "GOOGL",
        "AMZN",
        "NVDA",
        "META",
        "TSLA",
        "BRK-B",
        "V",
        "UNH",
        "XOM",
        "JNJ",
        "JPM",
        "WMT",
        "MA",
        "PG",
        "LLY",
        "AVGO",
        "HD",
        "MRK",
        "COST",
        "ABBV",
        "PEP",
        "ADBE",
        "TMO",
        "CSCO",
        "NFLX",
        "ACN",
        "DHR",
        "ABT",
        "VZ",
        "WFC",
        "CRM",
        "PM",
        "LIN",
        "DIS",
        "BMY",
        "NKE",
        "TXN",
        "RTX",
        "QCOM",
        "UPS",
        "HON",
        "AMGN",
        "DE",
        "INTU",
        "AMAT",
        "LOW",
        "SBUX",
        "C",
        "BKNG",
        "ADP",
        "GE",
        "TJX",
        "AXP",
        "SPGI",
        "MDT",
        "GILD",
        "ISRG",
        "BLK",
        "SYK",
        "ZTS",
        "CI",
        "CME",
        "ICE",
        "EQIX",
        "REGN",
        "APH",
        "KLAC",
        "CDNS",
        "SNPS",
        "MCHP",
        "FTNT",
        "ANSS",
        "CTSH",
        "WDAY",
        "ON",
        "NXPI",
        "MPWR",
        "CRWD",
        "AMD",
        "INTC",
        "MU",
        "LRCX",
        "PANW",
        "NOW",
        "DDOG",
        "ZS",
        "NET",
        "TEAM",
    ]


def get_pre_earnings_accumulation_signal(
    ticker: Annotated[str, "ticker symbol to analyze"],
    lookback_days: Annotated[int, "days to analyze volume"] = 10,
) -> dict:
    """
    Detect if a stock is being accumulated BEFORE earnings (LEADING INDICATOR).

    SIGNAL: Volume increases while price stays flat = Smart money accumulating

    This happens BEFORE the price run, giving you an early entry.
    Returns a dict with signal strength and metrics.

    Args:
        ticker: Stock symbol to check
        lookback_days: Recent days to analyze

    Returns:
        Dict with 'signal' (bool), 'volume_ratio' (float), 'price_change_pct' (float), 'current_price' (float)
    """
    try:
        stock = yf.Ticker(ticker.upper())

        # Get 1 month of data to calculate baseline
        hist = stock.history(period="1mo")
        if len(hist) < 20:
            return {"signal": False, "reason": "Insufficient data"}

        # Baseline volume (excluding recent period)
        baseline_volume = hist["Volume"][:-lookback_days].mean()

        # Recent volume
        recent_volume = hist["Volume"][-lookback_days:].mean()

        # Volume ratio
        volume_ratio = recent_volume / baseline_volume if baseline_volume > 0 else 0

        # Price movement in recent period
        price_start = hist["Close"].iloc[-lookback_days]
        price_end = hist["Close"].iloc[-1]
        price_change_pct = ((price_end - price_start) / price_start) * 100

        # SIGNAL CRITERIA:
        # - Volume up at least 50% (1.5x)
        # - Price relatively flat (< 5% move)
        accumulation_signal = volume_ratio >= 2.0 and abs(price_change_pct) < 5.0

        return {
            "signal": accumulation_signal,
            "volume_ratio": round(volume_ratio, 2),
            "price_change_pct": round(price_change_pct, 2),
            "current_price": round(price_end, 2),
            "baseline_volume": int(baseline_volume),
            "recent_volume": int(recent_volume),
        }

    except Exception as e:
        return {"signal": False, "reason": str(e)}


def check_if_price_reacted(
    ticker: Annotated[str, "ticker symbol to analyze"],
    lookback_days: Annotated[int, "days to check for price reaction"] = 3,
    reaction_threshold: Annotated[float, "% change to consider as 'reacted'"] = 5.0,
) -> dict:
    """
    Check if a stock's price has already reacted to news/catalyst.

    Use this to determine if a catalyst (analyst upgrade, news, etc.) is LEADING or LAGGING:
    - If price hasn't moved much = LEADING indicator (you're early)
    - If price already moved significantly = LAGGING indicator (you're late)

    Args:
        ticker: Stock symbol to check
        lookback_days: Days to check for reaction (default 3)
        reaction_threshold: Price change % to consider as "reacted" (default 5%)

    Returns:
        Dict with 'reacted' (bool), 'price_change_pct' (float), 'status' (str: 'leading' or 'lagging')
    """
    try:
        stock = yf.Ticker(ticker.upper())

        # Get recent history
        hist = stock.history(period="1mo")
        if len(hist) < lookback_days:
            return {"reacted": None, "reason": "Insufficient data", "status": "unknown"}

        # Check price movement in lookback period
        price_start = hist["Close"].iloc[-lookback_days]
        price_end = hist["Close"].iloc[-1]
        price_change_pct = ((price_end - price_start) / price_start) * 100

        # Determine if already reacted
        reacted = abs(price_change_pct) >= reaction_threshold

        return {
            "reacted": reacted,
            "price_change_pct": round(price_change_pct, 2),
            "status": "lagging" if reacted else "leading",
            "current_price": round(price_end, 2),
        }

    except Exception as e:
        return {"reacted": None, "reason": str(e), "status": "unknown"}


def check_intraday_movement(
    ticker: Annotated[str, "ticker symbol to analyze"],
    movement_threshold: Annotated[float, "% change to consider as 'already moved'"] = 15.0,
) -> dict:
    """
    Check if a stock has already moved significantly today (intraday).

    This helps filter out stocks that have already run up significantly today,
    avoiding "chasing" stocks that already made their upward move.
    Downside movers are NOT filtered — they are evaluated normally by the analysis layer.

    Args:
        ticker: Stock symbol to check
        movement_threshold: Intraday % change to consider as "already moved" (default 15%)

    Returns:
        Dict with:
        - 'already_moved': bool (True if price is UP more than threshold from open)
        - 'intraday_change_pct': float (% change from open to current/last)
        - 'open_price': float
        - 'current_price': float
        - 'status': str ('fresh' if not moved, 'stale' if already moved)
    """
    try:
        with suppress_yfinance_warnings():
            stock = yf.Ticker(ticker.upper())

            # Get today's intraday data (1-day period with 1-minute interval)
            # This gives us open, current price, high, low for today
            hist = stock.history(period="1d", interval="1m")

            if hist.empty:
                # Fallback to daily data if intraday not available
                hist_daily = stock.history(period="5d")
                if hist_daily.empty or len(hist_daily) == 0:
                    return {
                        "already_moved": None,
                        "reason": "No price data available",
                        "status": "unknown",
                    }

                # Use today's open and close from daily data
                today_data = hist_daily.iloc[-1]
                open_price = today_data["Open"]
                current_price = today_data["Close"]
            else:
                # Use intraday data - first candle's open vs latest candle's close
                open_price = hist["Open"].iloc[0]
                current_price = hist["Close"].iloc[-1]

            # Calculate intraday change percentage
            intraday_change_pct = ((current_price - open_price) / open_price) * 100

            # Determine if stock already moved significantly (upward only).
            # We only filter stocks that already *ran up* — the intent is to avoid chasing.
            # A stock that dropped significantly is not "stale" in the chase sense; the
            # analysis layer should decide whether it's a buy or not.
            already_moved = intraday_change_pct >= movement_threshold

            return {
                "already_moved": already_moved,
                "intraday_change_pct": round(intraday_change_pct, 2),
                "open_price": round(open_price, 2),
                "current_price": round(current_price, 2),
                "status": "stale" if already_moved else "fresh",
            }

    except Exception as e:
        return {"already_moved": None, "reason": str(e), "status": "unknown"}
