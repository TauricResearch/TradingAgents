"""Tushare data source module for A-share and HK stock markets.

This module implements the 9 standard data functions required by the
pluggable data-source architecture, using Tushare Pro API as backend.
"""

import os
import time
import logging
from datetime import datetime, timedelta
from typing import Annotated

import pandas as pd

try:
    import tushare as ts
except ImportError:
    ts = None

try:
    from stockstats import wrap as stockstats_wrap
except ImportError:
    stockstats_wrap = None

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class TushareRateLimitError(Exception):
    """Raised when Tushare API rate limit is exceeded after all retries."""
    pass


# ---------------------------------------------------------------------------
# Helper / Utility Functions
# ---------------------------------------------------------------------------

def get_tushare_pro():
    """Get a Tushare Pro API instance using the TUSHARE_API_KEY env variable.

    Returns:
        tushare pro_api instance

    Raises:
        ValueError: If TUSHARE_API_KEY is not set or tushare is not installed.
    """
    if ts is None:
        raise ValueError(
            "tushare is not installed. Please install it with: pip install tushare"
        )
    key = os.environ.get("TUSHARE_API_KEY", "").strip()
    if not key:
        raise ValueError(
            "TUSHARE_API_KEY environment variable is not set. "
            "Please set it to your Tushare Pro API token."
        )
    return ts.pro_api(key)


def normalize_ts_code(symbol: str) -> str:
    """Normalize various symbol formats to Tushare standard ts_code format.

    Examples:
        "600000"    -> "600000.SH"
        "000001"    -> "000001.SZ"
        "SH600000"  -> "600000.SH"
        "SZ000001"  -> "000001.SZ"
        "600000.SH" -> "600000.SH" (unchanged)
        "0700.HK"   -> "0700.HK" (unchanged)
        "HK0700"    -> "0700.HK"
    """
    symbol = symbol.strip()

    # Already in standard format with suffix
    upper = symbol.upper()
    # .SS is yfinance convention for Shanghai; convert to Tushare .SH
    if upper.endswith(".SS"):
        return upper[:-3] + ".SH"
    if upper.endswith(".SH") or upper.endswith(".SZ") or upper.endswith(".HK"):
        return upper

    # Prefixed format: SH600000, SS600000, SZ000001, HK0700
    if upper.startswith("SH") and upper[2:].isdigit():
        return f"{upper[2:]}.SH"
    if upper.startswith("SS") and upper[2:].isdigit():
        return f"{upper[2:]}.SH"
    if upper.startswith("SZ") and upper[2:].isdigit():
        return f"{upper[2:]}.SZ"
    if upper.startswith("HK") and upper[2:].isdigit():
        return f"{upper[2:]}.HK"

    # Pure digit — infer exchange from leading digit
    if symbol.isdigit():
        if symbol.startswith("6") or symbol.startswith("9"):
            return f"{symbol}.SH"
        elif symbol.startswith("0") or symbol.startswith("3"):
            return f"{symbol}.SZ"
        else:
            # Default to SH for other codes (e.g. 5xxxxx ETFs on Shanghai)
            return f"{symbol}.SH"

    # Fallback: return as-is uppercased
    return upper


def convert_date_to_tushare(date_str: str) -> str:
    """Convert date string from 'YYYY-MM-DD' to Tushare format 'YYYYMMDD'.

    Example: "2024-01-15" -> "20240115"
    """
    return date_str.replace("-", "")


def convert_date_from_tushare(date_str: str) -> str:
    """Convert date string from Tushare format 'YYYYMMDD' to 'YYYY-MM-DD'.

    Example: "20240115" -> "2024-01-15"
    """
    if len(date_str) == 8:
        return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
    return date_str


def tushare_retry(func, max_retries=3, base_delay=1.0):
    """Execute a Tushare API call with exponential backoff on rate limits.

    Retries when the exception message contains rate-limit keywords such as
    "too many requests" or "频率".

    Args:
        func: Callable to execute.
        max_retries: Maximum number of retry attempts.
        base_delay: Base delay in seconds (doubles each retry).

    Returns:
        The result of func().

    Raises:
        TushareRateLimitError: If all retries are exhausted.
    """
    rate_limit_keywords = ["too many requests", "频率", "每分钟", "限制", "rate limit"]

    for attempt in range(max_retries + 1):
        try:
            return func()
        except Exception as e:
            err_msg = str(e).lower()
            is_rate_limit = any(kw in err_msg for kw in rate_limit_keywords)

            if not is_rate_limit:
                raise  # Not a rate-limit error, propagate immediately

            if attempt < max_retries:
                delay = base_delay * (2 ** attempt)
                logger.warning(
                    f"Tushare rate limited, retrying in {delay:.1f}s "
                    f"(attempt {attempt + 1}/{max_retries})"
                )
                time.sleep(delay)
            else:
                raise TushareRateLimitError(
                    f"Tushare rate limit exceeded after {max_retries} retries: {e}"
                ) from e


