from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import List

logger = logging.getLogger(__name__)


@dataclass
class Position:
    ticker: str
    shares: float
    cost_basis: float
    current_price: float
    sector: str
    market_value: float


@dataclass
class Portfolio:
    positions: List[Position]
    cash: float
    source: str  # "live" or "fallback"


# ── Settings ──────────────────────────────────────────────────────────────────

def load_settings(data_dir: str) -> dict:
    """Load user settings from {data_dir}/settings.json."""
    path = os.path.join(data_dir, "settings.json")
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_settings(data_dir: str, patch: dict) -> None:
    """Merge patch into {data_dir}/settings.json."""
    os.makedirs(data_dir, exist_ok=True)
    existing = load_settings(data_dir)
    existing.update(patch)
    path = os.path.join(data_dir, "settings.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=2)


def _get_credentials(data_dir: str) -> tuple[str, str]:
    """Return (username, password): settings.json first, env var fallback."""
    s = load_settings(data_dir)
    username = s.get("robinhood_username") or os.environ.get("ROBINHOOD_USERNAME", "")
    password = s.get("robinhood_password") or os.environ.get("ROBINHOOD_PASSWORD", "")
    return username, password


# ── Portfolio loading ─────────────────────────────────────────────────────────

def load_portfolio(data_dir: str) -> Portfolio:
    try:
        portfolio = _load_from_robinhood(data_dir)
        logger.info("Portfolio loaded from Robinhood (%d positions)", len(portfolio.positions))
        return portfolio
    except Exception as exc:
        logger.warning("robin_stocks failed (%s); falling back to portfolio.json", exc)
        return _load_from_json(data_dir)


def _load_from_robinhood(data_dir: str) -> Portfolio:
    import robin_stocks.robinhood as rh

    username, password = _get_credentials(data_dir)
    if not username or not password:
        raise ValueError("Robinhood credentials not configured. Use Settings to add them.")

    # store_session persists the device token so subsequent logins skip MFA.
    rh.login(username, password, store_session=True)

    positions_raw = rh.get_open_stock_positions() or []
    cash = _get_cash(rh)

    positions: List[Position] = []
    for pos in positions_raw:
        qty = float(pos.get("quantity", 0))
        if qty == 0:
            continue

        instrument = rh.get_instrument_by_url(pos.get("instrument", "")) or {}
        ticker = instrument.get("symbol", "")
        if not ticker:
            continue

        cost_basis = float(pos.get("average_buy_price", 0))
        quote = rh.get_latest_price(ticker) or [str(cost_basis)]
        current_price = float(quote[0])

        fundamentals = rh.get_fundamentals(ticker) or [{}]
        sector = (fundamentals[0] or {}).get("sector", "Unknown")

        positions.append(Position(
            ticker=ticker,
            shares=qty,
            cost_basis=cost_basis,
            current_price=current_price,
            sector=sector,
            market_value=qty * current_price,
        ))

    rh.logout()
    return Portfolio(positions=positions, cash=cash, source="live")


def _get_cash(rh) -> float:
    try:
        profile = rh.load_account_profile() or {}
        for field in ("portfolio_cash", "buying_power", "cash", "excess_margin"):
            val = profile.get(field)
            if val is not None:
                return float(val)
    except Exception:
        pass
    return 0.0


def _load_from_json(data_dir: str) -> Portfolio:
    path = os.path.join(data_dir, "portfolio.json")
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    positions = [Position(**p) for p in data.get("positions", [])]
    return Portfolio(positions=positions, cash=float(data.get("cash", 0)), source="fallback")


# ── Connection check (lightweight — login + profile, no position detail) ──────

def check_connection(data_dir: str) -> dict:
    """Test Robinhood connectivity without a full portfolio build.

    Returns a dict with: ok, source, cash, positions (count), error (on failure).
    Falls back to local JSON if Robinhood is unavailable.
    """
    import robin_stocks.robinhood as rh

    username, password = _get_credentials(data_dir)
    if not username or not password:
        return {
            "ok": False,
            "source": "none",
            "error": "No credentials configured. Open Settings to add them.",
        }

    rh_exc: Exception | None = None
    try:
        rh.login(username, password, store_session=True)
        profile = rh.load_account_profile() or {}
        cash: float = 0.0
        for field in ("portfolio_cash", "buying_power", "cash", "excess_margin"):
            if profile.get(field) is not None:
                cash = float(profile[field])
                break
        positions_raw = rh.get_open_stock_positions() or []
        position_count = sum(1 for p in positions_raw if float(p.get("quantity", 0)) > 0)
        rh.logout()
        return {"ok": True, "source": "live", "cash": cash, "positions": position_count}
    except Exception as exc:
        rh_exc = exc
        logger.warning("Robinhood connection check failed: %s", exc)

    # Fallback: local JSON
    try:
        portfolio = _load_from_json(data_dir)
        return {
            "ok": True,
            "source": "fallback",
            "cash": portfolio.cash,
            "positions": len(portfolio.positions),
        }
    except Exception:
        return {"ok": False, "source": "none", "error": str(rh_exc)}


# ── Re-authentication ─────────────────────────────────────────────────────────

def reauth_robinhood(data_dir: str, mfa_code: str | None = None) -> tuple[str, str | None]:
    """Attempt a fresh Robinhood login without blocking the server.

    Returns (status, message):
        ("ok", None)            — login succeeded; device token stored
        ("mfa_required", None) — MFA prompt intercepted; call again with mfa_code
        ("error", message)     — login failed for another reason
    """
    import builtins
    import robin_stocks.robinhood as rh

    username, password = _get_credentials(data_dir)
    if not username or not password:
        return ("error", "No credentials configured. Open Settings to add them.")

    if mfa_code:
        try:
            rh.login(username, password, store_session=True, mfa_code=str(mfa_code))
            return ("ok", None)
        except Exception as exc:
            return ("error", str(exc))

    # First attempt: patch builtins.input so the MFA prompt raises instead of blocking.
    _mfa_seen: list[bool] = []
    _orig_input = builtins.input

    def _catch_mfa(prompt=""):
        _mfa_seen.append(True)
        raise RuntimeError("__MFA_INTERCEPTED__")

    builtins.input = _catch_mfa
    try:
        rh.login(username, password, store_session=True)
        return ("ok", None)
    except RuntimeError:
        if _mfa_seen:
            return ("mfa_required", None)
        return ("error", "Unexpected runtime error during login")
    except Exception as exc:
        return ("error", str(exc))
    finally:
        builtins.input = _orig_input


# ── Portfolio JSON editor ─────────────────────────────────────────────────────

def save_portfolio_json(data_dir: str, positions: list, cash: float) -> None:
    path = os.path.join(data_dir, "portfolio.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"cash": cash, "positions": positions}, fh, indent=2)
