"""Kalshi public market data — read-only.

This module is the *information* side of the Kalshi integration: it
fetches contract metadata, the current YES/NO mid-price, and recent
trade history, all of which feed into the Portfolio Manager's
``MarketDecision`` (specifically the ``market_p_yes`` and
``edge_bps`` fields).

The *execution* side (placing orders) lives in
``tradingagents.execution.kalshi_client`` and is built in Phase 3.

Authentication
==============

Read endpoints on Kalshi require the same API key + RSA signature as
write endpoints, so we sign every request. Credentials are read from
the env vars named in ``DEFAULT_CONFIG['kalshi']`` (``KALSHI_API_KEY_ID``
and ``KALSHI_PRIVATE_KEY_PATH``). When credentials are missing or
unreadable, helpers return a structured "missing-creds" placeholder so
agent tools can still produce a useful (degraded) report instead of
crashing the whole pipeline.
"""

from __future__ import annotations

import base64
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

import requests

logger = logging.getLogger(__name__)

_API_BASE = "https://api.elections.kalshi.com/trade-api/v2"


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------


class KalshiAuth:
    """Holds Kalshi credentials and signs outgoing requests.

    Sign format (RSA-PSS-SHA256):
        message = f"{timestamp_ms}{method}{path}"
        signature = base64( RSASSA-PSS-SHA256( private_key, message ) )

    Headers attached:
        KALSHI-ACCESS-KEY        — API key id
        KALSHI-ACCESS-SIGNATURE  — base64 signature
        KALSHI-ACCESS-TIMESTAMP  — millisecond epoch as string
    """

    def __init__(self, api_key_id: str, private_key_pem: bytes):
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding

        self._api_key_id = api_key_id
        self._private_key = serialization.load_pem_private_key(
            private_key_pem, password=None
        )
        self._padding = padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.DIGEST_LENGTH,
        )
        self._hash = hashes.SHA256()

    def headers(self, method: str, path: str) -> Dict[str, str]:
        timestamp_ms = str(int(time.time() * 1000))
        message = f"{timestamp_ms}{method.upper()}{path}".encode("utf-8")
        signature = self._private_key.sign(message, self._padding, self._hash)
        return {
            "KALSHI-ACCESS-KEY": self._api_key_id,
            "KALSHI-ACCESS-SIGNATURE": base64.b64encode(signature).decode("ascii"),
            "KALSHI-ACCESS-TIMESTAMP": timestamp_ms,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }


def _load_auth() -> Optional[KalshiAuth]:
    """Load Kalshi creds from the env vars configured in DEFAULT_CONFIG.

    Returns ``None`` (and logs a warning) when either env var is unset
    or the key file is unreadable. Callers must handle the ``None`` case.
    """
    from tradingagents.dataflows.config import get_config

    cfg = get_config().get("kalshi", {})
    key_id_var = cfg.get("api_key_id_env", "KALSHI_API_KEY_ID")
    key_path_var = cfg.get("private_key_path_env", "KALSHI_PRIVATE_KEY_PATH")

    api_key_id = os.environ.get(key_id_var)
    key_path = os.environ.get(key_path_var)

    if not api_key_id or not key_path:
        logger.debug(
            "Kalshi creds missing: %s=%s, %s=%s",
            key_id_var, bool(api_key_id), key_path_var, bool(key_path),
        )
        return None

    try:
        pem = Path(key_path).expanduser().read_bytes()
    except OSError as e:
        logger.warning("Could not read Kalshi private key at %s: %s", key_path, e)
        return None

    try:
        return KalshiAuth(api_key_id=api_key_id, private_key_pem=pem)
    except Exception as e:  # noqa: BLE001 — surface a clear log instead of crashing
        logger.warning("Failed to load Kalshi private key: %s", e)
        return None


# ---------------------------------------------------------------------------
# Public read API
# ---------------------------------------------------------------------------


