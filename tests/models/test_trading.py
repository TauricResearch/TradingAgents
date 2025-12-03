from datetime import datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from tradingagents.models.trading import (
    Fill,
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
    PositionSide,
    Trade,
)


class TestOrder:
    def test_market_order_creation(self):
        order = Order(
            ticker="AAPL",
            side=OrderSide.BUY,
            quantity=100,
        )
        assert order.ticker == "AAPL"
        assert order.side == OrderSide.BUY
        assert order.order_type == OrderType.MARKET
        assert order.quantity == 100
        assert order.status == OrderStatus.PENDING
        assert order.remaining_quantity == 100
        assert not order.is_complete

    def test_limit_order_creation(self):
        order = Order(
            ticker="AAPL",
            side=OrderSide.SELL,
            order_type=OrderType.LIMIT,
            quantity=50,
            limit_price=Decimal("150.00"),
        )
        assert order.order_type == OrderType.LIMIT
        assert order.limit_price == Decimal("150.00")

    def test_order_partial_fill(self):
        order = Order(
            ticker="AAPL",
            side=OrderSide.BUY,
            quantity=100,
            status=OrderStatus.PARTIAL,
            filled_quantity=30,
        )
        assert order.remaining_quantity == 70
        assert not order.is_complete

    def test_order_complete_states(self):
        for status in [OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.REJECTED]:
            order = Order(
                ticker="AAPL",
                side=OrderSide.BUY,
                quantity=100,
                status=status,
            )
            assert order.is_complete

    def test_invalid_quantity(self):
        with pytest.raises(ValueError):
            Order(ticker="AAPL", side=OrderSide.BUY, quantity=0)

    def test_invalid_limit_price(self):
        with pytest.raises(ValueError):
            Order(
                ticker="AAPL",
                side=OrderSide.BUY,
                order_type=OrderType.LIMIT,
                quantity=100,
                limit_price=Decimal("-10"),
            )


class TestFill:
    def test_buy_fill(self):
        order_id = uuid4()
        fill = Fill(
            order_id=order_id,
            ticker="AAPL",
            side=OrderSide.BUY,
            quantity=100,
            price=Decimal("150.00"),
            commission=Decimal("1.00"),
        )
        assert fill.total_value == Decimal("15000.00")
        assert fill.total_cost == Decimal("15001.00")

    def test_sell_fill(self):
        order_id = uuid4()
        fill = Fill(
            order_id=order_id,
            ticker="AAPL",
            side=OrderSide.SELL,
            quantity=100,
            price=Decimal("150.00"),
            commission=Decimal("1.00"),
        )
        assert fill.total_value == Decimal("15000.00")
        assert fill.total_cost == Decimal("14999.00")


