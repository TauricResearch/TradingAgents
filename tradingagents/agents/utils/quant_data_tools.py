import logging
from datetime import datetime, timedelta
from typing import Annotated

import numpy as np
import yfinance as yf
from dateutil.relativedelta import relativedelta
from langchain_core.tools import tool

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
        # `scipy` is an optional dependency (pip install "tradingagents[analytics]").
        # Import lazily so a missing wheel degrades this one tool instead of
        # breaking import of the whole package.
        from scipy import stats
    except ImportError:
        return (
            "Quantitative metrics unavailable: the optional 'scipy' dependency is not "
            "installed. Install it with: pip install \"tradingagents[analytics]\"."
        )
    try:
        symbol = normalize_symbol(ticker)
        # Fetch 1 year ending at curr_date for robust statistics. Bound the
        # request by explicit start/end: yfinance only honours `end` when
        # `start` is given (a bare `period=` ignores `end` and returns data up
        # to *today*, leaking future prices into a backtest). `end` is
        # exclusive, so add a day to include curr_date.
        end_dt = datetime.strptime(curr_date, "%Y-%m-%d")
        start = (end_dt - relativedelta(years=1)).strftime("%Y-%m-%d")
        end_inclusive = (end_dt + timedelta(days=1)).strftime("%Y-%m-%d")
        df = yf.Ticker(symbol).history(start=start, end=end_inclusive)
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
