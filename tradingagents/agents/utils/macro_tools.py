import yfinance as yf
from langchain_core.tools import tool
import pandas as pd

@tool
def get_macro_data(curr_date: str | None = None) -> str:
    """Fetch macroeconomic indicators (VIX, 10-Year Treasury Yield, Crude Oil, Gold) to understand the market environment."""
    tickers = {
        "^VIX": "Volatility Index (VIX)",
        "^TNX": "10-Year Treasury Yield",
        "CL=F": "Crude Oil",
        "GC=F": "Gold"
    }
    
    from tradingagents.dataflows.stockstats_utils import load_ohlcv
    import pandas as pd
    
    if not curr_date:
        curr_date = pd.Timestamp.today().strftime("%Y-%m-%d")
        
    report = []
    for ticker, name in tickers.items():
        try:
            data = load_ohlcv(ticker, curr_date)
            if len(data) >= 2:
                current = data['Close'].iloc[-1]
                previous = data['Close'].iloc[-2]
                pct_change = ((current - previous) / previous) * 100
                report.append(f"{name} ({ticker}): {current:.2f} (Change: {pct_change:+.2f}%)")
            else:
                report.append(f"{name} ({ticker}): Data unavailable")
        except Exception as e:
            report.append(f"{name} ({ticker}): Error fetching data - {str(e)}")
            
    return "\n".join(report)