# ---------------------------------------------------------------------------
# Helper to compute quarterly periods
# ---------------------------------------------------------------------------

def _get_report_periods(freq: str, curr_date: str = None, count: int = 4):
    """Generate a list of report period strings (YYYYMMDD) for financial queries.

    Args:
        freq: "quarterly" or "annual"
        curr_date: Current date in YYYY-MM-DD format (filter future periods)
        count: Number of periods to return

    Returns:
        List of period strings in YYYYMMDD format.
    """
    if curr_date:
        ref_date = datetime.strptime(curr_date, "%Y-%m-%d")
    else:
        ref_date = datetime.now()

    periods = []
    if freq.lower() == "quarterly":
        # Quarter end dates: 0331, 0630, 0930, 1231
        quarter_ends = ["0331", "0630", "0930", "1231"]
        year = ref_date.year
        # Generate periods going backward
        for y in range(year, year - 5, -1):
            for qe in reversed(quarter_ends):
                period = f"{y}{qe}"
                period_date = datetime.strptime(period, "%Y%m%d")
                if period_date <= ref_date:
                    periods.append(period)
                if len(periods) >= count:
                    break
            if len(periods) >= count:
                break
    else:
        # Annual: use 1231 as period end
        year = ref_date.year
        for y in range(year, year - 5, -1):
            period = f"{y}1231"
            period_date = datetime.strptime(period, "%Y%m%d")
            if period_date <= ref_date:
                periods.append(period)
            if len(periods) >= count:
                break

    return periods


# ---------------------------------------------------------------------------
# Indicator descriptions
# ---------------------------------------------------------------------------

INDICATOR_DESCRIPTIONS = {
    "close_50_sma": (
        "50 SMA: A medium-term trend indicator. "
        "Usage: Identify trend direction and serve as dynamic support/resistance. "
        "Tips: It lags price; combine with faster indicators for timely signals."
    ),
    "close_200_sma": (
        "200 SMA: A long-term trend benchmark. "
        "Usage: Confirm overall market trend and identify golden/death cross setups. "
        "Tips: It reacts slowly; best for strategic trend confirmation."
    ),
    "close_10_ema": (
        "10 EMA: A responsive short-term average. "
        "Usage: Capture quick shifts in momentum and potential entry points. "
        "Tips: Prone to noise in choppy markets; use alongside longer averages."
    ),
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
        "Tips: Can be volatile; complement with additional filters."
    ),
    "rsi": (
        "RSI: Measures momentum to flag overbought/oversold conditions. "
        "Usage: Apply 70/30 thresholds and watch for divergence to signal reversals. "
        "Tips: In strong trends, RSI may remain extreme; cross-check with trend analysis."
    ),
    "boll": (
        "Bollinger Middle: A 20 SMA serving as the basis for Bollinger Bands. "
        "Usage: Acts as a dynamic benchmark for price movement. "
        "Tips: Combine with upper and lower bands to spot breakouts or reversals."
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
        "Tips: It's a reactive measure; use as part of a broader risk management strategy."
    ),
    "vwma": (
        "VWMA: A moving average weighted by volume. "
        "Usage: Confirm trends by integrating price action with volume data. "
        "Tips: Watch for skewed results from volume spikes."
    ),
}


# ---------------------------------------------------------------------------
# 9 Core Data Functions
# ---------------------------------------------------------------------------

