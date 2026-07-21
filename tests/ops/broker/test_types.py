from decimal import Decimal
import pytest
from ops.broker.types import Order, Side, OrderType, Position

def test_order_is_frozen():
    o = Order(
        client_order_id="cid-1", symbol="AAPL", side=Side.BUY,
        notional_dollars=Decimal("25"), order_type=OrderType.MARKET,
        stop_loss_price=Decimal("180"),
    )
    with pytest.raises(Exception):
        o.symbol = "MSFT"

def test_order_buy_requires_positive_notional():
    with pytest.raises(ValueError):
        Order(
            client_order_id="x", symbol="AAPL", side=Side.BUY,
            notional_dollars=Decimal("0"), order_type=OrderType.MARKET,
        )

def test_order_sell_allows_zero_notional_meaning_sell_all():
    o = Order(
        client_order_id="x", symbol="AAPL", side=Side.SELL,
        notional_dollars=Decimal("0"), order_type=OrderType.MARKET,
    )
    assert o.notional_dollars == Decimal("0")

def test_position_value():
    p = Position(
        symbol="AAPL", quantity=Decimal("0.5"),
        avg_entry_price=Decimal("200"), stop_loss_price=Decimal("184"),
    )
    assert p.market_value(Decimal("210")) == Decimal("105.0")
    assert p.unrealized_pct(Decimal("210")) == Decimal("0.05")
