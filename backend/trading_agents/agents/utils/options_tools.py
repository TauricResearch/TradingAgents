import yfinance as yf
from langchain_core.tools import tool

@tool
def get_options_data(ticker: str) -> str:
    """Fetch options chain data for the given ticker, including put/call ratios and implied volatility for near-term expirations. You MUST provide the exact stock ticker as the 'ticker' parameter."""
    try:
        tkr = yf.Ticker(ticker)
        expirations = tkr.options
        if not expirations:
            return f"No options data available for {ticker}."
            
        # Get the two nearest expirations
        nearest_exps = expirations[:2]
        report = []
        
        for exp in nearest_exps:
            chain = tkr.option_chain(exp)
            calls = chain.calls
            puts = chain.puts
            
            call_vol = calls['volume'].sum() if 'volume' in calls else 0
            put_vol = puts['volume'].sum() if 'volume' in puts else 0
            
            # Prevent division by zero
            pc_ratio = put_vol / call_vol if call_vol > 0 else float('inf')
            
            # Average Implied Volatility
            call_iv = calls['impliedVolatility'].mean() if 'impliedVolatility' in calls else 0
            put_iv = puts['impliedVolatility'].mean() if 'impliedVolatility' in puts else 0
            
            report.append(f"Expiration: {exp}")
            report.append(f"- Call Volume: {call_vol}, Put Volume: {put_vol}")
            report.append(f"- Put/Call Ratio: {pc_ratio:.2f}")
            report.append(f"- Avg Call IV: {call_iv:.2%}, Avg Put IV: {put_iv:.2%}")
            
        return "\n".join(report)
    except Exception as e:
        return f"Error fetching options data for {ticker}: {str(e)}"