def get_tushare_stock(
    symbol: Annotated[str, "ticker symbol (e.g. '600000' or '600000.SH')"],
    start_date: Annotated[str, "Start date in YYYY-MM-DD format"],
    end_date: Annotated[str, "End date in YYYY-MM-DD format"],
) -> str:
    """Get OHLCV stock price data from Tushare with adjusted close price."""
    try:
        pro = get_tushare_pro()
        ts_code = normalize_ts_code(symbol)
        ts_start = convert_date_to_tushare(start_date)
        ts_end = convert_date_to_tushare(end_date)

        # Fetch daily price data
        df = tushare_retry(
            lambda: pro.daily(ts_code=ts_code, start_date=ts_start, end_date=ts_end)
        )

        if df is None or df.empty:
            return f"No stock data found for symbol '{symbol}' between {start_date} and {end_date}"

        # Fetch adjustment factor for calculating Adj Close
        adj_df = tushare_retry(
            lambda: pro.adj_factor(ts_code=ts_code, start_date=ts_start, end_date=ts_end)
        )

        # Sort by date ascending (tushare returns descending by default)
        df = df.sort_values("trade_date").reset_index(drop=True)

        # Calculate Adj Close
        if adj_df is not None and not adj_df.empty:
            adj_df = adj_df.sort_values("trade_date").reset_index(drop=True)
            # Merge adjustment factors
            df = df.merge(adj_df[["trade_date", "adj_factor"]], on="trade_date", how="left")
            # Latest adj_factor is the most recent one (last row after sort ascending)
            latest_adj = df["adj_factor"].iloc[-1]
            df["adj_close"] = (df["close"] * df["adj_factor"] / latest_adj).round(2)
        else:
            df["adj_close"] = df["close"]

        # Format date column
        df["date_fmt"] = df["trade_date"].apply(convert_date_from_tushare)

        # Volume: tushare 'vol' is in lots (手, 100 shares each), convert to shares
        df["volume_shares"] = (df["vol"] * 100).astype(int)

        # Round price columns
        for col in ["open", "high", "low", "close"]:
            df[col] = df[col].round(2)

        # Build CSV output
        header = f"# Stock data for {ts_code} from {start_date} to {end_date}\n"
        header += f"# Total records: {len(df)}\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

        lines = ["Date,Open,High,Low,Close,Adj Close,Volume"]
        for _, row in df.iterrows():
            lines.append(
                f"{row['date_fmt']},{row['open']:.2f},{row['high']:.2f},"
                f"{row['low']:.2f},{row['close']:.2f},{row['adj_close']:.2f},"
                f"{row['volume_shares']}"
            )

        return header + "\n".join(lines) + "\n"

    except TushareRateLimitError:
        raise
    except Exception as e:
        return f"Error retrieving stock data for {symbol}: {str(e)}"


def get_tushare_indicators(
    symbol: Annotated[str, "ticker symbol (e.g. '600000' or '600000.SH')"],
    indicator: Annotated[str, "technical indicator name"],
    curr_date: Annotated[str, "Current trading date in YYYY-MM-DD format"],
    look_back_days: Annotated[int, "Number of days to look back"],
) -> str:
    """Get technical indicator values computed from Tushare daily data."""
    supported_indicators = list(INDICATOR_DESCRIPTIONS.keys())
    if indicator not in supported_indicators:
        raise ValueError(
            f"Indicator '{indicator}' is not supported. "
            f"Please choose from: {supported_indicators}"
        )

    if stockstats_wrap is None:
        return (
            "Error: stockstats is not installed. "
            "Please install it with: pip install stockstats"
        )

    try:
        pro = get_tushare_pro()
        ts_code = normalize_ts_code(symbol)

        # Calculate date range with extra buffer for indicator warm-up
        curr_date_dt = datetime.strptime(curr_date, "%Y-%m-%d")
        buffer_days = look_back_days + 300  # Extra days for indicator calculation warm-up
        start_date_dt = curr_date_dt - timedelta(days=buffer_days)
        ts_start = convert_date_to_tushare(start_date_dt.strftime("%Y-%m-%d"))
        ts_end = convert_date_to_tushare(curr_date)

        # Fetch daily data
        df = tushare_retry(
            lambda: pro.daily(ts_code=ts_code, start_date=ts_start, end_date=ts_end)
        )

        if df is None or df.empty:
            return f"No stock data found for symbol '{symbol}' to compute indicators"

        # Sort ascending by date
        df = df.sort_values("trade_date").reset_index(drop=True)

        # Build DataFrame for stockstats (requires: open, high, low, close, volume)
        stock_df = pd.DataFrame({
            "date": df["trade_date"].apply(convert_date_from_tushare),
            "open": pd.to_numeric(df["open"], errors="coerce"),
            "high": pd.to_numeric(df["high"], errors="coerce"),
            "low": pd.to_numeric(df["low"], errors="coerce"),
            "close": pd.to_numeric(df["close"], errors="coerce"),
            "volume": pd.to_numeric(df["vol"], errors="coerce") * 100,
        })
        stock_df = stock_df.dropna(subset=["close"])

        # Wrap with stockstats and calculate indicator
        ss_df = stockstats_wrap(stock_df)
        ss_df[indicator]  # Trigger calculation

        # Build date -> value mapping
        indicator_map = {}
        for _, row in ss_df.iterrows():
            date_str = row["date"]
            val = row[indicator]
            if pd.isna(val):
                indicator_map[date_str] = "N/A"
            else:
                indicator_map[date_str] = f"{val:.2f}"

        # Generate output for the look_back_days range
        display_start_dt = curr_date_dt - timedelta(days=look_back_days)
        lines = []
        current_dt = display_start_dt
        while current_dt <= curr_date_dt:
            date_str = current_dt.strftime("%Y-%m-%d")
            if date_str in indicator_map:
                lines.append(f"{date_str}: {indicator_map[date_str]}")
            else:
                lines.append(f"{date_str}: N/A: Not a trading day (weekend or holiday)")
            current_dt += timedelta(days=1)

        result = (
            f"## {indicator} values from {display_start_dt.strftime('%Y-%m-%d')} to {curr_date}:\n\n"
            + "\n".join(lines)
            + "\n\n"
            + INDICATOR_DESCRIPTIONS.get(indicator, "No description available.")
        )
        return result

    except TushareRateLimitError:
        raise
    except Exception as e:
        return f"Error retrieving indicators for {symbol}: {str(e)}"


