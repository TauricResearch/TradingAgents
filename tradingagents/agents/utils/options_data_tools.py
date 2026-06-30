import logging
from typing import Annotated

import yfinance as yf
from langchain_core.tools import tool

from tradingagents.dataflows.symbol_utils import normalize_symbol

logger = logging.getLogger(__name__)

@tool
def get_options_chain_metrics(
    ticker: Annotated[str, "ticker symbol"]
) -> str:
    """
    Fetches the nearest expiration options chain and computes the Put/Call Ratio and Implied Volatility skew.
    Note: Options data is live and cannot easily be backdated to curr_date.
    """
    try:
        symbol = normalize_symbol(ticker)
        tk = yf.Ticker(symbol)
        
        expirations = tk.options
        if not expirations:
            return f"No options data available for {ticker}."
            
        nearest_expiry = expirations[0]
        chain = tk.option_chain(nearest_expiry)
        
        calls = chain.calls
        puts = chain.puts
        
        total_call_vol = calls['volume'].sum() if 'volume' in calls.columns else 0
        total_put_vol = puts['volume'].sum() if 'volume' in puts.columns else 0
        
        total_call_oi = calls['openInterest'].sum() if 'openInterest' in calls.columns else 0
        total_put_oi = puts['openInterest'].sum() if 'openInterest' in puts.columns else 0
        
        pc_vol_ratio = total_put_vol / total_call_vol if total_call_vol > 0 else 0
        pc_oi_ratio = total_put_oi / total_call_oi if total_call_oi > 0 else 0
        
        avg_call_iv = calls['impliedVolatility'].mean() if 'impliedVolatility' in calls.columns else 0
        avg_put_iv = puts['impliedVolatility'].mean() if 'impliedVolatility' in puts.columns else 0
        
        report = f"### Options & Volatility Metrics for {ticker}\n\n"
        report += f"**Nearest Expiration**: {nearest_expiry}\n"
        report += f"- **Put/Call Volume Ratio**: {pc_vol_ratio:.2f}\n"
        report += f"- **Put/Call Open Interest Ratio**: {pc_oi_ratio:.2f}\n"
        report += f"- **Average Call Implied Volatility**: {avg_call_iv:.2%}\n"
        report += f"- **Average Put Implied Volatility**: {avg_put_iv:.2%}\n"
        report += "\n*Note: High put/call ratios may indicate bearish sentiment, while elevated IV suggests expected upcoming volatility.*"
        
        return report
    except Exception as e:
        logger.error(f"Error computing options metrics: {e}")
        return f"Error computing options metrics: {e}"
