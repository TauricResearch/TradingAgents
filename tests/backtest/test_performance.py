"""
Tests for the PerformanceAnalyzer class.
"""

import pytest
from decimal import Decimal
import pandas as pd
import numpy as np

from tradingagents.backtest.performance import PerformanceAnalyzer
from tradingagents.backtest.exceptions import InsufficientDataError


@pytest.fixture
def analyzer():
    """Create performance analyzer."""
    return PerformanceAnalyzer(risk_free_rate=Decimal("0.02"))


@pytest.fixture
def sample_equity_curve():
    """Create sample equity curve."""
    dates = pd.date_range(start='2022-01-01', end='2022-12-31', freq='D')
    np.random.seed(42)
    returns = np.random.normal(0.0005, 0.02, len(dates))
    values = 100000 * np.exp(np.cumsum(returns))

    return pd.Series(values, index=dates)


@pytest.fixture
def sample_trades():
    """Create sample trades."""
    return pd.DataFrame({
        'ticker': ['AAPL'] * 10,
        'pnl': np.random.normal(100, 500, 10),
        'timestamp': pd.date_range(start='2022-01-01', periods=10, freq='M'),
    })


def test_analyzer_initialization(analyzer):
    """Test analyzer initialization."""
    assert analyzer is not None
    assert analyzer.risk_free_rate == 0.02


def test_total_return_calculation(analyzer, sample_equity_curve):
    """Test total return calculation."""
    total_return = analyzer._calculate_total_return(sample_equity_curve)

    assert isinstance(total_return, float)
    assert total_return >= -1.0  # Can't lose more than 100%


def test_volatility_calculation(analyzer, sample_equity_curve):
    """Test volatility calculation."""
    returns = sample_equity_curve.pct_change().dropna()
    volatility = analyzer._calculate_volatility(returns)

    assert isinstance(volatility, float)
    assert volatility >= 0


def test_sharpe_ratio_calculation(analyzer, sample_equity_curve):
    """Test Sharpe ratio calculation."""
    returns = sample_equity_curve.pct_change().dropna()
    volatility = analyzer._calculate_volatility(returns)
    sharpe = analyzer._calculate_sharpe_ratio(returns, volatility)

    assert isinstance(sharpe, float)


def test_max_drawdown_calculation(analyzer, sample_equity_curve):
    """Test maximum drawdown calculation."""
    drawdowns = analyzer._calculate_drawdowns(sample_equity_curve)
    max_dd = analyzer._calculate_max_drawdown(drawdowns)

    assert isinstance(max_dd, float)
    assert max_dd <= 0  # Drawdown should be negative


def test_trade_statistics(analyzer, sample_trades):
    """Test trade statistics calculation."""
    stats = analyzer._calculate_trade_statistics(sample_trades)

    assert 'total_trades' in stats
    assert 'winning_trades' in stats
    assert 'losing_trades' in stats
    assert 'win_rate' in stats

    assert stats['total_trades'] == len(sample_trades)
    assert 0 <= stats['win_rate'] <= 1


def test_insufficient_data_error(analyzer):
    """Test that insufficient data raises error."""
    empty_series = pd.Series([])

    with pytest.raises(InsufficientDataError):
        analyzer.analyze(empty_series, pd.DataFrame())


def test_monthly_returns(analyzer, sample_equity_curve):
    """Test monthly returns calculation."""
    monthly_returns = analyzer.calculate_monthly_returns(sample_equity_curve)

    assert isinstance(monthly_returns, pd.DataFrame)
    assert not monthly_returns.empty


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
