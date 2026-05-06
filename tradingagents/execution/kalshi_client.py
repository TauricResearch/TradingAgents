"""Authenticated Kalshi portfolio client (orders, positions, fills).

Reuses ``KalshiAuth`` from ``dataflows/kalshi_market`` for RSA-PSS-SHA256
request signing. All write endpoints (place_order, cancel_order) and the
authenticated read endpoints (positions, fills, balance) live here.

Read-only market data (current YES/NO mid, contract metadata, recent
trades) lives in ``dataflows/kalshi_market`` because it's used by the
analyst tool surface, not the execution layer.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

import requests

from tradingagents.dataflows.kalshi_market import KalshiAuth, _load_auth

logger = logging.getLogger(__name__)

_API_BASE = "https://api.elections.kalshi.com/trade-api/v2"


class KalshiAuthError(RuntimeError):
    """Raised when Kalshi credentials are missing or invalid."""


class KalshiOrderError(RuntimeError):
    """Raised when an order placement / cancellation fails on Kalshi's side."""


def _require_auth() -> KalshiAuth:
    auth = _load_auth()
    if auth is None:
        raise KalshiAuthError(
            "Kalshi credentials missing. Set KALSHI_API_KEY_ID and "
            "KALSHI_PRIVATE_KEY_PATH (or override the env-var names in "
            "DEFAULT_CONFIG['kalshi'])."
        )
    return auth


def _signed_request(method: str, path: str, body: Optional[Dict] = None) -> Dict:
    """Issue a signed ``method`` request to ``path`` and return the parsed JSON.

    Raises:
        KalshiAuthError: when credentials are missing.
        KalshiOrderError: on any non-2xx response (with the venue message).
    """
    auth = _require_auth()
    url = f"{_API_BASE}{path}"
    headers = auth.headers(method, path)

    try:
        resp = requests.request(
            method,
            url,
            headers=headers,
            data=json.dumps(body) if body is not None else None,
            timeout=15,
        )
    except requests.RequestException as e:
        raise KalshiOrderError(f"Kalshi {method} {path} network error: {e}") from e

    if not resp.ok:
        raise KalshiOrderError(
            f"Kalshi {method} {path} returned {resp.status_code}: {resp.text[:300]}"
        )

    if not resp.content:
        return {}
    return resp.json()


# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------


def place_order(
    *,
    contract_id: str,
    side: str,
    count: int,
    order_type: str = "limit",
    price_cents: Optional[int] = None,
    client_order_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Place a buy order on a Kalshi contract.

    Args:
        contract_id: Kalshi contract ticker (e.g. ``KXBTCD-26MAY05-T100000``).
        side: ``"yes"`` or ``"no"``.
        count: Number of contracts to buy.
        order_type: ``"limit"`` (default) or ``"market"``.
        price_cents: Limit price in cents [1, 99]. Required for limit orders.
        client_order_id: Optional idempotency key — pass to dedupe retries.

    Returns:
        The Kalshi ``{"order": {...}}`` payload as a dict. The ``order_id``
        field is what the reconciler tracks.
    """
    side_lc = side.strip().lower()
    if side_lc not in {"yes", "no"}:
        raise ValueError(f"side must be 'yes' or 'no', got {side!r}")
    if order_type not in {"limit", "market"}:
        raise ValueError(f"order_type must be 'limit' or 'market', got {order_type!r}")
    if order_type == "limit" and price_cents is None:
        raise ValueError("limit orders require price_cents")
    if count <= 0:
        raise ValueError("count must be positive")

    body: Dict[str, Any] = {
        "ticker": contract_id,
        "side": side_lc,
        "action": "buy",
        "count": int(count),
        "type": order_type,
    }
    if price_cents is not None:
        body["yes_price" if side_lc == "yes" else "no_price"] = int(price_cents)
    if client_order_id is not None:
        body["client_order_id"] = client_order_id

    logger.info(
        "Submitting Kalshi order: %s %s x%d %s%s",
        contract_id, side_lc.upper(), count, order_type,
        f" @ {price_cents}c" if price_cents is not None else "",
    )
    return _signed_request("POST", "/portfolio/orders", body=body)


def cancel_order(order_id: str) -> Dict[str, Any]:
    """Cancel a previously-submitted order by its venue order id."""
    return _signed_request("DELETE", f"/portfolio/orders/{order_id}")


def get_order(order_id: str) -> Dict[str, Any]:
    """Fetch the current state of a single order (status, fills, ...)."""
    return _signed_request("GET", f"/portfolio/orders/{order_id}")


# ---------------------------------------------------------------------------
# Portfolio reads (used by the reconciler)
# ---------------------------------------------------------------------------


def get_positions() -> List[Dict]:
    """List current open positions on the connected Kalshi account."""
    payload = _signed_request("GET", "/portfolio/positions")
    return payload.get("market_positions") or payload.get("positions") or []


def get_fills(ticker: Optional[str] = None, limit: int = 50) -> List[Dict]:
    """Recent fills for the connected account (optionally filtered by ticker)."""
    path = "/portfolio/fills"
    if ticker is not None:
        path = f"{path}?ticker={ticker}&limit={limit}"
    else:
        path = f"{path}?limit={limit}"
    payload = _signed_request("GET", path)
    return payload.get("fills") or []


def get_balance() -> Dict[str, Any]:
    """Cash balance on the connected Kalshi account."""
    return _signed_request("GET", "/portfolio/balance")
