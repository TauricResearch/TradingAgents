import logging
from datetime import datetime
from typing import Annotated

import pandas as pd
import requests
import yfinance as yf
from dateutil.relativedelta import relativedelta

from .finnhub_common import ThirdPartyTimeoutError
from .stockstats_utils import (
    StockstatsUtils,
    _clean_dataframe,
    _load_or_fetch_ohlcv,
    filter_ohlcv_by_date,
    yf_retry,
)

logger = logging.getLogger(__name__)


def _filter_financials_by_date(data: pd.DataFrame, curr_date: str | None) -> pd.DataFrame | str:
    """Drop financial statement columns whose date header is after curr_date.

    yfinance returns financial statements with dates as column headers (Timestamps).
    This function drops columns representing future fiscal periods to prevent
    look-ahead bias in backtesting.

    Args:
        data: Financial statement DataFrame (rows=line items, columns=dates).
        curr_date: Cutoff date in YYYY-MM-DD format. If None, returns data unchanged.

    Returns:
        DataFrame with only columns where date <= curr_date, or a message string
        if all columns are filtered out.
    """
    if curr_date is None or data.empty:
        return data
    cutoff = pd.Timestamp(curr_date)
    # yfinance column headers are Timestamps — filter them
    date_cols = pd.to_datetime(data.columns, errors="coerce")
    mask = date_cols <= cutoff
    # Keep columns that are valid dates and <= cutoff, plus any non-date columns
    keep_mask = mask | date_cols.isna()
    filtered = data.loc[:, keep_mask]
    if filtered.empty:
        return f"No financial data available on or before {curr_date}"
    return filtered


