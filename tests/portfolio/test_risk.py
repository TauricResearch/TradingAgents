"""
Tests for risk management.
"""

import unittest
from decimal import Decimal

from tradingagents.portfolio import RiskManager, RiskLimits
from tradingagents.portfolio.exceptions import (
    RiskLimitExceededError,
    ValidationError,
    CalculationError,
)


class TestRiskLimits(unittest.TestCase):
    """Test cases for RiskLimits."""

    def test_default_limits(self):
        """Test default risk limits."""
        limits = RiskLimits()

        self.assertEqual(limits.max_position_size, Decimal('0.20'))
        self.assertEqual(limits.max_sector_concentration, Decimal('0.30'))
        self.assertEqual(limits.max_drawdown, Decimal('0.25'))

    def test_custom_limits(self):
        """Test custom risk limits."""
        limits = RiskLimits(
            max_position_size=Decimal('0.15'),
            max_drawdown=Decimal('0.15')
        )

        self.assertEqual(limits.max_position_size, Decimal('0.15'))
        self.assertEqual(limits.max_drawdown, Decimal('0.15'))

    def test_invalid_limits_rejected(self):
        """Test that invalid limits are rejected."""
        with self.assertRaises(ValidationError):
            RiskLimits(max_position_size=Decimal('1.5'))  # Over 1.0

        with self.assertRaises(ValidationError):
            RiskLimits(max_position_size=Decimal('-0.1'))  # Negative