def get_tushare_fundamentals(
    ticker: Annotated[str, "ticker symbol (e.g. '600000' or '600000.SH')"],
    curr_date: Annotated[str, "current date in YYYY-MM-DD format"] = None,
) -> str:
    """Get company fundamentals from Tushare (PE, PB, market cap, etc.)."""
    try:
        pro = get_tushare_pro()
        ts_code = normalize_ts_code(ticker)

        # Determine trade_date for daily_basic query
        if curr_date:
            trade_date = convert_date_to_tushare(curr_date)
        else:
            trade_date = datetime.now().strftime("%Y%m%d")

        # Get daily basic metrics (PE, PB, market cap, etc.)
        basic_df = tushare_retry(
            lambda: pro.daily_basic(ts_code=ts_code, trade_date=trade_date)
        )

        # Get stock basic info (name, industry, etc.)
        stock_info = tushare_retry(
            lambda: pro.stock_basic(
                ts_code=ts_code,
                fields="ts_code,name,area,industry,market,list_date,fullname"
            )
        )

        if (basic_df is None or basic_df.empty) and (stock_info is None or stock_info.empty):
            return f"No fundamentals data found for symbol '{ticker}'"

        # Try to get financial indicators for the most recent period
        fina_df = None
        try:
            periods = _get_report_periods("quarterly", curr_date, count=1)
            if periods:
                fina_df = tushare_retry(
                    lambda: pro.fina_indicator(ts_code=ts_code, period=periods[0])
                )
        except Exception:
            pass  # Financial indicators are optional

        # Build output
        header = f"# Company Fundamentals for {ts_code}\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

        fields = []

        # Stock basic info
        if stock_info is not None and not stock_info.empty:
            info = stock_info.iloc[0]
            fields.append(("Name", info.get("name")))
            fields.append(("Full Name", info.get("fullname")))
            fields.append(("Area", info.get("area")))
            fields.append(("Industry", info.get("industry")))
            fields.append(("Market", info.get("market")))
            fields.append(("List Date", info.get("list_date")))

        # Daily basic metrics
        if basic_df is not None and not basic_df.empty:
            basic = basic_df.iloc[0]
            fields.append(("Close Price", basic.get("close")))
            fields.append(("Turnover Rate", basic.get("turnover_rate")))
            fields.append(("Volume Ratio", basic.get("volume_ratio")))
            fields.append(("PE Ratio (TTM)", basic.get("pe_ttm")))
            fields.append(("PE Ratio", basic.get("pe")))
            fields.append(("PB Ratio", basic.get("pb")))
            fields.append(("PS Ratio (TTM)", basic.get("ps_ttm")))
            fields.append(("Total Share", basic.get("total_share")))
            fields.append(("Float Share", basic.get("float_share")))
            fields.append(("Total Market Cap (万元)", basic.get("total_mv")))
            fields.append(("Float Market Cap (万元)", basic.get("circ_mv")))

        # Financial indicators
        if fina_df is not None and not fina_df.empty:
            fina = fina_df.iloc[0]
            fields.append(("ROE", fina.get("roe")))
            fields.append(("ROA", fina.get("roa")))
            fields.append(("Gross Profit Margin", fina.get("grossprofit_margin")))
            fields.append(("Net Profit Margin", fina.get("netprofit_margin")))
            fields.append(("Debt to Asset Ratio", fina.get("debt_to_assets")))
            fields.append(("EPS", fina.get("eps")))
            fields.append(("Revenue YoY (%)", fina.get("revenue_yoy")))
            fields.append(("Net Profit YoY (%)", fina.get("netprofit_yoy")))

        lines = []
        for label, value in fields:
            if value is not None and str(value) != "" and str(value) != "nan":
                lines.append(f"{label}: {value}")

        if not lines:
            return f"No fundamentals data found for symbol '{ticker}'"

        return header + "\n".join(lines)

    except TushareRateLimitError:
        raise
    except Exception as e:
        return f"Error retrieving fundamentals for {ticker}: {str(e)}"


