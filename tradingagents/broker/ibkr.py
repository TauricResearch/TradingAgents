"""Interactive Brokers adapter — TWS API (the most complete IBKR interface).

Uses the native TWS API via ``ib_async`` (the maintained successor to ib_insync,
by ib-api-reloaded) — the most powerful/complete IBKR tooling, covering the full
range of contracts and order types. Requires a running TWS or IB Gateway and
``pip install ib_async``; network/app bound, so it is integration-only, while
the pure mapping helpers are unit-tested.

Docs: https://ib-api-reloaded.github.io/ib_async/ ·
https://www.interactivebrokers.com/campus/ibkr-api-page/twsapi-doc/
Default ports: TWS 7497 (paper) / 7496 (live); IB Gateway 4002 (paper) /
4001 (live) — override ``port`` for the Gateway.
"""

from __future__ import annotations

from typing import Any, Optional

from .base import BrokerOrder, OrderRequest, OrderStatus

# ib_async OrderStatus.status -> our OrderStatus.
_STATUS_MAP = {
    "Filled": OrderStatus.FILLED,
    "Submitted": OrderStatus.ACCEPTED,
    "PreSubmitted": OrderStatus.ACCEPTED,
    "PendingSubmit": OrderStatus.PENDING,
    "ApiPending": OrderStatus.PENDING,
    "PendingCancel": OrderStatus.PENDING,
    "Cancelled": OrderStatus.CANCELLED,
    "ApiCancelled": OrderStatus.CANCELLED,
    "Inactive": OrderStatus.REJECTED,
    "ValidationError": OrderStatus.REJECTED,
}


def map_status(status: Any) -> OrderStatus:
    return _STATUS_MAP.get(str(status), OrderStatus.PENDING)


def order_action(req: OrderRequest) -> str:
    """IBKR action — BUY / SELL."""
    return req.side.upper()


def default_port(mode: str) -> int:
    """Default TWS port: 7496 live, 7497 paper (override for IB Gateway)."""
    return 7496 if mode == "live" else 7497


class IBKRBroker:
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 7497,
        client_id: int = 1,
        account: Optional[str] = None,
        *,
        settle_seconds: float = 1.0,
    ):
        self.host = host
        self.port = port
        self.client_id = client_id
        self.account = account
        self.settle_seconds = settle_seconds
        self._ib = None

    # -- connection ------------------------------------------------------
    def _conn(self):
        if self._ib is None or not self._ib.isConnected():
            import ib_async

            self._ib = ib_async.IB()
            self._ib.connect(self.host, self.port, clientId=self.client_id)
        return self._ib

    def disconnect(self) -> None:
        if self._ib is not None and self._ib.isConnected():
            self._ib.disconnect()

    def _contract(self, symbol: str):
        from ib_async import Stock

        contract = Stock(symbol.upper(), "SMART", "USD")
        self._conn().qualifyContracts(contract)
        return contract

    def _order(self, req: OrderRequest):
        from ib_async import LimitOrder, MarketOrder

        action = order_action(req)
        if req.order_type in ("limit", "stop_limit") and req.limit_price is not None:
            order = LimitOrder(action, req.quantity, req.limit_price)
        else:
            order = MarketOrder(action, req.quantity)
        if req.client_order_id:
            order.orderRef = req.client_order_id  # our idempotency reference
        return order

    def _trade_to_order(self, trade: Any, req: OrderRequest) -> BrokerOrder:
        st = trade.orderStatus
        return BrokerOrder(
            client_order_id=req.client_order_id or getattr(trade.order, "orderRef", "") or "",
            broker_order_id=str(getattr(trade.order, "orderId", "") or "") or None,
            status=map_status(getattr(st, "status", None)),
            symbol=req.symbol,
            side=req.side,
            quantity=req.quantity,
            filled_quantity=float(getattr(st, "filled", 0) or 0),
            filled_avg_price=(float(getattr(st, "avgFillPrice", 0) or 0) or None),
            raw={"status": getattr(st, "status", None)},
        )

    # -- Broker interface ------------------------------------------------
    def submit_order(self, req: OrderRequest) -> BrokerOrder:
        ib = self._conn()
        trade = ib.placeOrder(self._contract(req.symbol), self._order(req))
        ib.sleep(self.settle_seconds)  # let the status update
        return self._trade_to_order(trade, req)

    def get_order(self, client_order_id: str) -> Optional[BrokerOrder]:
        for trade in self._conn().trades():
            if getattr(trade.order, "orderRef", None) == client_order_id:
                req = OrderRequest(
                    symbol=trade.contract.symbol,
                    side=str(trade.order.action).lower(),
                    quantity=float(trade.order.totalQuantity or 0),
                    client_order_id=client_order_id,
                )
                return self._trade_to_order(trade, req)
        return None

    def get_positions(self) -> list[dict[str, Any]]:
        return [
            {"symbol": p.contract.symbol, "qty": p.position}
            for p in self._conn().positions()
        ]

    def get_account(self) -> dict[str, Any]:
        cash = 0.0
        for value in self._conn().accountSummary():
            if value.tag == "TotalCashValue":
                cash = float(value.value)
        return {"cash": cash, "positions": self.get_positions()}

    def list_assets(self) -> list[dict[str, Any]]:
        """IBKR (TWS API) has no clean 'list the whole universe' call — the
        universe for IBKR comes from the S&P 500 seed instead. Returns []."""
        return []
