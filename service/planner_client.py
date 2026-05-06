"""Client for the user's separate Financial Planner application.

The planner runs on the same NAS at a different port. We pull its
holdings (and the account names they belong to) and sync them into our
local ``positions`` table.

Configuration via env vars (read each call so a Settings page can update
them at runtime without a restart):

    PLANNER_API_URL    e.g. http://192.168.2.34:8765
    PLANNER_API_KEY    same value as INTEGRATION_API_KEY in the planner

When either is unset, ``is_configured()`` returns False and the API
returns a 412 Precondition Failed so the UI can render a "configure
this on Settings" message.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import requests

CONNECT_TIMEOUT = 5.0
READ_TIMEOUT = 30.0


def planner_url() -> Optional[str]:
    raw = (os.environ.get("PLANNER_API_URL") or "").strip().rstrip("/")
    return raw or None


def planner_key() -> Optional[str]:
    raw = (os.environ.get("PLANNER_API_KEY") or "").strip()
    return raw or None


def is_configured() -> bool:
    return bool(planner_url() and planner_key())


def _headers() -> Dict[str, str]:
    key = planner_key() or ""
    return {
        "X-API-Key": key,
        "Authorization": f"Bearer {key}",
        "Accept": "application/json",
    }


class PlannerClientError(Exception):
    """Raised when the planner returns an unexpected response."""


def _get(path: str) -> Any:
    url = planner_url()
    if not url:
        raise PlannerClientError("PLANNER_API_URL not configured")
    if not planner_key():
        raise PlannerClientError("PLANNER_API_KEY not configured")
    full = f"{url}{path}"
    try:
        resp = requests.get(
            full,
            headers=_headers(),
            timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
        )
    except requests.RequestException as e:
        raise PlannerClientError(f"could not reach planner at {full}: {e}")
    if resp.status_code == 401:
        raise PlannerClientError(
            "planner returned 401 — check that PLANNER_API_KEY matches "
            "INTEGRATION_API_KEY on the planner side"
        )
    if not resp.ok:
        raise PlannerClientError(
            f"planner {path} returned {resp.status_code}: {resp.text[:200]}"
        )
    try:
        return resp.json()
    except ValueError as e:
        raise PlannerClientError(f"planner {path} returned non-JSON: {e}")


def list_accounts() -> List[Dict[str, Any]]:
    """Return all accounts known to the planner."""
    raw = _get("/api/accounts")
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict) and "accounts" in raw:
        return list(raw["accounts"])
    raise PlannerClientError(f"unexpected /api/accounts shape: {type(raw)}")


def list_holdings() -> Dict[str, Any]:
    """Return the planner's holdings response.

    Shape (from backend/routers/investments.py):
        {
          "holdings": [
            {"id":..., "account_id":..., "symbol":..., "name":..., "asset_type":...,
             "quantity":..., "avg_cost_basis":..., "current_price":...,
             "current_value":..., "gain_loss":..., "gain_loss_pct":...,
             "last_priced_at":..., "source":...},
            ...
          ],
          "total_value": ...,
          "allocation": {...}
        }
    """
    raw = _get("/api/investments/holdings")
    if not isinstance(raw, dict) or "holdings" not in raw:
        raise PlannerClientError(f"unexpected /api/investments/holdings shape: {type(raw)}")
    return raw


def healthcheck() -> Dict[str, Any]:
    """Lightweight probe — returns the (possibly anonymous) /api/health."""
    url = planner_url()
    if not url:
        return {"ok": False, "error": "PLANNER_API_URL not configured"}
    try:
        resp = requests.get(
            f"{url}/api/health",
            headers=_headers(),
            timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
        )
    except requests.RequestException as e:
        return {"ok": False, "error": str(e)}
    return {
        "ok": resp.ok,
        "status_code": resp.status_code,
        "body": resp.text[:200] if not resp.ok else None,
    }
