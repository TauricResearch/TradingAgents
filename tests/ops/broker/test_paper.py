from decimal import Decimal
import pytest
from ops.broker.types import Order, Side, OrderType
from ops.broker.base import InsufficientFunds, NoSuchPosition
from ops.broker.paper import PaperBroker
from ops.journal import Journal


def _broker(tmp_path, prices: dict[str, str], cash: str = "250"):
    j = Journal(str(tmp_path / "j.sqlite"))
    quotes = {k: Decimal(v) for k, v in prices.items()}
    return PaperBroker(journal=j, quote_source=lambda s: quotes[s], starting_cash=Decimal(cash))


def test_buy_creates_position_and_debits_cash(tmp_path):
    b = _broker(tmp_path, {"AAPL": "200"})
    o = Order(
        client_order_id="c1", symbol="AAPL", side=Side.BUY,
        notional_dollars=Decimal("25"), order_type=OrderType.MARKET,
        stop_loss_price=Decimal("184"),
    )
    fill = b.place_order(o)
    assert fill.quantity == Decimal("0.125")
    assert fill.price == Decimal("200")
    assert b.get_cash() == Decimal("225")
    positions = b.get_positions()
    assert len(positions) == 1
    assert positions[0].symbol == "AAPL"
    assert positions[0].quantity == Decimal("0.125")
    assert positions[0].stop_loss_price == Decimal("184")


def test_buy_with_insufficient_cash_raises(tmp_path):
    b = _broker(tmp_path, {"AAPL": "200"}, cash="10")
    o = Order(
        client_order_id="c1", symbol="AAPL", side=Side.BUY,
        notional_dollars=Decimal("25"), order_type=OrderType.MARKET,
        stop_loss_price=Decimal("184"),
    )
    with pytest.raises(InsufficientFunds):
        b.place_order(o)


def test_sell_reduces_position_and_credits_cash(tmp_path):
    b = _broker(tmp_path, {"AAPL": "200"})
    b.place_order(Order(
        client_order_id="c1", symbol="AAPL", side=Side.BUY,
        notional_dollars=Decimal("50"), order_type=OrderType.MARKET,
        stop_loss_price=Decimal("184"),
    ))
    # price moves up — replace the quote_source for the next call
    b._quote = lambda s: Decimal("220")  # type: ignore[attr-defined]
    b.place_order(Order(
        client_order_id="c2", symbol="AAPL", side=Side.SELL,
        notional_dollars=Decimal("22"), order_type=OrderType.MARKET,
    ))
    pos = b.get_positions()[0]
    assert pos.quantity == Decimal("0.15")  # 0.25 bought, 0.1 sold
    assert b.get_cash() == Decimal("222")  # 250 - 50 + 22


def test_sell_zero_notional_closes_position(tmp_path):
    b = _broker(tmp_path, {"AAPL": "200"})
    b.place_order(Order(
        client_order_id="c1", symbol="AAPL", side=Side.BUY,
        notional_dollars=Decimal("50"), order_type=OrderType.MARKET,
        stop_loss_price=Decimal("184"),
    ))
    b.place_order(Order(
        client_order_id="c2", symbol="AAPL", side=Side.SELL,
        notional_dollars=Decimal("0"), order_type=OrderType.MARKET,
    ))
    assert b.get_positions() == []
    assert b.get_cash() == Decimal("250")


def test_sell_without_position_raises(tmp_path):
    b = _broker(tmp_path, {"AAPL": "200"})
    with pytest.raises(NoSuchPosition):
        b.place_order(Order(
            client_order_id="c1", symbol="AAPL", side=Side.SELL,
            notional_dollars=Decimal("25"), order_type=OrderType.MARKET,
        ))


def test_equity_reflects_position_value_and_cash(tmp_path):
    b = _broker(tmp_path, {"AAPL": "200"})
    b.place_order(Order(
        client_order_id="c1", symbol="AAPL", side=Side.BUY,
        notional_dollars=Decimal("50"), order_type=OrderType.MARKET,
        stop_loss_price=Decimal("184"),
    ))
    b._quote = lambda s: Decimal("240")  # type: ignore[attr-defined]
    # cash: 200; position value: 0.25 * 240 = 60; total: 260
    assert b.get_equity() == Decimal("260.000")


def test_fills_are_journaled(tmp_path):
    j = Journal(str(tmp_path / "j.sqlite"))
    b = PaperBroker(journal=j, quote_source=lambda s: Decimal("200"), starting_cash=Decimal("250"))
    b.place_order(Order(
        client_order_id="c1", symbol="AAPL", side=Side.BUY,
        notional_dollars=Decimal("25"), order_type=OrderType.MARKET,
        stop_loss_price=Decimal("184"),
    ))
    orders = j.read_orders()
    fills = j.read_fills()
    assert len(orders) == 1 and len(fills) == 1
    assert orders[0]["client_order_id"] == "c1"
    assert fills[0]["quantity"] == Decimal("0.125")
