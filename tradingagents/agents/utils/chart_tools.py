# TradingAgents/tradingagents/agents/utils/chart_tools.py
#
# Multimodal chart generation for the Market Analyst.
# Renders candlestick + volume charts via mplfinance and returns the
# image as a base64-encoded PNG for injection into vision-capable LLMs.
#
# This gives the Market Analyst a visual "tape reading" capability
# that complements the numeric indicator data. Vision models can spot
# patterns (head-and-shoulders, flags, gaps) that pure OHLCV columns miss.

import base64
import io
import logging
from typing import Annotated

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

# mplfinance is optional — degrade gracefully to text-only
try:
    import mplfinance as mpf
    import pandas as pd

    _HAS_MPLFINANCE = True
except ImportError:
    _HAS_MPLFINANCE = False


@tool
def generate_chart(
    symbol: Annotated[str, "Ticker symbol, e.g. AAPL"],
    curr_date: Annotated[str, "The current trading date, YYYY-mm-dd"],
    look_back_days: Annotated[int, "Number of trading days to include"] = 60,
    style: Annotated[str, "mplfinance style name"] = "charles",
) -> str:
    """Generate a candlestick chart with volume overlay for visual analysis.

    Returns a base64-encoded PNG image that can be passed to vision-capable
    models for pattern recognition (support/resistance, gaps, head-and-shoulders,
    channels, etc.).

    If mplfinance is not installed, falls back to a text summary of the
    price range and trend direction.

    Args:
        symbol: Ticker symbol (e.g., AAPL, TSLA, NVDA)
        curr_date: Current trading date in YYYY-mm-dd format
        look_back_days: How many trading days of history to chart (default 60)
        style: mplfinance chart style (default "charles")

    Returns:
        str: Either a base64-encoded PNG (prefixed with "data:image/png;base64,")
             or a text fallback if mplfinance is unavailable.
    """
    from tradingagents.dataflows.interface import route_to_vendor
    from datetime import datetime, timedelta

    # Calculate start date
    end_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    # Request extra calendar days to account for weekends/holidays
    start_dt = end_dt - timedelta(days=int(look_back_days * 1.6))
    start_date = start_dt.strftime("%Y-%m-%d")

    # Fetch OHLCV data via the existing vendor routing
    raw_data = route_to_vendor("get_stock_data", symbol, start_date, curr_date)

    if not _HAS_MPLFINANCE:
        return (
            f"[Chart unavailable — mplfinance not installed. "
            f"Install with: pip install mplfinance]\n\n"
            f"Raw price data for visual context:\n{raw_data[:2000]}"
        )

    # Parse the CSV/text data into a DataFrame
    try:
        df = _parse_ohlcv(raw_data)
    except Exception as e:
        logger.warning("Failed to parse OHLCV for chart generation: %s", e)
        return f"[Chart generation failed: {e}]\n\nRaw data:\n{raw_data[:2000]}"

    if df.empty or len(df) < 5:
        return f"[Insufficient data for chart — only {len(df)} bars]\n\n{raw_data[:2000]}"

    # Trim to the requested lookback window
    df = df.tail(look_back_days)

    # Render the chart to a PNG buffer
    buf = io.BytesIO()
    try:
        mpf.plot(
            df,
            type="candle",
            volume=True,
            style=style,
            title=f"\n{symbol} — {look_back_days}d",
            figsize=(12, 7),
            savefig=dict(fname=buf, dpi=120, bbox_inches="tight"),
            warn_too_much_data=9999,
        )
    except Exception as e:
        logger.warning("mplfinance render failed: %s", e)
        return f"[Chart render error: {e}]\n\nRaw data:\n{raw_data[:2000]}"

    buf.seek(0)
    b64 = base64.b64encode(buf.read()).decode("utf-8")
    return f"data:image/png;base64,{b64}"


def _parse_ohlcv(raw_text: str) -> "pd.DataFrame":
    """Parse the text output from get_stock_data into a mplfinance-ready DataFrame.

    Handles both CSV-style and the formatted table outputs from yfinance/alpha_vantage
    vendors. The DataFrame must have a DatetimeIndex and columns: Open, High, Low,
    Close, Volume.
    """
    import pandas as pd

    # Try CSV parse first
    try:
        df = pd.read_csv(io.StringIO(raw_text), parse_dates=True, index_col=0)
    except Exception:
        # Try tab-separated or whitespace-delimited
        df = pd.read_csv(
            io.StringIO(raw_text),
            sep=r"\s+",
            parse_dates=True,
            index_col=0,
        )

    # Normalize column names to title case
    col_map = {}
    for col in df.columns:
        lower = col.lower().strip()
        if "open" in lower:
            col_map[col] = "Open"
        elif "high" in lower:
            col_map[col] = "High"
        elif "low" in lower:
            col_map[col] = "Low"
        elif "close" in lower and "adj" not in lower:
            col_map[col] = "Close"
        elif "volume" in lower:
            col_map[col] = "Volume"

    df = df.rename(columns=col_map)

    required_cols = ["Open", "High", "Low", "Close", "Volume"]
    missing = set(required_cols) - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    df.index = pd.to_datetime(df.index)
    df = df.sort_index()
    df = df[required_cols].apply(pd.to_numeric, errors="coerce").dropna()

    return df