def _signed_get(path: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict]:
    """Issue a signed GET to Kalshi. Returns parsed JSON or None on failure."""
    auth = _load_auth()
    if auth is None:
        return None

    url = f"{_API_BASE}{path}"
    try:
        r = requests.get(url, headers=auth.headers("GET", path), params=params, timeout=15)
        r.raise_for_status()
        return r.json()
    except requests.RequestException as e:
        logger.warning("Kalshi GET %s failed: %s", path, e)
        return None


def get_market(contract_id: str) -> Optional[Dict[str, Any]]:
    """Fetch metadata + current pricing for a Kalshi market by ticker."""
    data = _signed_get(f"/markets/{contract_id}")
    if data is None:
        return None
    return data.get("market") or data


def get_market_orderbook(contract_id: str) -> Optional[Dict[str, Any]]:
    """Fetch the YES/NO orderbook for a market."""
    data = _signed_get(f"/markets/{contract_id}/orderbook")
    return data


def get_recent_trades(contract_id: str, limit: int = 50) -> Optional[Dict[str, Any]]:
    """Fetch recent trades for a market.

    Note: the public trades endpoint takes ``ticker`` as a query parameter.
    """
    return _signed_get("/markets/trades", params={"ticker": contract_id, "limit": limit})


# ---------------------------------------------------------------------------
# Markdown rendering for analyst prompts
# ---------------------------------------------------------------------------


def _missing_creds_message(contract_id: str) -> str:
    return (
        f"Kalshi market data for `{contract_id}` is unavailable: "
        "KALSHI_API_KEY_ID or KALSHI_PRIVATE_KEY_PATH is unset, or the private "
        "key file is unreadable. Set both env vars and re-run to populate this "
        "section. The pipeline continues with the other analyst inputs."
    )


def render_market_markdown(contract_id: str) -> str:
    """Compact markdown summary of a Kalshi market for analyst prompts."""
    market = get_market(contract_id)
    if market is None:
        return _missing_creds_message(contract_id)

    yes_bid = market.get("yes_bid")
    yes_ask = market.get("yes_ask")
    no_bid = market.get("no_bid")
    no_ask = market.get("no_ask")
    last = market.get("last_price")

    def _fmt(cents: Optional[float]) -> str:
        if cents is None:
            return "—"
        try:
            return f"{float(cents) / 100:.2f}"
        except (TypeError, ValueError):
            return str(cents)

    lines = [
        f"### Kalshi Market: `{contract_id}`",
        "",
        f"- Title: {market.get('title') or market.get('subtitle') or '—'}",
        f"- Status: {market.get('status', '—')}",
        f"- Open Time: {market.get('open_time', '—')}",
        f"- Close Time: {market.get('close_time', '—')}",
        f"- Settlement Source: {market.get('settlement_source') or 'Coinbase BTC-USD index (typical)'}",
        "",
        "| Side | Bid | Ask |",
        "|---|---:|---:|",
        f"| YES | {_fmt(yes_bid)} | {_fmt(yes_ask)} |",
        f"| NO  | {_fmt(no_bid)} | {_fmt(no_ask)} |",
        "",
        f"Last trade: {_fmt(last)}",
    ]
    return "\n".join(lines)


def get_market_p_yes(contract_id: str) -> Optional[float]:
    """Best-available implied probability for the YES side, in [0, 1].

    Order of preference: midpoint of YES bid/ask, last trade price, YES bid.
    Returns ``None`` when no pricing data is available.
    """
    market = get_market(contract_id)
    if market is None:
        return None

    yes_bid = market.get("yes_bid")
    yes_ask = market.get("yes_ask")
    last = market.get("last_price")

    def _to_dollars(cents: Any) -> Optional[float]:
        if cents in (None, ""):
            return None
        try:
            return float(cents) / 100
        except (TypeError, ValueError):
            return None

    bid = _to_dollars(yes_bid)
    ask = _to_dollars(yes_ask)
    if bid is not None and ask is not None:
        return (bid + ask) / 2
    if last is not None:
        return _to_dollars(last)
    if bid is not None:
        return bid
    return None