class TestRiskManager(unittest.TestCase):
    """Test cases for RiskManager."""

    def setUp(self):
        """Set up test risk manager."""
        self.risk_manager = RiskManager()

    def test_position_size_check_pass(self):
        """Test position size check that passes."""
        # 10% position size (under 20% limit)
        position_value = Decimal('10000')
        portfolio_value = Decimal('100000')

        # Should not raise
        self.risk_manager.check_position_size_limit(
            position_value, portfolio_value, 'AAPL'
        )

    def test_position_size_check_fail(self):
        """Test position size check that fails."""
        # 30% position size (over 20% limit)
        position_value = Decimal('30000')
        portfolio_value = Decimal('100000')

        with self.assertRaises(RiskLimitExceededError):
            self.risk_manager.check_position_size_limit(
                position_value, portfolio_value, 'AAPL'
            )

    def test_sector_concentration_check_pass(self):
        """Test sector concentration check that passes."""
        sector_exposure = {
            'Technology': Decimal('25000'),  # 25%
            'Healthcare': Decimal('20000'),   # 20%
        }
        portfolio_value = Decimal('100000')

        # Should not raise (under 30% limit)
        self.risk_manager.check_sector_concentration(
            sector_exposure, portfolio_value
        )

    def test_sector_concentration_check_fail(self):
        """Test sector concentration check that fails."""
        sector_exposure = {
            'Technology': Decimal('35000'),  # 35% - over limit
        }
        portfolio_value = Decimal('100000')

        with self.assertRaises(RiskLimitExceededError):
            self.risk_manager.check_sector_concentration(
                sector_exposure, portfolio_value
            )

    def test_drawdown_check_pass(self):
        """Test drawdown check that passes."""
        current_value = Decimal('90000')
        peak_value = Decimal('100000')

        # 10% drawdown (under 25% limit)
        self.risk_manager.check_drawdown_limit(current_value, peak_value)

    def test_drawdown_check_fail(self):
        """Test drawdown check that fails."""
        current_value = Decimal('70000')
        peak_value = Decimal('100000')

        # 30% drawdown (over 25% limit)
        with self.assertRaises(RiskLimitExceededError):
            self.risk_manager.check_drawdown_limit(current_value, peak_value)

    def test_cash_reserve_check_pass(self):
        """Test cash reserve check that passes."""
        cash = Decimal('10000')  # 10%
        portfolio_value = Decimal('100000')

        # Should not raise (over 5% minimum)
        self.risk_manager.check_cash_reserve(cash, portfolio_value)

    def test_cash_reserve_check_fail(self):
        """Test cash reserve check that fails."""
        cash = Decimal('2000')  # 2%
        portfolio_value = Decimal('100000')

        # Should raise (under 5% minimum)
        with self.assertRaises(RiskLimitExceededError):
            self.risk_manager.check_cash_reserve(cash, portfolio_value)

    def test_calculate_position_size(self):
        """Test position size calculation."""
        portfolio_value = Decimal('100000')
        risk_per_trade = Decimal('0.02')  # 2% risk
        entry_price = Decimal('100.00')
        stop_loss_price = Decimal('95.00')

        position_size = self.risk_manager.calculate_position_size(
            portfolio_value, risk_per_trade, entry_price, stop_loss_price
        )

        # Risk per share = $5
        # Max risk = $2000 (2% of $100k)
        # Position size = $2000 / $5 = 400 shares
        self.assertEqual(position_size, Decimal('400'))

    def test_calculate_var(self):
        """Test VaR calculation."""
        returns = [
            Decimal('0.01'),
            Decimal('0.02'),
            Decimal('-0.01'),
            Decimal('-0.02'),
            Decimal('0.015'),
            Decimal('-0.015'),
            Decimal('0.005'),
            Decimal('-0.005'),
        ]

        var = self.risk_manager.calculate_var(returns, Decimal('0.95'))

        # Should return a positive number representing potential loss
        self.assertGreater(var, 0)

    def test_calculate_sharpe_ratio(self):
        """Test Sharpe ratio calculation."""
        returns = [Decimal('0.01')] * 252  # Consistent 1% daily returns

        sharpe = self.risk_manager.calculate_sharpe_ratio(returns)

        # Should be a high positive number (very consistent returns)
        self.assertGreater(sharpe, 0)

    def test_calculate_sortino_ratio(self):
        """Test Sortino ratio calculation."""
        # Mix of positive and negative returns
        returns = [Decimal('0.01'), Decimal('0.02'), Decimal('-0.01')] * 84

        sortino = self.risk_manager.calculate_sortino_ratio(returns)

        # Should be positive (more upside than downside)
        self.assertGreater(sortino, 0)

    def test_calculate_max_drawdown(self):
        """Test max drawdown calculation."""
        equity_curve = [
            Decimal('100000'),
            Decimal('105000'),
            Decimal('110000'),  # Peak
            Decimal('105000'),
            Decimal('95000'),   # Trough (13.6% drawdown)
            Decimal('100000'),
            Decimal('115000'),
        ]

        max_dd, peak_idx, trough_idx = self.risk_manager.calculate_max_drawdown(
            equity_curve
        )

        self.assertGreater(max_dd, 0)
        self.assertEqual(peak_idx, 2)
        self.assertEqual(trough_idx, 4)

    def test_calculate_beta(self):
        """Test beta calculation."""
        portfolio_returns = [Decimal('0.01'), Decimal('0.02'), Decimal('-0.01')] * 10
        benchmark_returns = [Decimal('0.008'), Decimal('0.015'), Decimal('-0.008')] * 10

        beta = self.risk_manager.calculate_beta(portfolio_returns, benchmark_returns)

        # Beta should be around 1.0 (similar volatility to benchmark)
        self.assertGreater(beta, 0)

    def test_calculate_correlation(self):
        """Test correlation calculation."""
        returns1 = [Decimal('0.01'), Decimal('0.02'), Decimal('-0.01')] * 10
        returns2 = [Decimal('0.01'), Decimal('0.02'), Decimal('-0.01')] * 10

        correlation = self.risk_manager.calculate_correlation(returns1, returns2)

        # Perfect correlation
        self.assertAlmostEqual(float(correlation), 1.0, places=1)


if __name__ == '__main__':
    unittest.main()