def get_YFin_data_online(
    symbol: Annotated[str, "ticker symbol of the company"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
) -> str:

    datetime.strptime(start_date, "%Y-%m-%d")
    datetime.strptime(end_date, "%Y-%m-%d")

    # Create ticker object
    ticker = yf.Ticker(symbol.upper())

    # Fetch historical data for the specified date range
    data = yf_retry(lambda: ticker.history(start=start_date, end=end_date))

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


def get_stock_data(
    symbol: Annotated[str, "ticker symbol of the company"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
    lookback_days: int = 90,
) -> str:
    """Fetch OHLCV data and append key reference levels.

    Fetches the full date range (start_date to end_date) to compute reference
    statistics, then truncates the CSV output to the last ``lookback_days``
    trading days. The reference levels are appended as a text block after the
    CSV to preserve context without the token cost of the full price history.
    """
    datetime.strptime(start_date, "%Y-%m-%d")
    datetime.strptime(end_date, "%Y-%m-%d")

    ticker = yf.Ticker(symbol.upper())
    data = yf_retry(lambda: ticker.history(start=start_date, end=end_date))

    if data.empty:
        return f"No data found for symbol '{symbol}' between {start_date} and {end_date}"

    if data.index.tz is not None:
        data.index = data.index.tz_localize(None)

    numeric_columns = ["Open", "High", "Low", "Close", "Adj Close"]
    for col in numeric_columns:
        if col in data.columns:
            data[col] = data[col].round(2)

    # ── Compute reference levels from the full dataset ────────────────────────
    close = data["Close"]
    week52_high = round(float(close.max()), 2)
    week52_low = round(float(close.min()), 2)

    stats_lines: list[str] = [
        f"52-Week High: {week52_high}",
        f"52-Week Low:  {week52_low}",
    ]

    current_price = round(float(close.iloc[-1]), 2)
    stats_lines.append(f"Current Price: {current_price}")

    if len(close) >= 50:
        sma50 = round(float(close.iloc[-50:].mean()), 2)
        pct_vs_50 = round((current_price - sma50) / sma50 * 100, 2)
        direction_50 = "above" if current_price >= sma50 else "below"
        stats_lines.append(f"50-Day SMA: {sma50}  ({direction_50} by {abs(pct_vs_50):.2f}%)")
    else:
        stats_lines.append("50-Day SMA: insufficient data")

    if len(close) >= 200:
        sma200 = round(float(close.iloc[-200:].mean()), 2)
        pct_vs_200 = round((current_price - sma200) / sma200 * 100, 2)
        direction_200 = "above" if current_price >= sma200 else "below"
        stats_lines.append(f"200-Day SMA: {sma200}  ({direction_200} by {abs(pct_vs_200):.2f}%)")
    else:
        stats_lines.append("200-Day SMA: insufficient data (< 200 trading days)")

    # ── Truncate to lookback_days ─────────────────────────────────────────────
    truncated = data.tail(lookback_days)
    csv_string = truncated.to_csv()

    header = f"# Stock data for {symbol.upper()} (last {lookback_days} days ending {end_date})\n"
    header += f"# Rows shown: {len(truncated)} of {len(data)} available\n"
    header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

    reference_block = "\n\n--- Key Reference Levels ---\n" + "\n".join(stats_lines)

    return header + csv_string + reference_block


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
        logger.warning(
            "Bulk stockstats failed for %s/%s, falling back to per-day loop: %s",
            symbol,
            indicator,
            e,
        )
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
    Fetches data once (via shared _load_or_fetch_ohlcv cache) and calculates
    the indicator for all available dates up to curr_date.
    Returns dict mapping date strings to indicator values.

    Raises:
        YFinanceError: if data cannot be loaded or indicator calculation fails.
    """
    from stockstats import wrap

    # Single authority: _load_or_fetch_ohlcv handles both online and local modes,
    # dynamic cache filename, and corpus validation — no duplicated download logic here.
    data = _load_or_fetch_ohlcv(symbol)
    data = _clean_dataframe(data)
    # Filter to prevent look-ahead bias: only data on or before curr_date
    data = filter_ohlcv_by_date(data, curr_date)
    df = wrap(data)
    # After wrap(), the date column becomes the datetime index (named 'date').
    # Access via df.index, not df["Date"] which stockstats would try to parse as an indicator.

    # Calculate the indicator for all rows at once
    df[indicator]  # This triggers stockstats to calculate the indicator

    # Create a dictionary mapping date strings to indicator values
    # Optimized: vectorized operations for performance using correct DatetimeIndex
    series = df[indicator].copy()
    series.index = series.index.strftime("%Y-%m-%d")
    return series.fillna("N/A").astype(str).to_dict()


def get_stockstats_indicator(
    symbol: Annotated[str, "ticker symbol of the company"],
    indicator: Annotated[str, "technical indicator to get the analysis and report of"],
    curr_date: Annotated[str, "The current trading date you are trading on, YYYY-mm-dd"],
) -> str:
    curr_date_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    curr_date = curr_date_dt.strftime("%Y-%m-%d")

    # Raises YFinanceError on failure — caller (route_to_vendor) catches typed exceptions.
    indicator_value = StockstatsUtils.get_stock_stats(symbol, indicator, curr_date)
    return str(indicator_value)


def get_fundamentals(
    ticker: Annotated[str, "ticker symbol of the company"],
    curr_date: Annotated[str, "current date (not used for yfinance)"] = None,
) -> str:
    """Get company fundamentals overview from yfinance."""
    try:
        ticker_obj = yf.Ticker(ticker.upper())
        info = yf_retry(lambda: ticker_obj.info)

        if not info:
            return f"No fundamentals data found for symbol '{ticker}'"

        fields = [
            ("Name", info.get("longName")),
            ("Sector", info.get("sector")),
            ("Industry", info.get("industry")),
            ("Market Cap", info.get("marketCap")),
            ("PE Ratio (TTM)", info.get("trailingPE")),
            ("Forward PE", info.get("forwardPE")),
            ("PEG Ratio", info.get("pegRatio")),
            ("Price to Book", info.get("priceToBook")),
            ("EPS (TTM)", info.get("trailingEps")),
            ("Forward EPS", info.get("forwardEps")),
            ("Dividend Yield", info.get("dividendYield")),
            ("Beta", info.get("beta")),
            ("52 Week High", info.get("fiftyTwoWeekHigh")),
            ("52 Week Low", info.get("fiftyTwoWeekLow")),
            ("50 Day Average", info.get("fiftyDayAverage")),
            ("200 Day Average", info.get("twoHundredDayAverage")),
            ("Revenue (TTM)", info.get("totalRevenue")),
            ("Gross Profit", info.get("grossProfits")),
            ("EBITDA", info.get("ebitda")),
            ("Net Income", info.get("netIncomeToCommon")),
            ("Profit Margin", info.get("profitMargins")),
            ("Operating Margin", info.get("operatingMargins")),
            ("Return on Equity", info.get("returnOnEquity")),
            ("Return on Assets", info.get("returnOnAssets")),
            ("Debt to Equity", info.get("debtToEquity")),
            ("Current Ratio", info.get("currentRatio")),
            ("Book Value", info.get("bookValue")),
            ("Free Cash Flow", info.get("freeCashflow")),
        ]

        lines = []
        for label, value in fields:
            if value is not None:
                lines.append(f"{label}: {value}")

        header = f"# Company Fundamentals for {ticker.upper()}\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

        return header + "\n".join(lines)

    except requests.exceptions.Timeout:
        raise ThirdPartyTimeoutError(
            f"Request timed out retrieving fundamentals for {ticker}"
        ) from None
    except ThirdPartyTimeoutError:
        raise
    except Exception as e:
        return f"Error retrieving fundamentals for {ticker}: {str(e)}"


def get_balance_sheet(
    ticker: Annotated[str, "ticker symbol of the company"],
    freq: Annotated[str, "frequency of data: 'annual' or 'quarterly'"] = "quarterly",
    curr_date: Annotated[str, "current date for look-ahead bias filtering"] = None,
) -> str:
    """Get balance sheet data from yfinance, filtered by curr_date to prevent look-ahead bias."""
    try:
        ticker_obj = yf.Ticker(ticker.upper())

        if freq.lower() == "quarterly":
            data = yf_retry(lambda: ticker_obj.quarterly_balance_sheet)
        else:
            data = yf_retry(lambda: ticker_obj.balance_sheet)

        if data.empty:
            return f"No balance sheet data found for symbol '{ticker}'"

        # Filter to prevent look-ahead bias
        data = _filter_financials_by_date(data, curr_date)
        if isinstance(data, str):
            return data

        # Convert to CSV string for consistency with other functions
        csv_string = data.to_csv()

        # Add header information
        header = f"# Balance Sheet data for {ticker.upper()} ({freq})\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

        return header + csv_string

    except requests.exceptions.Timeout:
        raise ThirdPartyTimeoutError(
            f"Request timed out retrieving balance sheet for {ticker}"
        ) from None
    except ThirdPartyTimeoutError:
        raise
    except Exception as e:
        return f"Error retrieving balance sheet for {ticker}: {str(e)}"


def get_cashflow(
    ticker: Annotated[str, "ticker symbol of the company"],
    freq: Annotated[str, "frequency of data: 'annual' or 'quarterly'"] = "quarterly",
    curr_date: Annotated[str, "current date for look-ahead bias filtering"] = None,
) -> str:
    """Get cash flow data from yfinance, filtered by curr_date to prevent look-ahead bias."""
    try:
        ticker_obj = yf.Ticker(ticker.upper())

        if freq.lower() == "quarterly":
            data = yf_retry(lambda: ticker_obj.quarterly_cashflow)
        else:
            data = yf_retry(lambda: ticker_obj.cashflow)

        if data.empty:
            return f"No cash flow data found for symbol '{ticker}'"

        # Filter to prevent look-ahead bias
        data = _filter_financials_by_date(data, curr_date)
        if isinstance(data, str):
            return data

        # Convert to CSV string for consistency with other functions
        csv_string = data.to_csv()

        # Add header information
        header = f"# Cash Flow data for {ticker.upper()} ({freq})\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

        return header + csv_string

    except requests.exceptions.Timeout:
        raise ThirdPartyTimeoutError(
            f"Request timed out retrieving cash flow for {ticker}"
        ) from None
    except ThirdPartyTimeoutError:
        raise
    except Exception as e:
        return f"Error retrieving cash flow for {ticker}: {str(e)}"


def get_income_statement(
    ticker: Annotated[str, "ticker symbol of the company"],
    freq: Annotated[str, "frequency of data: 'annual' or 'quarterly'"] = "quarterly",
    curr_date: Annotated[str, "current date for look-ahead bias filtering"] = None,
) -> str:
    """Get income statement data from yfinance, filtered by curr_date to prevent look-ahead bias."""
    try:
        ticker_obj = yf.Ticker(ticker.upper())

        if freq.lower() == "quarterly":
            data = yf_retry(lambda: ticker_obj.quarterly_income_stmt)
        else:
            data = yf_retry(lambda: ticker_obj.income_stmt)

        if data.empty:
            return f"No income statement data found for symbol '{ticker}'"

        # Filter to prevent look-ahead bias
        data = _filter_financials_by_date(data, curr_date)
        if isinstance(data, str):
            return data

        # Convert to CSV string for consistency with other functions
        csv_string = data.to_csv()

        # Add header information
        header = f"# Income Statement data for {ticker.upper()} ({freq})\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

        return header + csv_string

    except requests.exceptions.Timeout:
        raise ThirdPartyTimeoutError(
            f"Request timed out retrieving income statement for {ticker}"
        ) from None
    except ThirdPartyTimeoutError:
        raise
    except Exception as e:
        return f"Error retrieving income statement for {ticker}: {str(e)}"


def get_insider_transactions(ticker: Annotated[str, "ticker symbol of the company"]) -> str:
    """Get insider transactions data from yfinance."""
    try:
        ticker_obj = yf.Ticker(ticker.upper())
        data = yf_retry(lambda: ticker_obj.insider_transactions)

        if data is None or data.empty:
            return f"No insider transactions data found for symbol '{ticker}'"

        # Convert to CSV string for consistency with other functions
        csv_string = data.to_csv()

        # Add header information
        header = f"# Insider Transactions data for {ticker.upper()}\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

        return header + csv_string

    except requests.exceptions.Timeout:
        raise ThirdPartyTimeoutError(
            f"Request timed out retrieving insider transactions for {ticker}"
        ) from None
    except ThirdPartyTimeoutError:
        raise
    except Exception as e:
        return f"Error retrieving insider transactions for {ticker}: {str(e)}"
