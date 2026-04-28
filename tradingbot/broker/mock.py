"""
In-memory mock broker for unit testing and local development.

Simulates order fills instantly at the price returned by get_latest_price,
which itself uses yfinance so no Alpaca credentials are required.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Dict, List, Optional

from .base import (
    AccountInfo,
    BrokerAdapter,
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
)

logger = logging.getLogger(__name__)


class MockBroker(BrokerAdapter):
    """
    Stateful in-memory broker for testing without real credentials.

    Fills every order instantly at the current yfinance price.
    Tracks positions and a simulated cash balance.
    """

    def __init__(self, starting_cash: float = 100_000.0):
        self._cash = starting_cash
        self._starting_cash = starting_cash
        self._positions: Dict[str, Position] = {}
        self._orders: List[Order] = []
        logger.info("MockBroker initialised with $%.2f starting cash", starting_cash)

    # ------------------------------------------------------------------ #
    # Account                                                              #
    # ------------------------------------------------------------------ #

    def get_account(self) -> AccountInfo:
        portfolio_value = self._cash + sum(
            p.market_value for p in self._positions.values()
        )
        return AccountInfo(
            cash=self._cash,
            portfolio_value=portfolio_value,
            buying_power=self._cash,
            equity=portfolio_value,
        )

    # ------------------------------------------------------------------ #
    # Positions                                                            #
    # ------------------------------------------------------------------ #

    def get_positions(self) -> List[Position]:
        self._refresh_prices()
        return list(self._positions.values())

    def get_position(self, ticker: str) -> Optional[Position]:
        self._refresh_prices()
        return self._positions.get(ticker.upper())

    def _refresh_prices(self) -> None:
        for ticker, pos in list(self._positions.items()):
            try:
                price = self.get_latest_price(ticker)
                pnl = (price - pos.avg_entry_price) * pos.qty
                pnl_pct = pnl / (pos.avg_entry_price * pos.qty) if pos.avg_entry_price > 0 else 0.0
                self._positions[ticker] = Position(
                    ticker=pos.ticker,
                    qty=pos.qty,
                    avg_entry_price=pos.avg_entry_price,
                    current_price=price,
                    market_value=price * pos.qty,
                    unrealized_pnl=pnl,
                    unrealized_pnl_pct=pnl_pct,
                )
            except Exception:
                pass

    # ------------------------------------------------------------------ #
    # Orders                                                               #
    # ------------------------------------------------------------------ #

    def submit_order(
        self,
        ticker: str,
        qty: float,
        side: OrderSide,
        order_type: OrderType = OrderType.MARKET,
        limit_price: Optional[float] = None,
        time_in_force: str = "day",
    ) -> Order:
        ticker = ticker.upper()
        price = self.get_latest_price(ticker)
        fill_price = limit_price if (order_type == OrderType.LIMIT and limit_price) else price

        order = Order(
            order_id=str(uuid.uuid4()),
            ticker=ticker,
            side=side,
            qty=qty,
            order_type=order_type,
            status=OrderStatus.FILLED,
            submitted_at=datetime.utcnow(),
            filled_qty=qty,
            filled_avg_price=fill_price,
            filled_at=datetime.utcnow(),
            limit_price=limit_price,
        )

        self._apply_fill(ticker, side, qty, fill_price)
        self._orders.insert(0, order)

        logger.info(
            "MockBroker FILLED: %s %s %.4f @ $%.2f",
            side.value.upper(), ticker, qty, fill_price,
        )
        return order

    def _apply_fill(self, ticker: str, side: OrderSide, qty: float, price: float) -> None:
        if side == OrderSide.BUY:
            cost = qty * price
            if cost > self._cash:
                raise ValueError(
                    f"Insufficient cash: need ${cost:.2f}, have ${self._cash:.2f}"
                )
            self._cash -= cost
            existing = self._positions.get(ticker)
            if existing:
                total_qty = existing.qty + qty
                avg_price = (existing.avg_entry_price * existing.qty + price * qty) / total_qty
                self._positions[ticker] = Position(
                    ticker=ticker,
                    qty=total_qty,
                    avg_entry_price=avg_price,
                    current_price=price,
                    market_value=total_qty * price,
                    unrealized_pnl=(price - avg_price) * total_qty,
                    unrealized_pnl_pct=(price - avg_price) / avg_price if avg_price > 0 else 0.0,
                )
            else:
                self._positions[ticker] = Position(
                    ticker=ticker,
                    qty=qty,
                    avg_entry_price=price,
                    current_price=price,
                    market_value=qty * price,
                    unrealized_pnl=0.0,
                    unrealized_pnl_pct=0.0,
                )
        else:  # SELL
            existing = self._positions.get(ticker)
            if not existing or existing.qty < qty:
                raise ValueError(
                    f"Cannot sell {qty} shares of {ticker}: "
                    f"only {existing.qty if existing else 0} held"
                )
            proceeds = qty * price
            self._cash += proceeds
            remaining_qty = existing.qty - qty
            if remaining_qty < 1e-6:
                del self._positions[ticker]
            else:
                self._positions[ticker] = Position(
                    ticker=ticker,
                    qty=remaining_qty,
                    avg_entry_price=existing.avg_entry_price,
                    current_price=price,
                    market_value=remaining_qty * price,
                    unrealized_pnl=(price - existing.avg_entry_price) * remaining_qty,
                    unrealized_pnl_pct=(price - existing.avg_entry_price) / existing.avg_entry_price
                    if existing.avg_entry_price > 0 else 0.0,
                )

    def get_order(self, order_id: str) -> Order:
        for o in self._orders:
            if o.order_id == order_id:
                return o
        raise ValueError(f"Order {order_id} not found")

    def cancel_order(self, order_id: str) -> bool:
        for o in self._orders:
            if o.order_id == order_id and o.status == OrderStatus.PENDING:
                o.status = OrderStatus.CANCELLED
                return True
        return False

    def get_order_history(self, limit: int = 100) -> List[Order]:
        return self._orders[:limit]

    # ------------------------------------------------------------------ #
    # Market data                                                          #
    # ------------------------------------------------------------------ #

    def get_latest_price(self, ticker: str) -> float:
        import yfinance as yf
        data = yf.Ticker(ticker).fast_info
        price = getattr(data, "last_price", None) or getattr(data, "previous_close", None)
        if price is None:
            raise ValueError(f"Could not fetch price for {ticker}")
        return float(price)
