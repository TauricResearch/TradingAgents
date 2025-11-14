"""
Tests for performance analytics.
"""

import unittest
from decimal import Decimal
from datetime import datetime, timedelta

from tradingagents.portfolio import PerformanceAnalytics, TradeRecord
from tradingagents.portfolio.exceptions import ValidationError, CalculationError


class TestPerformanceAnalytics(unittest.TestCase):
    """Test cases for PerformanceAnalytics."""

    def setUp(self):
        """Set up test analytics."""
        self.analytics = PerformanceAnalytics()

    def test_calculate_returns(self):
        """Test returns calculation from equity curve."""
        equity_curve = [
            (datetime(2024, 1, 1), Decimal('100000')),
            (datetime(2024, 1, 2), Decimal('101000')),
            (datetime(2024, 1, 3), Decimal('102000')),
        ]

        returns = self.analytics.calculate_returns(equity_curve)

        self.assertEqual(len(returns), 2)
        # First return: (101000 - 100000) / 100000 = 0.01
        self.assertEqual(returns[0], Decimal('0.01'))

    def test_calculate_total_return(self):
        """Test total return calculation."""
        initial = Decimal('100000')
        final = Decimal('120000')

        total_return = self.analytics.calculate_total_return(initial, final)

        # (120000 - 100000) / 100000 = 0.20 (20%)
        self.assertEqual(total_return, Decimal('0.20'))

    def test_calculate_annualized_return(self):
        """Test annualized return calculation."""
        total_return = Decimal('0.20')  # 20% total
        days = 365  # Over one year

        annualized = self.analytics.calculate_annualized_return(total_return, days)

        # Should be approximately 20% for one year
        self.assertAlmostEqual(float(annualized), 0.20, places=2)

    def test_calculate_volatility(self):
        """Test volatility calculation."""
        # Create some returns with variation
        returns = [Decimal('0.01'), Decimal('-0.01'), Decimal('0.02')] * 84  # 252 days

        volatility = self.analytics.calculate_volatility(returns)

        # Should be a positive number
        self.assertGreater(volatility, 0)

    def test_calculate_trade_statistics_empty(self):
        """Test trade statistics with no trades."""
        stats = self.analytics.calculate_trade_statistics([])

        self.assertEqual(stats['total_trades'], 0)
        self.assertEqual(stats['win_rate'], Decimal('0'))

    def test_calculate_trade_statistics_with_trades(self):
        """Test trade statistics with trades."""
        trades = [
            TradeRecord(
                ticker='AAPL',
                entry_date=datetime(2024, 1, 1),
                exit_date=datetime(2024, 1, 10),
                entry_price=Decimal('150'),
                exit_price=Decimal('160'),
                quantity=Decimal('100'),
                pnl=Decimal('1000'),
                pnl_percent=Decimal('0.067'),
                commission=Decimal('15'),
                holding_period=9,
                is_win=True
            ),
            TradeRecord(
                ticker='GOOGL',
                entry_date=datetime(2024, 1, 5),
                exit_date=datetime(2024, 1, 15),
                entry_price=Decimal('2000'),
                exit_price=Decimal('1950'),
                quantity=Decimal('50'),
                pnl=Decimal('-2500'),
                pnl_percent=Decimal('-0.025'),
                commission=Decimal('100'),
                holding_period=10,
                is_win=False
            ),
        ]

        stats = self.analytics.calculate_trade_statistics(trades)

        self.assertEqual(stats['total_trades'], 2)
        self.assertEqual(stats['winning_trades'], 1)
        self.assertEqual(stats['losing_trades'], 1)
        self.assertEqual(stats['win_rate'], Decimal('0.5'))
        self.assertGreater(stats['average_win'], 0)
        self.assertGreater(stats['average_loss'], 0)

    def test_generate_performance_metrics(self):
        """Test comprehensive performance metrics generation."""
        # Create sample equity curve
        base_date = datetime(2024, 1, 1)
        equity_curve = [
            (base_date + timedelta(days=i), Decimal('100000') + Decimal(i * 100))
            for i in range(30)
        ]

        # Create sample trades
        trades = [
            TradeRecord(
                ticker='AAPL',
                entry_date=datetime(2024, 1, 1),
                exit_date=datetime(2024, 1, 10),
                entry_price=Decimal('150'),
                exit_price=Decimal('160'),
                quantity=Decimal('100'),
                pnl=Decimal('1000'),
                pnl_percent=Decimal('0.067'),
                commission=Decimal('15'),
                holding_period=9,
                is_win=True
            ),
        ]

        metrics = self.analytics.generate_performance_metrics(
            equity_curve,
            trades,
            Decimal('100000')
        )

        self.assertIsNotNone(metrics.total_return)
        self.assertIsNotNone(metrics.sharpe_ratio)
        self.assertIsNotNone(metrics.max_drawdown)
        self.assertEqual(metrics.total_trades, 1)

    def test_calculate_monthly_returns(self):
        """Test monthly returns calculation."""
        equity_curve = [
            (datetime(2024, 1, 1), Decimal('100000')),
            (datetime(2024, 1, 15), Decimal('105000')),
            (datetime(2024, 1, 31), Decimal('110000')),
            (datetime(2024, 2, 15), Decimal('115000')),
            (datetime(2024, 2, 29), Decimal('120000')),
        ]

        monthly_returns = self.analytics.calculate_monthly_returns(equity_curve)

        self.assertIn('2024-01', monthly_returns)
        self.assertIn('2024-02', monthly_returns)

    def test_equity_curve_summary(self):
        """Test equity curve summary."""
        equity_curve = [
            (datetime(2024, 1, 1), Decimal('100000')),
            (datetime(2024, 1, 15), Decimal('105000')),
            (datetime(2024, 1, 31), Decimal('110000')),
        ]

        summary = self.analytics.generate_equity_curve_summary(equity_curve)

        self.assertEqual(summary['start_value'], '100000')
        self.assertEqual(summary['end_value'], '110000')
        self.assertEqual(summary['peak_value'], '110000')
        self.assertEqual(summary['data_points'], 3)


if __name__ == '__main__':
    unittest.main()
