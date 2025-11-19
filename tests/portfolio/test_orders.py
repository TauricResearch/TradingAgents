"""
Tests for order classes.
"""

import unittest
from decimal import Decimal
from datetime import datetime

from tradingagents.portfolio import (
    MarketOrder,
    LimitOrder,
    StopLossOrder,
    TakeProfitOrder,
    OrderStatus,
    OrderSide,
    create_order_from_dict,
)
from tradingagents.portfolio.exceptions import (
    InvalidOrderError,
    InvalidPriceError,
    InvalidQuantityError,
)


class TestMarketOrder(unittest.TestCase):
    """Test cases for MarketOrder."""

    def test_create_buy_order(self):
        """Test creating a buy market order."""
        order = MarketOrder('AAPL', Decimal('100'))

        self.assertEqual(order.ticker, 'AAPL')
        self.assertEqual(order.quantity, Decimal('100'))
        self.assertTrue(order.is_buy)
        self.assertFalse(order.is_sell)
        self.assertEqual(order.side, OrderSide.BUY)
        self.assertEqual(order.status, OrderStatus.PENDING)

    def test_create_sell_order(self):
        """Test creating a sell market order."""
        order = MarketOrder('AAPL', Decimal('-50'))

        self.assertEqual(order.quantity, Decimal('-50'))
        self.assertFalse(order.is_buy)
        self.assertTrue(order.is_sell)
        self.assertEqual(order.side, OrderSide.SELL)

    def test_zero_quantity_rejected(self):
        """Test that zero quantity is rejected."""
        with self.assertRaises(InvalidQuantityError):
            MarketOrder('AAPL', Decimal('0'))

    def test_can_execute(self):
        """Test that market orders can always execute."""
        order = MarketOrder('AAPL', Decimal('100'))

        self.assertTrue(order.can_execute(Decimal('150.00')))
        self.assertTrue(order.can_execute(Decimal('100.00')))
        self.assertTrue(order.can_execute(Decimal('200.00')))

    def test_mark_executed(self):
        """Test marking an order as executed."""
        order = MarketOrder('AAPL', Decimal('100'))

        order.mark_executed(Decimal('100'), Decimal('150.00'))

        self.assertEqual(order.status, OrderStatus.EXECUTED)
        self.assertEqual(order.filled_quantity, Decimal('100'))
        self.assertEqual(order.filled_price, Decimal('150.00'))
        self.assertIsNotNone(order.executed_at)
        self.assertTrue(order.is_filled)

    def test_partial_fill(self):
        """Test partial order fill."""
        order = MarketOrder('AAPL', Decimal('100'))

        order.mark_executed(Decimal('50'), Decimal('150.00'))

        self.assertEqual(order.status, OrderStatus.PARTIALLY_FILLED)
        self.assertTrue(order.is_partially_filled)
        self.assertFalse(order.is_filled)

    def test_cannot_execute_twice(self):
        """Test that executed order cannot be executed again."""
        order = MarketOrder('AAPL', Decimal('100'))
        order.mark_executed(Decimal('100'), Decimal('150.00'))

        with self.assertRaises(InvalidOrderError):
            order.mark_executed(Decimal('100'), Decimal('151.00'))

    def test_cancel_order(self):
        """Test cancelling an order."""
        order = MarketOrder('AAPL', Decimal('100'))
        order.cancel()

        self.assertEqual(order.status, OrderStatus.CANCELLED)

    def test_cannot_cancel_executed_order(self):
        """Test that executed orders cannot be cancelled."""
        order = MarketOrder('AAPL', Decimal('100'))
        order.mark_executed(Decimal('100'), Decimal('150.00'))

        with self.assertRaises(InvalidOrderError):
            order.cancel()


