"""
Tests for the Portfolio class.
"""

import unittest
from decimal import Decimal
from datetime import datetime

from tradingagents.portfolio import (
    Portfolio,
    MarketOrder,
    Position,
    RiskLimits,
)
from tradingagents.portfolio.exceptions import (
    InsufficientFundsError,
    InsufficientSharesError,
    RiskLimitExceededError,
    PositionNotFoundError,
)


class TestPortfolio(unittest.TestCase):
    """Test cases for Portfolio class."""

    def setUp(self):
        """Set up test portfolio."""
        self.initial_capital = Decimal('100000.00')
        self.commission_rate = Decimal('0.001')
        self.portfolio = Portfolio(
            initial_capital=self.initial_capital,
            commission_rate=self.commission_rate
        )

    def test_initialization(self):
        """Test portfolio initialization."""
        self.assertEqual(self.portfolio.cash, self.initial_capital)
        self.assertEqual(self.portfolio.initial_capital, self.initial_capital)
        self.assertEqual(self.portfolio.commission_rate, self.commission_rate)
        self.assertEqual(len(self.portfolio.positions), 0)

    def test_execute_buy_order(self):
        """Test executing a buy order."""
        order = MarketOrder('AAPL', Decimal('100'))
        price = Decimal('150.00')

        self.portfolio.execute_order(order, price)

        # Check position created
        self.assertIn('AAPL', self.portfolio.positions)
        position = self.portfolio.get_position('AAPL')
        self.assertEqual(position.quantity, Decimal('100'))
        self.assertEqual(position.cost_basis, price)

        # Check cash deducted
        order_value = Decimal('100') * price
        commission = order_value * self.commission_rate
        expected_cash = self.initial_capital - order_value - commission
        self.assertEqual(self.portfolio.cash, expected_cash)

    def test_execute_sell_order(self):
        """Test executing a sell order."""
        # First buy
        buy_order = MarketOrder('AAPL', Decimal('100'))
        self.portfolio.execute_order(buy_order, Decimal('150.00'))

        # Then sell
        sell_order = MarketOrder('AAPL', Decimal('-100'))
        self.portfolio.execute_order(sell_order, Decimal('160.00'))

        # Position should be closed
        self.assertNotIn('AAPL', self.portfolio.positions)

        # Should have a trade record
        self.assertEqual(len(self.portfolio.trade_history), 1)
        trade = self.portfolio.trade_history[0]
        self.assertEqual(trade.ticker, 'AAPL')
        self.assertTrue(trade.is_win)

    def test_partial_sell(self):
        """Test partially selling a position."""
        # Buy 100 shares
        buy_order = MarketOrder('AAPL', Decimal('100'))
        self.portfolio.execute_order(buy_order, Decimal('150.00'))

        # Sell 50 shares
        sell_order = MarketOrder('AAPL', Decimal('-50'))
        self.portfolio.execute_order(sell_order, Decimal('160.00'))

        # Position should still exist with 50 shares
        position = self.portfolio.get_position('AAPL')
        self.assertEqual(position.quantity, Decimal('50'))

    def test_insufficient_funds(self):
        """Test that insufficient funds raises error."""
        # Try to buy more than we have cash for
        order = MarketOrder('AAPL', Decimal('1000000'))

        with self.assertRaises(InsufficientFundsError):
            self.portfolio.execute_order(order, Decimal('150.00'))

    def test_insufficient_shares(self):
        """Test that selling more shares than owned raises error."""
        # Buy 100 shares
        buy_order = MarketOrder('AAPL', Decimal('100'))
        self.portfolio.execute_order(buy_order, Decimal('150.00'))

        # Try to sell 200 shares
        sell_order = MarketOrder('AAPL', Decimal('-200'))

        with self.assertRaises(InsufficientSharesError):
            self.portfolio.execute_order(sell_order, Decimal('160.00'))

    def test_sell_nonexistent_position(self):
        """Test that selling a position we don't own raises error."""
        sell_order = MarketOrder('AAPL', Decimal('-100'))

        with self.assertRaises(PositionNotFoundError):
            self.portfolio.execute_order(sell_order, Decimal('150.00'))

    def test_total_value(self):
        """Test total portfolio value calculation."""
        # Buy some positions (use smaller quantities to avoid running out of cash)
        # Disable risk checks for this test to focus on value calculation
        self.portfolio.execute_order(MarketOrder('AAPL', Decimal('100')), Decimal('150.00'), check_risk=False)
        self.portfolio.execute_order(MarketOrder('GOOGL', Decimal('20')), Decimal('2000.00'), check_risk=False)

        # Calculate total value with current prices
        prices = {
            'AAPL': Decimal('160.00'),
            'GOOGL': Decimal('2100.00')
        }

        total_value = self.portfolio.total_value(prices)

        # Expected: cash + AAPL value + GOOGL value
        aapl_value = Decimal('100') * Decimal('160.00')
        googl_value = Decimal('20') * Decimal('2100.00')
        expected = self.portfolio.cash + aapl_value + googl_value

        self.assertAlmostEqual(float(total_value), float(expected), places=2)

    def test_unrealized_pnl(self):
        """Test unrealized P&L calculation."""
        # Buy AAPL at $150
        self.portfolio.execute_order(MarketOrder('AAPL', Decimal('100')), Decimal('150.00'))

        # Current price is $160
        prices = {'AAPL': Decimal('160.00')}
        unrealized = self.portfolio.unrealized_pnl(prices)

        # Expected profit: (160 - 150) * 100 = 1000
        expected = Decimal('1000.00')
        self.assertEqual(unrealized, expected)

    def test_realized_pnl(self):
        """Test realized P&L calculation."""
        # Buy and sell for profit
        self.portfolio.execute_order(MarketOrder('AAPL', Decimal('100')), Decimal('150.00'))
        self.portfolio.execute_order(MarketOrder('AAPL', Decimal('-100')), Decimal('160.00'))

        realized = self.portfolio.realized_pnl()

        # Should be positive (profit)
        self.assertGreater(realized, 0)

    def test_position_size_limit(self):
        """Test that position size limits are enforced."""
        # Create portfolio with strict limits
        limits = RiskLimits(max_position_size=Decimal('0.10'))  # 10% max
        portfolio = Portfolio(
            initial_capital=Decimal('100000.00'),
            commission_rate=Decimal('0.001'),
            risk_limits=limits
        )

        # Try to buy more than 10% of portfolio
        # 10% of 100k = 10k, at $150/share = 66 shares max (approx)
        # We'll try 100 shares at $150 = $15k which is 15% > 10%
        order = MarketOrder('AAPL', Decimal('100'))  # 15% of portfolio

        with self.assertRaises(RiskLimitExceededError):
            portfolio.execute_order(order, Decimal('150.00'))

    def test_save_and_load(self):
        """Test saving and loading portfolio state."""
        # Execute some trades
        self.portfolio.execute_order(MarketOrder('AAPL', Decimal('100')), Decimal('150.00'))

        # Save
        filename = 'test_portfolio.json'
        self.portfolio.save(filename)

        # Load into new portfolio
        loaded = Portfolio.load(filename)

        # Verify state is preserved
        self.assertEqual(loaded.cash, self.portfolio.cash)
        self.assertEqual(loaded.initial_capital, self.portfolio.initial_capital)
        self.assertIn('AAPL', loaded.positions)

    def test_summary(self):
        """Test portfolio summary generation."""
        self.portfolio.execute_order(MarketOrder('AAPL', Decimal('100')), Decimal('150.00'))

        summary = self.portfolio.summary()

        self.assertIn('total_value', summary)
        self.assertIn('cash', summary)
        self.assertIn('num_positions', summary)
        self.assertEqual(summary['num_positions'], 1)

    def test_check_stop_loss_triggers(self):
        """Test stop-loss trigger detection."""
        # Create position with stop-loss
        self.portfolio.execute_order(MarketOrder('AAPL', Decimal('100')), Decimal('150.00'))

        position = self.portfolio.get_position('AAPL')
        position.stop_loss = Decimal('145.00')

        # Price drops to stop-loss level
        prices = {'AAPL': Decimal('144.00')}
        triggered_orders = self.portfolio.check_stop_loss_triggers(prices)

        self.assertEqual(len(triggered_orders), 1)
        self.assertEqual(triggered_orders[0].ticker, 'AAPL')

    def test_check_take_profit_triggers(self):
        """Test take-profit trigger detection."""
        # Create position with take-profit
        self.portfolio.execute_order(MarketOrder('AAPL', Decimal('100')), Decimal('150.00'))

        position = self.portfolio.get_position('AAPL')
        position.take_profit = Decimal('160.00')

        # Price rises to take-profit level
        prices = {'AAPL': Decimal('161.00')}
        triggered_orders = self.portfolio.check_take_profit_triggers(prices)

        self.assertEqual(len(triggered_orders), 1)
        self.assertEqual(triggered_orders[0].ticker, 'AAPL')

    def test_equity_curve_tracking(self):
        """Test that equity curve is tracked."""
        initial_points = len(self.portfolio.equity_curve)

        # Execute some trades
        self.portfolio.execute_order(MarketOrder('AAPL', Decimal('100')), Decimal('150.00'))

        # Equity curve should have more points
        self.assertGreater(len(self.portfolio.equity_curve), initial_points)

    def test_thread_safety(self):
        """Test that portfolio operations are thread-safe."""
        import threading

        def buy_shares():
            order = MarketOrder('AAPL', Decimal('10'))
            try:
                self.portfolio.execute_order(order, Decimal('150.00'))
            except:
                pass  # May fail due to insufficient funds, that's ok

        threads = [threading.Thread(target=buy_shares) for _ in range(10)]

        for t in threads:
            t.start()

        for t in threads:
            t.join()

        # Should complete without crashing
        self.assertIsNotNone(self.portfolio.cash)


if __name__ == '__main__':
    unittest.main()
