import logging
from typing import Annotated

import pandas as pd
import yfinance as yf
from langchain_core.tools import tool
from ta import add_all_ta_features
from ta.utils import dropna

from tradingagents.dataflows.symbol_utils import normalize_symbol

logger = logging.getLogger(__name__)

@tool
def get_technical_indicators(
    ticker: Annotated[str, "ticker symbol"],
    curr_date: Annotated[str, "current trading date, yyyy-mm-dd"]
) -> str:
    """
    Computes a comprehensive suite of Technical Analysis indicators (Momentum, Volatility, Trend, Volume) 
    using the 'ta' library. Returns the latest values for RSI, MACD, Bollinger Bands, ATR, ADX, CCI, and OBV.
    """
    try:
        symbol = normalize_symbol(ticker)
        # Fetch 6 months to ensure moving averages have enough data to compute
        df = yf.Ticker(symbol).history(end=curr_date, period="6mo")
        if df.empty:
            return f"No price data found for {ticker} up to {curr_date}."
        df = df[['Open', 'High', 'Low', 'Close', 'Volume']].copy()
        df = dropna(df)
        df = add_all_ta_features(
            df, open="Open", high="High", low="Low", close="Close", volume="Volume", fillna=True
        )
        
        last_row = df.iloc[-1]
        
        report = f"### Technical Indicators for {ticker} as of {curr_date}\n\n"
        report += f"- **Close Price**: {last_row['Close']:.2f}\n"
        report += f"- **RSI (14)**: {last_row['momentum_rsi']:.2f} (Over 70 is overbought, under 30 is oversold)\n"
        report += f"- **MACD**: {last_row['trend_macd']:.2f} (Signal: {last_row['trend_macd_signal']:.2f})\n"
        report += f"- **Bollinger Bands**: Upper={last_row['volatility_bbh']:.2f}, Lower={last_row['volatility_bbl']:.2f}\n"
        report += f"- **ATR (Average True Range)**: {last_row['volatility_atr']:.2f}\n"
        report += f"- **ADX (Trend Strength)**: {last_row['trend_adx']:.2f}\n"
        report += f"- **CCI (Commodity Channel Index)**: {last_row['trend_cci']:.2f}\n"
        report += f"- **OBV (On-Balance Volume)**: {last_row['volume_obv']:.0f}\n"
        
        return report
    except Exception as e:
        logger.error(f"Error computing technical indicators: {e}")
        return f"Error computing technical indicators: {e}"