class TestLimitOrder(unittest.TestCase):
    """Test cases for LimitOrder."""

    def test_create_buy_limit_order(self):
        """Test creating a buy limit order."""
        order = LimitOrder('AAPL', Decimal('100'), limit_price=Decimal('150.00'))

        self.assertEqual(order.limit_price, Decimal('150.00'))
        self.assertTrue(order.is_buy)

    def test_missing_limit_price_rejected(self):
        """Test that limit orders require limit_price."""
        with self.assertRaises(InvalidOrderError):
            LimitOrder('AAPL', Decimal('100'))

    def test_buy_limit_can_execute(self):
        """Test buy limit order execution logic."""
        order = LimitOrder('AAPL', Decimal('100'), limit_price=Decimal('150.00'))

        # Can execute at or below limit
        self.assertTrue(order.can_execute(Decimal('150.00')))
        self.assertTrue(order.can_execute(Decimal('149.00')))

        # Cannot execute above limit
        self.assertFalse(order.can_execute(Decimal('151.00')))

    def test_sell_limit_can_execute(self):
        """Test sell limit order execution logic."""
        order = LimitOrder('AAPL', Decimal('-100'), limit_price=Decimal('150.00'))

        # Can execute at or above limit
        self.assertTrue(order.can_execute(Decimal('150.00')))
        self.assertTrue(order.can_execute(Decimal('151.00')))

        # Cannot execute below limit
        self.assertFalse(order.can_execute(Decimal('149.00')))


class TestStopLossOrder(unittest.TestCase):
    """Test cases for StopLossOrder."""

    def test_create_stop_loss_order(self):
        """Test creating a stop-loss order."""
        order = StopLossOrder('AAPL', Decimal('-100'), stop_price=Decimal('145.00'))

        self.assertEqual(order.stop_price, Decimal('145.00'))

    def test_stop_loss_trigger_for_long_position(self):
        """Test stop-loss trigger for closing long position."""
        order = StopLossOrder('AAPL', Decimal('-100'), stop_price=Decimal('145.00'))

        # Triggers at or below stop price
        self.assertTrue(order.can_execute(Decimal('145.00')))
        self.assertTrue(order.can_execute(Decimal('144.00')))

        # Does not trigger above stop price
        self.assertFalse(order.can_execute(Decimal('146.00')))


class TestTakeProfitOrder(unittest.TestCase):
    """Test cases for TakeProfitOrder."""

    def test_create_take_profit_order(self):
        """Test creating a take-profit order."""
        order = TakeProfitOrder('AAPL', Decimal('-100'), target_price=Decimal('160.00'))

        self.assertEqual(order.target_price, Decimal('160.00'))

    def test_take_profit_trigger_for_long_position(self):
        """Test take-profit trigger for closing long position."""
        order = TakeProfitOrder('AAPL', Decimal('-100'), target_price=Decimal('160.00'))

        # Triggers at or above target price
        self.assertTrue(order.can_execute(Decimal('160.00')))
        self.assertTrue(order.can_execute(Decimal('161.00')))

        # Does not trigger below target price
        self.assertFalse(order.can_execute(Decimal('159.00')))


class TestOrderSerialization(unittest.TestCase):
    """Test order serialization and deserialization."""

    def test_market_order_to_dict(self):
        """Test market order serialization."""
        order = MarketOrder('AAPL', Decimal('100'))
        data = order.to_dict()

        self.assertEqual(data['ticker'], 'AAPL')
        self.assertEqual(data['quantity'], '100')
        self.assertEqual(data['order_type'], 'market')

    def test_limit_order_to_dict(self):
        """Test limit order serialization."""
        order = LimitOrder('AAPL', Decimal('100'), limit_price=Decimal('150.00'))
        data = order.to_dict()

        self.assertEqual(data['limit_price'], '150.00')

    def test_create_order_from_dict(self):
        """Test creating order from dictionary."""
        order = MarketOrder('AAPL', Decimal('100'))
        data = order.to_dict()

        restored = create_order_from_dict(data)

        self.assertIsInstance(restored, MarketOrder)
        self.assertEqual(restored.ticker, order.ticker)
        self.assertEqual(restored.quantity, order.quantity)


if __name__ == '__main__':
    unittest.main()