def get_tushare_balance_sheet(
    ticker: Annotated[str, "ticker symbol (e.g. '600000' or '600000.SH')"],
    freq: Annotated[str, "frequency: 'quarterly' or 'annual'"] = "quarterly",
    curr_date: Annotated[str, "current date in YYYY-MM-DD format"] = None,
) -> str:
    """Get balance sheet data from Tushare."""
    try:
        pro = get_tushare_pro()
        ts_code = normalize_ts_code(ticker)
        periods = _get_report_periods(freq, curr_date, count=4)

        if not periods:
            return f"No balance sheet data found for symbol '{ticker}'"

        all_data = []
        for period in periods:
            p = period  # capture for lambda
            df = tushare_retry(
                lambda: pro.balancesheet(ts_code=ts_code, period=p, report_type="1")
            )
            if df is not None and not df.empty:
                all_data.append(df.iloc[0])

        if not all_data:
            return f"No balance sheet data found for symbol '{ticker}'"

        # Build a combined DataFrame with periods as columns
        result_df = pd.DataFrame(all_data).T
        # Use formatted period as column names
        col_names = []
        for row in all_data:
            period_str = str(row.get("end_date", row.get("ann_date", "")))
            col_names.append(convert_date_from_tushare(period_str) if len(period_str) == 8 else period_str)
        result_df.columns = col_names

        # Remove metadata rows
        skip_rows = ["ts_code", "ann_date", "f_ann_date", "end_date", "report_type",
                     "comp_type", "end_type", "update_flag"]
        result_df = result_df.drop(
            [r for r in skip_rows if r in result_df.index], errors="ignore"
        )

        # Remove rows where all values are NaN
        result_df = result_df.dropna(how="all")

        csv_string = result_df.to_csv()

        header = f"# Balance Sheet data for {ts_code} ({freq})\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

        return header + csv_string

    except TushareRateLimitError:
        raise
    except Exception as e:
        return f"Error retrieving balance sheet for {ticker}: {str(e)}"


def get_tushare_cashflow(
    ticker: Annotated[str, "ticker symbol (e.g. '600000' or '600000.SH')"],
    freq: Annotated[str, "frequency: 'quarterly' or 'annual'"] = "quarterly",
    curr_date: Annotated[str, "current date in YYYY-MM-DD format"] = None,
) -> str:
    """Get cash flow statement data from Tushare."""
    try:
        pro = get_tushare_pro()
        ts_code = normalize_ts_code(ticker)
        periods = _get_report_periods(freq, curr_date, count=4)

        if not periods:
            return f"No cash flow data found for symbol '{ticker}'"

        all_data = []
        for period in periods:
            p = period
            df = tushare_retry(
                lambda: pro.cashflow(ts_code=ts_code, period=p, report_type="1")
            )
            if df is not None and not df.empty:
                all_data.append(df.iloc[0])

        if not all_data:
            return f"No cash flow data found for symbol '{ticker}'"

        result_df = pd.DataFrame(all_data).T
        col_names = []
        for row in all_data:
            period_str = str(row.get("end_date", row.get("ann_date", "")))
            col_names.append(convert_date_from_tushare(period_str) if len(period_str) == 8 else period_str)
        result_df.columns = col_names

        skip_rows = ["ts_code", "ann_date", "f_ann_date", "end_date", "report_type",
                     "comp_type", "end_type", "update_flag"]
        result_df = result_df.drop(
            [r for r in skip_rows if r in result_df.index], errors="ignore"
        )
        result_df = result_df.dropna(how="all")

        csv_string = result_df.to_csv()

        header = f"# Cash Flow data for {ts_code} ({freq})\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

        return header + csv_string

    except TushareRateLimitError:
        raise
    except Exception as e:
        return f"Error retrieving cash flow for {ticker}: {str(e)}"


