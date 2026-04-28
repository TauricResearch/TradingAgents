"""Alpaca Markets broker adapter (paper and live trading)."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Optional

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


def _to_order_status(alpaca_status: str) -> OrderStatus:
    mapping = {
        "new": OrderStatus.PENDING,
        "partially_filled": OrderStatus.PARTIALLY_FILLED,
        "filled": OrderStatus.FILLED,
        "done_for_day": OrderStatus.CANCELLED,
        "canceled": OrderStatus.CANCELLED,
        "expired": OrderStatus.EXPIRED,
        "replaced": OrderStatus.CANCELLED,
        "pending_cancel": OrderStatus.PENDING,
        "pending_replace": OrderStatus.PENDING,
        "accepted": OrderStatus.PENDING,
        "pending_new": OrderStatus.PENDING,
        "accepted_for_bidding": OrderStatus.PENDING,
        "stopped": OrderStatus.CANCELLED,
        "rejected": OrderStatus.REJECTED,
        "suspended": OrderStatus.REJECTED,
        "calculated": OrderStatus.PENDING,
    }
    return mapping.get(alpaca_status.lower(), OrderStatus.PENDING)


class AlpacaBroker(BrokerAdapter):
    """
    Alpaca Markets implementation of BrokerAdapter.

    Supports both paper trading (paper=True, the default) and live trading.
    Paper trading is strongly recommended during development and testing.

    Requires:
        pip install alpaca-py

    Environment variables (or pass directly):
        ALPACA_API_KEY
        ALPACA_API_SECRET
    """

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        paper: bool = True,
    ):
        """
        Args:
            api_key:    Alpaca API key ID.
            api_secret: Alpaca API secret key.
            paper:      True → paper trading endpoint (safe default).
                        False → live trading (real money — use with caution).
        """
        try:
            from alpaca.trading.client import TradingClient
            from alpaca.data.historical import StockHistoricalDataClient
        except ImportError as exc:
            raise ImportError(
                "alpaca-py is required for AlpacaBroker. "
                "Install it with: pip install alpaca-py"
            ) from exc

        self._trading = TradingClient(api_key, api_secret, paper=paper)
        self._data = StockHistoricalDataClient(api_key, api_secret)
        self._paper = paper
        logger.info("AlpacaBroker initialised (%s)", "PAPER" if paper else "LIVE")

    # ------------------------------------------------------------------ #
    # Account                                                              #
    # ------------------------------------------------------------------ #

    def get_account(self) -> AccountInfo:
        acct = self._trading.get_account()
        return AccountInfo(
            cash=float(acct.cash),
            portfolio_value=float(acct.portfolio_value),
            buying_power=float(acct.buying_power),
            equity=float(acct.equity),
            daytrade_count=int(acct.daytrade_count),
        )

    # ------------------------------------------------------------------ #
    # Positions                                                            #
    # ------------------------------------------------------------------ #

    def get_positions(self) -> List[Position]:
        raw = self._trading.get_all_positions()
        return [self._parse_position(p) for p in raw]

    def get_position(self, ticker: str) -> Optional[Position]:
        try:
            raw = self._trading.get_open_position(ticker)
            return self._parse_position(raw)
        except Exception:
            return None

    def _parse_position(self, raw) -> Position:
        return Position(
            ticker=raw.symbol,
            qty=float(raw.qty),
            avg_entry_price=float(raw.avg_entry_price),
            current_price=float(raw.current_price),
            market_value=float(raw.market_value),
            unrealized_pnl=float(raw.unrealized_pl),
            unrealized_pnl_pct=float(raw.unrealized_plpc),
            side=raw.side.value if hasattr(raw.side, "value") else str(raw.side),
        )

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
        from alpaca.trading.requests import MarketOrderRequest, LimitOrderRequest
        from alpaca.trading.enums import (
            OrderSide as AlpacaSide,
            TimeInForce,
        )

        alpaca_side = AlpacaSide.BUY if side == OrderSide.BUY else AlpacaSide.SELL
        tif = TimeInForce(time_in_force.lower())

        if order_type == OrderType.MARKET:
            req = MarketOrderRequest(
                symbol=ticker,
                qty=round(qty, 4),
                side=alpaca_side,
                time_in_force=tif,
            )
        else:
            if limit_price is None:
                raise ValueError("limit_price is required for LIMIT orders")
            req = LimitOrderRequest(
                symbol=ticker,
                qty=round(qty, 4),
                side=alpaca_side,
                time_in_force=tif,
                limit_price=round(limit_price, 2),
            )

        raw = self._trading.submit_order(req)
        logger.info(
            "Order submitted: %s %s %.4f %s @ %s (id=%s)",
            side.value.upper(),
            ticker,
            qty,
            order_type.value,
            limit_price or "MARKET",
            raw.id,
        )
        return self._parse_order(raw)

    def get_order(self, order_id: str) -> Order:
        raw = self._trading.get_order_by_id(order_id)
        return self._parse_order(raw)

    def cancel_order(self, order_id: str) -> bool:
        try:
            self._trading.cancel_order_by_id(order_id)
            return True
        except Exception as exc:
            logger.warning("Failed to cancel order %s: %s", order_id, exc)
            return False

    def get_order_history(self, limit: int = 100) -> List[Order]:
        from alpaca.trading.requests import GetOrdersRequest
        from alpaca.trading.enums import QueryOrderStatus

        req = GetOrdersRequest(status=QueryOrderStatus.ALL, limit=limit)
        raw_orders = self._trading.get_orders(req)
        return [self._parse_order(o) for o in raw_orders]

    def _parse_order(self, raw) -> Order:
        return Order(
            order_id=str(raw.id),
            ticker=raw.symbol,
            side=OrderSide.BUY if str(raw.side).lower() in ("buy", "ordersid.buy") else OrderSide.SELL,
            qty=float(raw.qty or 0),
            order_type=OrderType.LIMIT if str(raw.order_type).lower() == "limit" else OrderType.MARKET,
            status=_to_order_status(str(raw.status)),
            submitted_at=raw.submitted_at or datetime.utcnow(),
            filled_qty=float(raw.filled_qty or 0),
            filled_avg_price=float(raw.filled_avg_price) if raw.filled_avg_price else None,
            filled_at=raw.filled_at,
            limit_price=float(raw.limit_price) if raw.limit_price else None,
        )

    # ------------------------------------------------------------------ #
    # Market data                                                          #
    # ------------------------------------------------------------------ #

    def get_latest_price(self, ticker: str) -> float:
        from alpaca.data.requests import StockLatestTradeRequest

        req = StockLatestTradeRequest(symbol_or_symbols=ticker)
        trades = self._data.get_stock_latest_trade(req)
        return float(trades[ticker].price)
