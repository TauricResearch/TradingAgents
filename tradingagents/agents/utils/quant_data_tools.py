import logging
from typing import Annotated
import numpy as np

import yfinance as yf
from langchain_core.tools import tool
import scipy.stats as stats

from tradingagents.dataflows.symbol_utils import normalize_symbol

logger = logging.getLogger(__name__)

@tool
def get_quantitative_metrics(
    ticker: Annotated[str, "ticker symbol"],
    curr_date: Annotated[str, "current trading date, yyyy-mm-dd"]
) -> str:
    """
    Computes quantitative and statistical risk metrics including Value at Risk (VaR), 
    Expected Shortfall (ES), Annualized Volatility, and Sharpe Ratio over the past year.
    """
    try:
        symbol = normalize_symbol(ticker)
        # Fetch 1 year of data for robust statistical metrics
        df = yf.Ticker(symbol).history(end=curr_date, period="1y")
        if len(df) < 20:
            return f"Not enough price data found for {ticker} up to {curr_date}."
        
        returns = df['Close'].pct_change().dropna()
        
        # Volatility
        daily_vol = returns.std()
        annual_vol = daily_vol * np.sqrt(252)
        
        # VaR and Expected Shortfall (95% confidence)
        var_95 = np.percentile(returns, 5)
        es_95 = returns[returns <= var_95].mean()
        
        # Sharpe Ratio (assuming 0% risk-free rate for simplicity)
        annual_return = returns.mean() * 252
        sharpe_ratio = annual_return / annual_vol if annual_vol != 0 else 0
        
        report = f"### Quantitative Risk Metrics for {ticker} as of {curr_date} (1-Year Lookback)\n\n"
        report += f"- **Annualized Volatility**: {annual_vol:.2%}\n"
        report += f"- **Daily Value at Risk (95%)**: {var_95:.2%}\n"
        report += f"- **Expected Shortfall (95%)**: {es_95:.2%}\n"
        report += f"- **Annualized Return**: {annual_return:.2%}\n"
        report += f"- **Sharpe Ratio**: {sharpe_ratio:.2f}\n"
        report += f"- **Skewness**: {stats.skew(returns):.2f}\n"
        report += f"- **Kurtosis**: {stats.kurtosis(returns):.2f}\n"
        
        return report
    except Exception as e:
        logger.error(f"Error computing quant metrics: {e}")
        return f"Error computing quant metrics: {e}"
