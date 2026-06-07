"""Alpaca paper-trading adapter (REST).

Network-bound; used in integration, not unit tests. Reads credentials from the
environment (``ALPACA_API_KEY`` / ``ALPACA_SECRET_KEY``) and defaults to the
paper endpoint. Implemented over ``requests`` to avoid an extra SDK dependency.
"""

from __future__ import annotations

import os
from typing import Any, Optional

from .base import BrokerOrder, OrderRequest, OrderStatus

_PAPER_URL = "https://paper-api.alpaca.markets"
_LIVE_URL = "https://api.alpaca.markets"


def alpaca_base_url(mode: str) -> str:
    """Resolve the Alpaca REST base URL for ``mode`` ('paper' | 'live')."""
    return _LIVE_URL if mode == "live" else _PAPER_URL

_STATUS_MAP = {
    "filled": OrderStatus.FILLED,
    "partially_filled": OrderStatus.ACCEPTED,
    "new": OrderStatus.ACCEPTED,
    "accepted": OrderStatus.ACCEPTED,
    "pending_new": OrderStatus.PENDING,
    "rejected": OrderStatus.REJECTED,
    "canceled": OrderStatus.CANCELLED,
    "cancelled": OrderStatus.CANCELLED,
    "expired": OrderStatus.CANCELLED,
}


class AlpacaBroker:
    def __init__(
        self,
        api_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        base_url: str = _PAPER_URL,
    ):
        self.api_key = api_key or os.environ.get("ALPACA_API_KEY", "")
        self.secret_key = secret_key or os.environ.get("ALPACA_SECRET_KEY", "")
        self.base_url = base_url.rstrip("/")
        if not (self.api_key and self.secret_key):
            raise RuntimeError("Alpaca credentials missing (ALPACA_API_KEY/SECRET_KEY)")

    # -- helpers ---------------------------------------------------------
    @property
    def _headers(self) -> dict[str, str]:
        return {
            "APCA-API-KEY-ID": self.api_key,
            "APCA-API-SECRET-KEY": self.secret_key,
        }

    def _to_order(self, data: dict[str, Any]) -> BrokerOrder:
        status = _STATUS_MAP.get(str(data.get("status", "")).lower(), OrderStatus.PENDING)
        filled_avg = data.get("filled_avg_price")
        return BrokerOrder(
            client_order_id=data.get("client_order_id", ""),
            broker_order_id=data.get("id"),
            status=status,
            symbol=data.get("symbol", ""),
            side=data.get("side", ""),
            quantity=float(data.get("qty", 0) or 0),
            filled_quantity=float(data.get("filled_qty", 0) or 0),
            filled_avg_price=float(filled_avg) if filled_avg else None,
            raw=data,
        )

    # -- Broker interface ------------------------------------------------
    def submit_order(self, req: OrderRequest) -> BrokerOrder:
        import requests

        payload: dict[str, Any] = {
            "symbol": req.symbol,
            "qty": req.quantity,
            "side": req.side,
            "type": req.order_type,
            "time_in_force": "day",
        }
        if req.limit_price is not None:
            payload["limit_price"] = req.limit_price
        if req.client_order_id:
            payload["client_order_id"] = req.client_order_id
        if req.stop_loss is not None or req.take_profit is not None:
            payload["order_class"] = "bracket"
            if req.take_profit is not None:
                payload["take_profit"] = {"limit_price": req.take_profit}
            if req.stop_loss is not None:
                payload["stop_loss"] = {"stop_price": req.stop_loss}

        resp = requests.post(
            f"{self.base_url}/v2/orders", json=payload, headers=self._headers, timeout=15
        )
        resp.raise_for_status()
        return self._to_order(resp.json())

    def get_order(self, client_order_id: str) -> Optional[BrokerOrder]:
        import requests

        resp = requests.get(
            f"{self.base_url}/v2/orders:by_client_order_id",
            params={"client_order_id": client_order_id},
            headers=self._headers,
            timeout=15,
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return self._to_order(resp.json())

    def get_positions(self) -> list[dict[str, Any]]:
        import requests

        resp = requests.get(f"{self.base_url}/v2/positions", headers=self._headers, timeout=15)
        resp.raise_for_status()
        return resp.json()

    def get_account(self) -> dict[str, Any]:
        import requests

        resp = requests.get(f"{self.base_url}/v2/account", headers=self._headers, timeout=15)
        resp.raise_for_status()
        return resp.json()