class TestPosition:
    def test_new_position(self):
        position = Position(ticker="AAPL")
        assert position.quantity == 0
        assert position.side == PositionSide.FLAT
        assert position.cost_basis == Decimal("0")

    def test_long_position(self):
        position = Position(
            ticker="AAPL",
            quantity=100,
            avg_cost=Decimal("150.00"),
        )
        assert position.side == PositionSide.LONG
        assert position.cost_basis == Decimal("15000.00")

    def test_short_position(self):
        position = Position(
            ticker="AAPL",
            quantity=-100,
            avg_cost=Decimal("150.00"),
        )
        assert position.side == PositionSide.SHORT
        assert position.cost_basis == Decimal("15000.00")

    def test_unrealized_pnl_long(self):
        position = Position(
            ticker="AAPL",
            quantity=100,
            avg_cost=Decimal("150.00"),
        )
        pnl = position.unrealized_pnl(Decimal("160.00"))
        assert pnl == Decimal("1000.00")

    def test_unrealized_pnl_short(self):
        position = Position(
            ticker="AAPL",
            quantity=-100,
            avg_cost=Decimal("150.00"),
        )
        pnl = position.unrealized_pnl(Decimal("140.00"))
        assert pnl == Decimal("1000.00")

    def test_update_from_buy_fill_new_position(self):
        position = Position(ticker="AAPL")
        fill = Fill(
            order_id=uuid4(),
            ticker="AAPL",
            side=OrderSide.BUY,
            quantity=100,
            price=Decimal("150.00"),
        )
        position.update_from_fill(fill)
        assert position.quantity == 100
        assert position.avg_cost == Decimal("150.00")

    def test_update_from_buy_fill_add_to_position(self):
        position = Position(
            ticker="AAPL",
            quantity=100,
            avg_cost=Decimal("150.00"),
        )
        fill = Fill(
            order_id=uuid4(),
            ticker="AAPL",
            side=OrderSide.BUY,
            quantity=100,
            price=Decimal("160.00"),
        )
        position.update_from_fill(fill)
        assert position.quantity == 200
        assert position.avg_cost == Decimal("155.00")

    def test_update_from_sell_fill_close_position(self):
        position = Position(
            ticker="AAPL",
            quantity=100,
            avg_cost=Decimal("150.00"),
        )
        fill = Fill(
            order_id=uuid4(),
            ticker="AAPL",
            side=OrderSide.SELL,
            quantity=100,
            price=Decimal("160.00"),
        )
        position.update_from_fill(fill)
        assert position.quantity == 0
        assert position.realized_pnl == Decimal("1000.00")

    def test_update_from_sell_fill_partial_close(self):
        position = Position(
            ticker="AAPL",
            quantity=100,
            avg_cost=Decimal("150.00"),
        )
        fill = Fill(
            order_id=uuid4(),
            ticker="AAPL",
            side=OrderSide.SELL,
            quantity=50,
            price=Decimal("160.00"),
        )
        position.update_from_fill(fill)
        assert position.quantity == 50
        assert position.realized_pnl == Decimal("500.00")
        assert position.avg_cost == Decimal("150.00")


class TestTrade:
    def test_open_trade(self):
        trade = Trade(
            ticker="AAPL",
            side=OrderSide.BUY,
            entry_price=Decimal("150.00"),
            entry_quantity=100,
            entry_time=datetime(2024, 1, 15, 9, 30),
        )
        assert not trade.is_closed
        assert trade.pnl is None
        assert trade.holding_period is None

    def test_closed_trade_profit(self):
        trade = Trade(
            ticker="AAPL",
            side=OrderSide.BUY,
            entry_price=Decimal("150.00"),
            entry_quantity=100,
            entry_time=datetime(2024, 1, 15),
            exit_price=Decimal("160.00"),
            exit_quantity=100,
            exit_time=datetime(2024, 1, 25),
        )
        assert trade.is_closed
        assert trade.pnl == Decimal("1000.00")
        assert trade.holding_period == 10

    def test_closed_trade_loss(self):
        trade = Trade(
            ticker="AAPL",
            side=OrderSide.BUY,
            entry_price=Decimal("150.00"),
            entry_quantity=100,
            entry_time=datetime(2024, 1, 15),
            exit_price=Decimal("140.00"),
            exit_quantity=100,
            exit_time=datetime(2024, 1, 20),
        )
        assert trade.pnl == Decimal("-1000.00")

    def test_trade_with_commission(self):
        trade = Trade(
            ticker="AAPL",
            side=OrderSide.BUY,
            entry_price=Decimal("150.00"),
            entry_quantity=100,
            entry_time=datetime(2024, 1, 15),
            exit_price=Decimal("160.00"),
            exit_quantity=100,
            exit_time=datetime(2024, 1, 20),
            commission=Decimal("10.00"),
        )
        assert trade.pnl == Decimal("990.00")

    def test_short_trade_profit(self):
        trade = Trade(
            ticker="AAPL",
            side=OrderSide.SELL,
            entry_price=Decimal("150.00"),
            entry_quantity=100,
            entry_time=datetime(2024, 1, 15),
            exit_price=Decimal("140.00"),
            exit_quantity=100,
            exit_time=datetime(2024, 1, 20),
        )
        assert trade.pnl == Decimal("1000.00")

    def test_pnl_percent(self):
        trade = Trade(
            ticker="AAPL",
            side=OrderSide.BUY,
            entry_price=Decimal("100.00"),
            entry_quantity=100,
            entry_time=datetime(2024, 1, 15),
            exit_price=Decimal("110.00"),
            exit_quantity=100,
            exit_time=datetime(2024, 1, 20),
        )
        assert trade.pnl_percent == Decimal("10")
