"""Market data tools for the Market Analyst agent.

These are plain Python functions that Google ADK wraps as FunctionTools.
ADK agents call these automatically when they decide to use a tool.
"""

import json
from datetime import datetime, timedelta

try:
    import yfinance as yf
    import pandas as pd
except ImportError:
    yf = None
    pd = None


def get_stock_data(symbol: str, start_date: str, end_date: str) -> str:
    """Retrieve stock price data (OHLCV) for a given ticker symbol.

    Args:
        symbol: Ticker symbol of the company, e.g. AAPL, NVDA, TSM
        start_date: Start date in yyyy-mm-dd format
        end_date: End date in yyyy-mm-dd format

    Returns:
        A formatted string containing the stock price data (Open, High, Low,
        Close, Volume) for the specified ticker in the given date range.
    """
    if yf is None:
        return f"[Mock] Stock data for {symbol} from {start_date} to {end_date}: Price ~$150, Volume ~50M"

    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(start=start_date, end=end_date)
        if df.empty:
            return f"No stock data found for {symbol} between {start_date} and {end_date}"
        df_str = df[["Open", "High", "Low", "Close", "Volume"]].to_string()
        return f"Stock data for {symbol} ({start_date} to {end_date}):\n{df_str}"
    except Exception as e:
        return f"Error fetching stock data for {symbol}: {e}"


def get_technical_indicators(symbol: str, start_date: str, end_date: str, indicators: list[str]) -> str:
    """Calculate technical indicators for a given stock.

    Args:
        symbol: Ticker symbol of the company
        start_date: Start date in yyyy-mm-dd format
        end_date: End date in yyyy-mm-dd format
        indicators: List of indicator names to calculate. Options include:
            rsi, macd, boll_ub, boll_lb, close_50_sma, close_200_sma,
            close_10_ema, atr, vwma

    Returns:
        A formatted string with the requested technical indicators.
    """
    if yf is None or pd is None:
        return f"[Mock] Technical indicators for {symbol}: RSI=55, MACD=1.2, SMA50=$148"

    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(start=start_date, end=end_date)
        if df.empty:
            return f"No data found for {symbol}"

        results = {}
        close = df["Close"]

        for ind in indicators:
            ind = ind.lower().strip()
            if ind == "rsi":
                delta = close.diff()
                gain = delta.where(delta > 0, 0).rolling(14).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
                rs = gain / loss
                results["RSI"] = (100 - 100 / (1 + rs)).iloc[-1]
            elif ind == "close_50_sma":
                results["SMA_50"] = close.rolling(50).mean().iloc[-1]
            elif ind == "close_200_sma":
                results["SMA_200"] = close.rolling(200).mean().iloc[-1]
            elif ind == "close_10_ema":
                results["EMA_10"] = close.ewm(span=10).mean().iloc[-1]
            elif ind == "macd":
                ema12 = close.ewm(span=12).mean()
                ema26 = close.ewm(span=26).mean()
                macd_line = ema12 - ema26
                results["MACD"] = macd_line.iloc[-1]
                results["MACD_Signal"] = macd_line.ewm(span=9).mean().iloc[-1]
            elif ind == "atr":
                high = df["High"]
                low = df["Low"]
                prev_close = close.shift(1)
                tr = pd.concat([
                    high - low,
                    (high - prev_close).abs(),
                    (low - prev_close).abs()
                ], axis=1).max(axis=1)
                results["ATR"] = tr.rolling(14).mean().iloc[-1]
            elif ind in ("boll_ub", "boll_lb"):
                sma20 = close.rolling(20).mean()
                std20 = close.rolling(20).std()
                if ind == "boll_ub":
                    results["Bollinger_Upper"] = (sma20 + 2 * std20).iloc[-1]
                else:
                    results["Bollinger_Lower"] = (sma20 - 2 * std20).iloc[-1]

        lines = [f"Technical Indicators for {symbol} (as of {end_date}):"]
        for name, value in results.items():
            if isinstance(value, float):
                lines.append(f"  {name}: {value:.4f}")
            else:
                lines.append(f"  {name}: {value}")

        return "\n".join(lines)
    except Exception as e:
        return f"Error calculating indicators for {symbol}: {e}"
