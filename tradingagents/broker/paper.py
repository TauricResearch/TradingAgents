"""In-process paper broker: instant fills, idempotent submits.

Good enough for tests and a local paper-trading loop. Tracks cash and positions
so ``get_account`` / ``get_positions`` are meaningful. Submitting the same
``client_order_id`` twice returns the existing order (anti double-order).
"""

from __future__ import annotations

import uuid
from typing import Any, Optional

from .base import BrokerOrder, OrderRequest, OrderStatus


class PaperBroker:
    def __init__(self, cash: float = 100_000.0, assets: Optional[list[dict[str, Any]]] = None):
        self._cash = cash
        self._positions: dict[str, float] = {}
        self._orders: dict[str, BrokerOrder] = {}
        self._assets = assets or []  # optional static universe for tests/local

    def list_assets(self) -> list[dict[str, Any]]:
        return list(self._assets)

    # -- Broker interface ------------------------------------------------
    def submit_order(self, req: OrderRequest) -> BrokerOrder:
        coid = req.client_order_id or uuid.uuid4().hex
        if coid in self._orders:
            return self._orders[coid]  # idempotent

        fill_price = req.limit_price if req.limit_price is not None else 0.0
        signed = req.quantity if req.side == "buy" else -req.quantity
        self._positions[req.symbol] = self._positions.get(req.symbol, 0.0) + signed
        self._cash -= signed * fill_price

        order = BrokerOrder(
            client_order_id=coid,
            broker_order_id=f"paper-{uuid.uuid4().hex[:12]}",
            status=OrderStatus.FILLED,
            symbol=req.symbol,
            side=req.side,
            quantity=req.quantity,
            filled_quantity=req.quantity,
            filled_avg_price=fill_price,
        )
        self._orders[coid] = order
        return order

    def get_order(self, client_order_id: str) -> Optional[BrokerOrder]:
        return self._orders.get(client_order_id)

    def get_positions(self) -> list[dict[str, Any]]:
        return [
            {"symbol": sym, "qty": qty}
            for sym, qty in self._positions.items()
            if qty != 0
        ]

    def get_account(self) -> dict[str, Any]:
        return {"cash": self._cash, "positions": self.get_positions()}
