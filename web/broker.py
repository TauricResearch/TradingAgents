"""Alpaca broker integration for confirmed live/paper order execution.

Maps the framework's 5-tier rating (Buy/Overweight/Hold/Underweight/Sell)
to a market order via Alpaca's REST Trading API. Designed so the web layer
proposes an order and only places it after explicit user confirmation.

Configuration (environment variables):
    ALPACA_API_KEY      - Alpaca API key id (required to enable trading)
    ALPACA_SECRET_KEY   - Alpaca API secret (required)
    ALPACA_PAPER        - "true" routes to the paper endpoint; anything else
                          (or unset) uses the LIVE endpoint. Keys must match
                          the chosen endpoint.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

import requests

_LIVE_URL = "https://api.alpaca.markets"
_PAPER_URL = "https://paper-api.alpaca.markets"

# Rating -> order side. Hold (and anything unmapped) means "no trade".
_RATING_SIDE = {
    "buy": "buy",
    "overweight": "buy",
    "sell": "sell",
    "underweight": "sell",
    "hold": None,
}


def rating_to_side(rating: str) -> Optional[str]:
    """Translate a 5-tier rating into an Alpaca order side, or None for Hold."""
    return _RATING_SIDE.get((rating or "").strip().lower())


class AlpacaBroker:
    """Thin Alpaca Trading API wrapper used by the web app."""

    def __init__(self):
        self.api_key = os.getenv("ALPACA_API_KEY", "").strip()
        self.secret_key = os.getenv("ALPACA_SECRET_KEY", "").strip()
        self.paper = os.getenv("ALPACA_PAPER", "false").strip().lower() in (
            "true", "1", "yes", "on",
        )
        self.base_url = _PAPER_URL if self.paper else _LIVE_URL

    # -- configuration -----------------------------------------------------

    def is_configured(self) -> bool:
        return bool(self.api_key and self.secret_key)

    @property
    def mode(self) -> str:
        return "paper" if self.paper else "live"

    def _headers(self) -> Dict[str, str]:
        return {
            "APCA-API-KEY-ID": self.api_key,
            "APCA-API-SECRET-KEY": self.secret_key,
        }

    # -- reads -------------------------------------------------------------

    def get_account(self) -> Dict[str, Any]:
        """Return key account fields; raises on auth/connection error."""
        resp = requests.get(
            f"{self.base_url}/v2/account", headers=self._headers(), timeout=15
        )
        resp.raise_for_status()
        a = resp.json()
        return {
            "status": a.get("status"),
            "currency": a.get("currency"),
            "cash": a.get("cash"),
            "buying_power": a.get("buying_power"),
            "portfolio_value": a.get("portfolio_value"),
            "trading_blocked": a.get("trading_blocked"),
            "account_number": a.get("account_number"),
        }

    def get_position(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Return the open position for symbol, or None if flat."""
        resp = requests.get(
            f"{self.base_url}/v2/positions/{symbol}",
            headers=self._headers(),
            timeout=15,
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        p = resp.json()
        return {"qty": p.get("qty"), "market_value": p.get("market_value")}

    # -- writes ------------------------------------------------------------

    def place_order(
        self,
        symbol: str,
        side: str,
        notional: Optional[float] = None,
        qty: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Submit a market order. Provide exactly one of notional or qty.

        Returns selected fields from the created order. Raises requests
        HTTPError (with the broker's message attached) on rejection.
        """
        if side not in ("buy", "sell"):
            raise ValueError(f"Invalid side: {side!r}")
        if bool(notional) == bool(qty):
            raise ValueError("Provide exactly one of notional or qty")

        payload: Dict[str, Any] = {
            "symbol": symbol,
            "side": side,
            "type": "market",
            "time_in_force": "day",
        }
        if notional:
            payload["notional"] = round(float(notional), 2)
        else:
            payload["qty"] = qty

        resp = requests.post(
            f"{self.base_url}/v2/orders",
            headers=self._headers(),
            json=payload,
            timeout=20,
        )
        if resp.status_code >= 400:
            # Surface Alpaca's human-readable reason rather than a bare 4xx.
            try:
                detail = resp.json().get("message", resp.text)
            except Exception:
                detail = resp.text
            raise requests.HTTPError(f"Alpaca order rejected: {detail}")

        o = resp.json()
        return {
            "id": o.get("id"),
            "symbol": o.get("symbol"),
            "side": o.get("side"),
            "type": o.get("type"),
            "qty": o.get("qty"),
            "notional": o.get("notional"),
            "status": o.get("status"),
            "submitted_at": o.get("submitted_at"),
        }
