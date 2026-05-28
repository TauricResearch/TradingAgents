import yfinance as yf
import pandas as pd
import numpy as np
from langchain_core.tools import tool

@tool
def get_quant_data(
    ticker: str,
    curr_date: str | None = None
) -> str:
    """Calculate quantitative metrics like Beta, Sharpe Ratio, and Volatility for a given ticker compared to SPY over a 1-year period. You MUST provide the exact stock ticker as the 'ticker' parameter."""
    try:
        from tradingagents.dataflows.stockstats_utils import load_ohlcv
        import pandas as pd
        
        if not curr_date:
            curr_date = pd.Timestamp.today().strftime("%Y-%m-%d")
            
        # Fetch data up to curr_date using cache and avoiding look-ahead bias
        hist = load_ohlcv(ticker, curr_date)
        spy_hist = load_ohlcv("SPY", curr_date)
        
        # Ensure we filter to 1 year back from curr_date
        curr_date_dt = pd.to_datetime(curr_date)
        one_year_ago = curr_date_dt - pd.DateOffset(years=1)
        
        hist = hist[hist['Date'] >= one_year_ago]
        spy_hist = spy_hist[spy_hist['Date'] >= one_year_ago]
        
        if len(hist) < 20 or len(spy_hist) < 20:
            return f"Not enough historical data to calculate quant metrics for {ticker}."
            
        # Set Date as index for joining
        hist_indexed = hist.set_index('Date')
        spy_indexed = spy_hist.set_index('Date')
            
        # Ensure dates align
        data = pd.DataFrame({
            'Stock': hist_indexed['Close'],
            'SPY': spy_indexed['Close']
        }).dropna()
        
        # Calculate daily returns
        returns = data.pct_change().dropna()
        
        # Volatility (Annualized standard deviation)
        # 252 trading days in a year
        stock_volatility = returns['Stock'].std() * np.sqrt(252)
        spy_volatility = returns['SPY'].std() * np.sqrt(252)
        
        # Beta
        covariance = returns['Stock'].cov(returns['SPY'])
        spy_variance = returns['SPY'].var()
        beta = covariance / spy_variance if spy_variance > 0 else 0
        
        # Risk-free rate (approx 4%)
        rf = 0.04
        daily_rf = rf / 252
        
        # Sharpe Ratio (Annualized)
        excess_returns = returns['Stock'] - daily_rf
        sharpe = (excess_returns.mean() / excess_returns.std()) * np.sqrt(252) if excess_returns.std() > 0 else 0
        
        # Correlation
        correlation = returns['Stock'].corr(returns['SPY'])
        
        report = [
            f"Quantitative Metrics for {ticker} (1-Year):",
            f"- Beta: {beta:.2f} (vs SPY)",
            f"- Annualized Volatility: {stock_volatility:.2%} (SPY: {spy_volatility:.2%})",
            f"- Sharpe Ratio: {sharpe:.2f}",
            f"- Correlation with SPY: {correlation:.2f}"
        ]
        
        return "\n".join(report)
    except Exception as e:
        return f"Error calculating quant data for {ticker}: {str(e)}"
