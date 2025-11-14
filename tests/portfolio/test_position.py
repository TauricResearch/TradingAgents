"""
Tests for the Position class.
"""

import unittest
from decimal import Decimal
from datetime import datetime, timedelta

from tradingagents.portfolio import Position
from tradingagents.portfolio.exceptions import (
    InvalidPositionError,
    InvalidPriceError,
    InvalidQuantityError,
)


class TestPosition(unittest.TestCase):
    """Test cases for Position class."""

    def test_create_long_position(self):
        """Test creating a long position."""
        position = Position(
            ticker='AAPL',
            quantity=Decimal('100'),
            cost_basis=Decimal('150.00')
        )

        self.assertEqual(position.ticker, 'AAPL')
        self.assertEqual(position.quantity, Decimal('100'))
        self.assertEqual(position.cost_basis, Decimal('150.00'))
        self.assertTrue(position.is_long)
        self.assertFalse(position.is_short)

    def test_create_short_position(self):
        """Test creating a short position."""
        position = Position(
            ticker='TSLA',
            quantity=Decimal('-50'),
            cost_basis=Decimal('200.00')
        )

        self.assertEqual(position.quantity, Decimal('-50'))
        self.assertFalse(position.is_long)
        self.assertTrue(position.is_short)

    def test_invalid_ticker(self):
        """Test that invalid tickers are rejected."""
        with self.assertRaises(InvalidPositionError):
            Position(
                ticker='../etc/passwd',
                quantity=Decimal('100'),
                cost_basis=Decimal('150.00')
            )

    def test_zero_quantity_rejected(self):
        """Test that zero quantity is rejected."""
        with self.assertRaises(InvalidQuantityError):
            Position(
                ticker='AAPL',
                quantity=Decimal('0'),
                cost_basis=Decimal('150.00')
            )

    def test_negative_cost_basis_rejected(self):
        """Test that negative cost basis is rejected."""
        with self.assertRaises(InvalidPriceError):
            Position(
                ticker='AAPL',
                quantity=Decimal('100'),
                cost_basis=Decimal('-150.00')
            )

    def test_market_value(self):
        """Test market value calculation."""
        position = Position(
            ticker='AAPL',
            quantity=Decimal('100'),
            cost_basis=Decimal('150.00')
        )

        market_value = position.market_value(Decimal('160.00'))
        self.assertEqual(market_value, Decimal('16000.00'))

    def test_total_cost(self):
        """Test total cost calculation."""
        position = Position(
            ticker='AAPL',
            quantity=Decimal('100'),
            cost_basis=Decimal('150.00')
        )

        self.assertEqual(position.total_cost(), Decimal('15000.00'))

    def test_unrealized_pnl_long_profit(self):
        """Test unrealized P&L for profitable long position."""
        position = Position(
            ticker='AAPL',
            quantity=Decimal('100'),
            cost_basis=Decimal('150.00')
        )

        pnl = position.unrealized_pnl(Decimal('160.00'))
        self.assertEqual(pnl, Decimal('1000.00'))  # (160 - 150) * 100

    def test_unrealized_pnl_long_loss(self):
        """Test unrealized P&L for losing long position."""
        position = Position(
            ticker='AAPL',
            quantity=Decimal('100'),
            cost_basis=Decimal('150.00')
        )

        pnl = position.unrealized_pnl(Decimal('140.00'))
        self.assertEqual(pnl, Decimal('-1000.00'))  # (140 - 150) * 100

    def test_unrealized_pnl_short_profit(self):
        """Test unrealized P&L for profitable short position."""
        position = Position(
            ticker='TSLA',
            quantity=Decimal('-50'),
            cost_basis=Decimal('200.00')
        )

        pnl = position.unrealized_pnl(Decimal('180.00'))
        self.assertEqual(pnl, Decimal('1000.00'))  # (200 - 180) * 50

    def test_unrealized_pnl_percent(self):
        """Test unrealized P&L percentage calculation."""
        position = Position(
            ticker='AAPL',
            quantity=Decimal('100'),
            cost_basis=Decimal('150.00')
        )

        pnl_pct = position.unrealized_pnl_percent(Decimal('165.00'))
        self.assertEqual(pnl_pct, Decimal('0.1'))  # 10% gain

    def test_update_quantity(self):
        """Test updating position quantity."""
        position = Position(
            ticker='AAPL',
            quantity=Decimal('100'),
            cost_basis=Decimal('150.00')
        )

        position.update_quantity(Decimal('50'))
        self.assertEqual(position.quantity, Decimal('150'))

    def test_update_quantity_cannot_reach_zero(self):
        """Test that update_quantity cannot result in zero."""
        position = Position(
            ticker='AAPL',
            quantity=Decimal('100'),
            cost_basis=Decimal('150.00')
        )

        with self.assertRaises(InvalidQuantityError):
            position.update_quantity(Decimal('-100'))

    def test_update_cost_basis(self):
        """Test weighted average cost basis calculation."""
        position = Position(
            ticker='AAPL',
            quantity=Decimal('100'),
            cost_basis=Decimal('150.00')
        )

        # Add 50 shares at $160
        position.update_cost_basis(Decimal('50'), Decimal('160.00'))

        # New cost basis should be (100*150 + 50*160) / 150 = 153.33...
        expected = (Decimal('100') * Decimal('150.00') + Decimal('50') * Decimal('160.00')) / Decimal('150')
        self.assertAlmostEqual(float(position.cost_basis), float(expected), places=2)

    def test_stop_loss_trigger_long(self):
        """Test stop-loss trigger for long position."""
        position = Position(
            ticker='AAPL',
            quantity=Decimal('100'),
            cost_basis=Decimal('150.00'),
            stop_loss=Decimal('145.00')
        )

        self.assertFalse(position.should_trigger_stop_loss(Decimal('150.00')))
        self.assertFalse(position.should_trigger_stop_loss(Decimal('146.00')))
        self.assertTrue(position.should_trigger_stop_loss(Decimal('145.00')))
        self.assertTrue(position.should_trigger_stop_loss(Decimal('140.00')))

    def test_take_profit_trigger_long(self):
        """Test take-profit trigger for long position."""
        position = Position(
            ticker='AAPL',
            quantity=Decimal('100'),
            cost_basis=Decimal('150.00'),
            take_profit=Decimal('160.00')
        )

        self.assertFalse(position.should_trigger_take_profit(Decimal('150.00')))
        self.assertFalse(position.should_trigger_take_profit(Decimal('159.00')))
        self.assertTrue(position.should_trigger_take_profit(Decimal('160.00')))
        self.assertTrue(position.should_trigger_take_profit(Decimal('165.00')))

    def test_to_dict_and_from_dict(self):
        """Test serialization and deserialization."""
        position = Position(
            ticker='AAPL',
            quantity=Decimal('100'),
            cost_basis=Decimal('150.00'),
            sector='Technology',
            stop_loss=Decimal('145.00'),
            take_profit=Decimal('160.00')
        )

        # Convert to dict
        data = position.to_dict()

        # Create from dict
        restored = Position.from_dict(data)

        self.assertEqual(restored.ticker, position.ticker)
        self.assertEqual(restored.quantity, position.quantity)
        self.assertEqual(restored.cost_basis, position.cost_basis)
        self.assertEqual(restored.sector, position.sector)
        self.assertEqual(restored.stop_loss, position.stop_loss)
        self.assertEqual(restored.take_profit, position.take_profit)


if __name__ == '__main__':
    unittest.main()
