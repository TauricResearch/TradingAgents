"""In-memory paper broker. Records every order and fill to the journal."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Callable
from uuid import uuid4

from ops.broker.base import Broker, InsufficientFunds, NoSuchPosition
from ops.broker.types import Fill, Order, Position, Side
from ops.journal import Journal

QuoteSource = Callable[[str], Decimal]

_EPSILON = Decimal("0.0000001")


class PaperBroker(Broker):
    def __init__(self, *, journal: Journal, quote_source: QuoteSource, starting_cash: Decimal):
        self._journal = journal
        self._quote = quote_source
        self._cash = Decimal(starting_cash)
        self._positions: dict[str, Position] = {}

    def get_cash(self) -> Decimal:
        return self._cash

    def get_quote(self, symbol: str) -> Decimal:
        return self._quote(symbol)

    def get_positions(self) -> list[Position]:
        return list(self._positions.values())

    def get_equity(self) -> Decimal:
        total = self._cash
        for pos in self._positions.values():
            total += pos.market_value(self._quote(pos.symbol))
        return total

    def place_order(self, order: Order) -> Fill:
        self._journal.record_order(
            client_order_id=order.client_order_id,
            symbol=order.symbol,
            side=order.side.value,
            notional_dollars=order.notional_dollars,
            stop_loss_price=order.stop_loss_price,
        )
        price = self._quote(order.symbol)
        if order.side == Side.BUY:
            return self._fill_buy(order, price)
        return self._fill_sell(order, price)

    def _fill_buy(self, order: Order, price: Decimal) -> Fill:
        cost = order.notional_dollars
        if cost > self._cash:
            raise InsufficientFunds(f"need ${cost}, have ${self._cash}")
        qty = cost / price
        self._cash -= cost
        existing = self._positions.get(order.symbol)
        if existing is None:
            new_pos = Position(
                symbol=order.symbol,
                quantity=qty,
                avg_entry_price=price,
                stop_loss_price=order.stop_loss_price,
            )
        else:
            total_qty = existing.quantity + qty
            avg = (
                (existing.avg_entry_price * existing.quantity) + (price * qty)
            ) / total_qty
            new_pos = Position(
                symbol=order.symbol,
                quantity=total_qty,
                avg_entry_price=avg,
                stop_loss_price=order.stop_loss_price or existing.stop_loss_price,
            )
        self._positions[order.symbol] = new_pos
        return self._make_fill(order, qty, price)

    def _fill_sell(self, order: Order, price: Decimal) -> Fill:
        existing = self._positions.get(order.symbol)
        if existing is None:
            raise NoSuchPosition(f"no position in {order.symbol}")
        if order.notional_dollars == 0:
            qty_to_sell = existing.quantity
        else:
            qty_to_sell = order.notional_dollars / price
        if qty_to_sell > existing.quantity + _EPSILON:
            raise NoSuchPosition(
                f"sell qty {qty_to_sell} exceeds position {existing.quantity}"
            )
        proceeds = qty_to_sell * price
        self._cash += proceeds
        remaining = existing.quantity - qty_to_sell
        if remaining > _EPSILON:
            self._positions[order.symbol] = Position(
                symbol=existing.symbol,
                quantity=remaining,
                avg_entry_price=existing.avg_entry_price,
                stop_loss_price=existing.stop_loss_price,
            )
        else:
            del self._positions[order.symbol]
        return self._make_fill(order, qty_to_sell, price)

    def _make_fill(self, order: Order, qty: Decimal, price: Decimal) -> Fill:
        fill = Fill(
            order_id=str(uuid4()),
            client_order_id=order.client_order_id,
            symbol=order.symbol,
            side=order.side,
            quantity=qty,
            price=price,
            filled_at=datetime.now(timezone.utc),
        )
        self._journal.record_fill(
            order_id=fill.order_id,
            client_order_id=fill.client_order_id,
            symbol=fill.symbol,
            side=fill.side.value,
            quantity=fill.quantity,
            price=fill.price,
            filled_at=fill.filled_at,
        )
        return fill
