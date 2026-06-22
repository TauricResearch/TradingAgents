"""Toss Securities order-execution and account broker.

Wraps the account, asset, and order endpoints of the Toss Open API into a small
broker interface used by the semi-automated trading flow. Read methods (account,
holdings, buying power, current price) are safe to call freely; ``place_order``
submits a real order and should only be invoked after explicit user confirmation.

Symbols determine market and currency automatically: a 6-digit numeric code is
treated as KRX/KRW, anything else as US/USD.
"""

import re
from typing import Optional

from tradingagents.dataflows.toss_client import TossClient
from tradingagents.dataflows.toss import _toss_symbol

_KRX_SYMBOL = re.compile(r"^\d{6}$")


def market_of(symbol: str) -> str:
    """Return 'KR' for a 6-digit KRX code, otherwise 'US'."""
    return "KR" if _KRX_SYMBOL.match(_toss_symbol(symbol)) else "US"


def currency_of(symbol: str) -> str:
    """Return the trading currency for a symbol ('KRW' or 'USD')."""
    return "KRW" if market_of(symbol) == "KR" else "USD"


class TossBroker:
    """Account and order operations against a single Toss account."""

    def __init__(self, account_seq: Optional[int] = None):
        self._client = TossClient.instance()
        self._account_seq = account_seq if account_seq is not None else self._first_account_seq()

    @property
    def account_seq(self) -> int:
        return self._account_seq

    def _first_account_seq(self) -> int:
        accounts = self.accounts()
        if not accounts:
            raise RuntimeError("No Toss accounts available for these credentials.")
        return accounts[0]["accountSeq"]

    # -- read (safe) --------------------------------------------------------

    def accounts(self) -> list:
        """List accounts for the authenticated client."""
        return self._client.request("GET", "/api/v1/accounts")["result"]

    def holdings(self) -> dict:
        """Holdings with per-item detail and aggregate valuation."""
        return self._client.request(
            "GET", "/api/v1/holdings", account_seq=self._account_seq
        )["result"]

    def buying_power(self, currency: str) -> dict:
        """Cash buying power for the given currency ('KRW' or 'USD')."""
        return self._client.request(
            "GET",
            "/api/v1/buying-power",
            params={"currency": currency},
            account_seq=self._account_seq,
        )["result"]

    def sellable_quantity(self, symbol: str) -> dict:
        """Quantity of a held symbol that can currently be sold."""
        return self._client.request(
            "GET",
            "/api/v1/sellable-quantity",
            params={"symbol": symbol},
            account_seq=self._account_seq,
        )["result"]

    def last_price(self, symbol: str) -> dict:
        """Latest price for a single symbol."""
        prices = self._client.request(
            "GET", "/api/v1/prices", params={"symbols": symbol}
        )["result"]
        return prices[0] if prices else {}

    def get_order(self, order_id: str) -> dict:
        """Order detail for any status."""
        return self._client.request(
            "GET", f"/api/v1/orders/{order_id}", account_seq=self._account_seq
        )["result"]

    def open_orders(self, symbol: Optional[str] = None) -> dict:
        """Pending (OPEN) orders, optionally filtered by symbol."""
        params = {"status": "OPEN"}
        if symbol:
            params["symbol"] = symbol
        return self._client.request(
            "GET", "/api/v1/orders", params=params, account_seq=self._account_seq
        )["result"]

    # -- write (live orders) ------------------------------------------------

    def place_order(
        self,
        symbol: str,
        side: str,
        order_type: str = "LIMIT",
        *,
        quantity: Optional[str] = None,
        price: Optional[str] = None,
        order_amount: Optional[str] = None,
        time_in_force: str = "DAY",
        client_order_id: Optional[str] = None,
        confirm_high_value: bool = False,
    ) -> dict:
        """Submit a live order. Returns {orderId, clientOrderId}.

        - Quantity-based: pass ``quantity`` (+ ``price`` for LIMIT).
        - Amount-based (US MARKET only): pass ``order_amount``.

        This places a REAL order. Callers must obtain user confirmation first.
        """
        symbol = _toss_symbol(symbol)
        side = side.upper()
        order_type = order_type.upper()
        if side not in ("BUY", "SELL"):
            raise ValueError(f"side must be BUY or SELL, got {side!r}")
        if order_type not in ("LIMIT", "MARKET"):
            raise ValueError(f"order_type must be LIMIT or MARKET, got {order_type!r}")

        body: dict = {"symbol": symbol, "side": side, "orderType": order_type}

        if order_amount is not None:
            if order_type != "MARKET":
                raise ValueError("Amount-based orders must use MARKET order_type.")
            body["orderAmount"] = str(order_amount)
        else:
            if quantity is None:
                raise ValueError("Provide either quantity or order_amount.")
            body["quantity"] = str(quantity)
            if order_type == "LIMIT":
                if price is None:
                    raise ValueError("LIMIT orders require a price.")
                body["price"] = str(price)
            body["timeInForce"] = time_in_force

        if client_order_id is not None:
            body["clientOrderId"] = client_order_id
        if confirm_high_value:
            body["confirmHighValueOrder"] = True

        return self._client.request(
            "POST", "/api/v1/orders", json=body, account_seq=self._account_seq
        )["result"]

    def cancel_order(self, order_id: str) -> dict:
        """Cancel a pending order."""
        return self._client.request(
            "POST", f"/api/v1/orders/{order_id}/cancel", account_seq=self._account_seq
        )["result"]

    def modify_order(
        self,
        order_id: str,
        *,
        price: Optional[str] = None,
        quantity: Optional[str] = None,
    ) -> dict:
        """Modify a pending order's price and/or quantity."""
        body = {}
        if price is not None:
            body["price"] = str(price)
        if quantity is not None:
            body["quantity"] = str(quantity)
        if not body:
            raise ValueError("modify_order requires price and/or quantity.")
        return self._client.request(
            "POST",
            f"/api/v1/orders/{order_id}/modify",
            json=body,
            account_seq=self._account_seq,
        )["result"]
