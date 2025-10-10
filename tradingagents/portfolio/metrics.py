"""Portfolio metrics calculation utilities."""
import numpy as np
import pandas as pd
import yfinance as yf
from typing import Dict, List, Tuple, Optional
from datetime import datetime, timedelta
from tradingagents.portfolio.models import Portfolio


def fetch_historical_prices(
    tickers: List[str],
    end_date: str,
    days: int = 252
) -> pd.DataFrame:
    """
    Fetch historical prices for multiple tickers.

    Args:
        tickers: List of ticker symbols
        end_date: End date for historical data (YYYY-MM-DD)
        days: Number of days of historical data to fetch

    Returns:
        DataFrame with adjusted close prices for each ticker
    """
    end = datetime.strptime(end_date, '%Y-%m-%d')
    start = end - timedelta(days=days)

    data = yf.download(
        tickers,
        start=start.strftime('%Y-%m-%d'),
        end=end.strftime('%Y-%m-%d'),
        progress=False
    )

    # Handle single ticker vs multiple tickers
    if len(tickers) == 1:
        prices = data['Adj Close'].to_frame()
        prices.columns = tickers
    else:
        prices = data['Adj Close']

    return prices


def calculate_returns(prices: pd.DataFrame) -> pd.DataFrame:
    """Calculate daily returns from price data."""
    return prices.pct_change().dropna()


def calculate_correlation_matrix(returns: pd.DataFrame) -> pd.DataFrame:
    """Calculate correlation matrix for portfolio holdings."""
    return returns.corr()


def calculate_portfolio_beta(
    portfolio_returns: pd.Series,
    market_returns: pd.Series
) -> float:
    """
    Calculate portfolio beta relative to market.

    Args:
        portfolio_returns: Daily returns of the portfolio
        market_returns: Daily returns of the market (e.g., SPY)

    Returns:
        Portfolio beta
    """
    # Align the series
    aligned = pd.concat([portfolio_returns, market_returns], axis=1, join='inner')
    aligned.columns = ['portfolio', 'market']

    covariance = aligned['portfolio'].cov(aligned['market'])
    market_variance = aligned['market'].var()

    beta = covariance / market_variance
    return float(beta)


def calculate_sharpe_ratio(
    returns: pd.Series,
    risk_free_rate: float = 0.04
) -> float:
    """
    Calculate annualized Sharpe ratio.

    Args:
        returns: Daily returns
        risk_free_rate: Annual risk-free rate (default 4%)

    Returns:
        Annualized Sharpe ratio
    """
    # Annualize returns and volatility
    annual_return = returns.mean() * 252
    annual_vol = returns.std() * np.sqrt(252)

    if annual_vol == 0:
        return 0.0

    sharpe = (annual_return - risk_free_rate) / annual_vol
    return float(sharpe)


def calculate_portfolio_volatility(returns: pd.Series) -> float:
    """
    Calculate annualized portfolio volatility.

    Args:
        returns: Daily returns

    Returns:
        Annualized volatility (standard deviation)
    """
    return float(returns.std() * np.sqrt(252))


def get_sector_allocation(tickers: List[str]) -> Dict[str, Dict[str, float]]:
    """
    Get sector allocation for portfolio tickers.

    Args:
        tickers: List of ticker symbols

    Returns:
        Dictionary mapping tickers to sector and industry
    """
    sector_data = {}

    for ticker in tickers:
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            sector_data[ticker] = {
                'sector': info.get('sector', 'Unknown'),
                'industry': info.get('industry', 'Unknown'),
            }
        except Exception as e:
            print(f"Warning: Could not fetch sector data for {ticker}: {e}")
            sector_data[ticker] = {
                'sector': 'Unknown',
                'industry': 'Unknown',
            }

    return sector_data


def calculate_diversification_score(correlation_matrix: pd.DataFrame) -> float:
    """
    Calculate portfolio diversification score.

    A score closer to 1 indicates better diversification (low correlation).
    A score closer to 0 indicates poor diversification (high correlation).

    Args:
        correlation_matrix: Correlation matrix of portfolio returns

    Returns:
        Diversification score between 0 and 1
    """
    # Get average correlation excluding diagonal
    n = len(correlation_matrix)
    if n <= 1:
        return 1.0

    # Sum all correlations and subtract diagonal (which is all 1s)
    total_corr = correlation_matrix.sum().sum() - n
    # Average correlation between different assets
    avg_corr = total_corr / (n * (n - 1))

    # Convert to diversification score (inverse of average correlation)
    # High correlation = low diversification
    diversification_score = 1 - avg_corr

    return float(max(0, min(1, diversification_score)))


def calculate_portfolio_metrics(portfolio: Portfolio) -> Dict:
    """
    Calculate comprehensive portfolio metrics.

    Args:
        portfolio: Portfolio object with positions

    Returns:
        Dictionary of portfolio metrics
    """
    tickers = portfolio.tickers

    if len(tickers) == 0:
        return {}

    try:
        # Fetch historical data
        prices = fetch_historical_prices(tickers, portfolio.analysis_date)
        returns = calculate_returns(prices)

        # Calculate portfolio returns (weighted by position value)
        weights = portfolio.get_position_weights()
        weight_array = np.array([weights[ticker] / 100 for ticker in tickers])
        portfolio_returns = (returns * weight_array).sum(axis=1)

        # Correlation matrix
        correlation_matrix = calculate_correlation_matrix(returns)

        # Fetch market data (SPY as proxy)
        market_prices = fetch_historical_prices(['SPY'], portfolio.analysis_date)
        market_returns = calculate_returns(market_prices)['SPY']

        # Calculate metrics
        metrics = {
            'correlation_matrix': correlation_matrix.to_dict(),
            'portfolio_beta': calculate_portfolio_beta(portfolio_returns, market_returns),
            'portfolio_volatility': calculate_portfolio_volatility(portfolio_returns),
            'sharpe_ratio': calculate_sharpe_ratio(portfolio_returns),
            'diversification_score': calculate_diversification_score(correlation_matrix),
            'annualized_return': float(portfolio_returns.mean() * 252),
            'max_drawdown': float((portfolio_returns.cumsum().expanding().max() -
                                  portfolio_returns.cumsum()).max()),
        }

        # Add sector allocation
        sector_data = get_sector_allocation(tickers)
        metrics['sector_allocation'] = sector_data

        # Calculate sector concentration
        sectors = {}
        for ticker, data in sector_data.items():
            sector = data['sector']
            weight = weights[ticker]
            sectors[sector] = sectors.get(sector, 0) + weight
        metrics['sector_weights'] = sectors

        return metrics

    except Exception as e:
        print(f"Error calculating portfolio metrics: {e}")
        return {
            'error': str(e),
            'sector_allocation': get_sector_allocation(tickers)
        }