def get_tushare_income_statement(
    ticker: Annotated[str, "ticker symbol (e.g. '600000' or '600000.SH')"],
    freq: Annotated[str, "frequency: 'quarterly' or 'annual'"] = "quarterly",
    curr_date: Annotated[str, "current date in YYYY-MM-DD format"] = None,
) -> str:
    """Get income statement data from Tushare."""
    try:
        pro = get_tushare_pro()
        ts_code = normalize_ts_code(ticker)
        periods = _get_report_periods(freq, curr_date, count=4)

        if not periods:
            return f"No income statement data found for symbol '{ticker}'"

        all_data = []
        for period in periods:
            p = period
            df = tushare_retry(
                lambda: pro.income(ts_code=ts_code, period=p, report_type="1")
            )
            if df is not None and not df.empty:
                all_data.append(df.iloc[0])

        if not all_data:
            return f"No income statement data found for symbol '{ticker}'"

        result_df = pd.DataFrame(all_data).T
        col_names = []
        for row in all_data:
            period_str = str(row.get("end_date", row.get("ann_date", "")))
            col_names.append(convert_date_from_tushare(period_str) if len(period_str) == 8 else period_str)
        result_df.columns = col_names

        skip_rows = ["ts_code", "ann_date", "f_ann_date", "end_date", "report_type",
                     "comp_type", "end_type", "update_flag"]
        result_df = result_df.drop(
            [r for r in skip_rows if r in result_df.index], errors="ignore"
        )
        result_df = result_df.dropna(how="all")

        csv_string = result_df.to_csv()

        header = f"# Income Statement data for {ts_code} ({freq})\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

        return header + csv_string

    except TushareRateLimitError:
        raise
    except Exception as e:
        return f"Error retrieving income statement for {ticker}: {str(e)}"


def get_tushare_insider_transactions(
    ticker: Annotated[str, "ticker symbol (e.g. '600000' or '600000.SH')"],
) -> str:
    """Get insider (shareholder) trading records from Tushare."""
    try:
        pro = get_tushare_pro()
        ts_code = normalize_ts_code(ticker)

        df = tushare_retry(
            lambda: pro.stk_holdertrade(ts_code=ts_code)
        )

        if df is None or df.empty:
            return f"No insider transactions data found for symbol '{ticker}'"

        header = f"# Insider Transactions data for {ts_code}\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

        lines = ["Date,Holder Name,Change Volume,Change Type,Price,Change Reason"]
        for _, row in df.iterrows():
            date_val = str(row.get("ann_date", ""))
            if len(date_val) == 8:
                date_val = convert_date_from_tushare(date_val)
            holder = row.get("holder_name", "")
            vol = row.get("vol", "")
            change_type = row.get("in_de", "")
            price = row.get("price", "")
            reason = row.get("holder_type", "")
            lines.append(f"{date_val},{holder},{vol},{change_type},{price},{reason}")

        return header + "\n".join(lines) + "\n"

    except TushareRateLimitError:
        raise
    except Exception as e:
        return f"Error retrieving insider transactions for {ticker}: {str(e)}"


def get_tushare_news(
    ticker: Annotated[str, "ticker symbol"],
    start_date: Annotated[str, "Start date in YYYY-MM-DD format"],
    end_date: Annotated[str, "End date in YYYY-MM-DD format"],
) -> str:
    """Get news for a specific ticker from the news service."""
    from .news_service import get_news_service_news
    return get_news_service_news(ticker, start_date, end_date)


def get_tushare_global_news(
    curr_date: Annotated[str, "Current date in YYYY-MM-DD format"],
    look_back_days: int = None,
    limit: int = None,
) -> str:
    """Get global market news from the news service."""
    from .news_service import get_news_service_global_news
    return get_news_service_global_news(curr_date, look_back_days, limit)
