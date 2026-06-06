"""Deterministic risk engine.

Pure functions (no LLM) that encode the wiki's quantitative decisions:

- entry/stop/take-profit as ``current_price ± k·ATR`` (state-schemas: entry_price)
- risk-based / fixed-fractional position sizing (position-sizing)
- the R:R and Statute guardrails the Risk Analyst relies on

The LLM produces coefficients and judgement; the numbers are computed here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from .enums import Direction
from .state import Levels

# Conviction → risk-budget multiplier (position-sizing). Strong signals get a
# bigger slice of the base risk budget; Hold spends nothing.
CONVICTION_MULTIPLIER: dict[Direction, float] = {
    Direction.STRONG_BUY: 1.75,
    Direction.BUY: 1.0,
    Direction.HOLD: 0.0,
    Direction.SELL: 1.0,
    Direction.STRONG_SELL: 1.75,
}


def conviction_multiplier(direction: Direction) -> float:
    return CONVICTION_MULTIPLIER[direction]


# ---------------------------------------------------------------------------
# Entry / stop / take-profit in ATR units
# ---------------------------------------------------------------------------
def atr_levels(
    current_price: float,
    atr: float,
    direction: Direction,
    *,
    k_entry: float,
    k_stop: float,
    k_tp: float,
) -> Levels:
    """Translate ATR coefficients into concrete prices.

    BUY:  entry = price - k_entry·ATR ; stop = entry - k_stop·ATR ; tp = entry + k_tp·ATR
    SELL: mirrored. HOLD has no levels.
    """
    if atr <= 0:
        raise ValueError("ATR must be positive")
    if direction.is_long:
        entry = current_price - k_entry * atr
        stop = entry - k_stop * atr
        tp = entry + k_tp * atr
    elif direction.is_short:
        entry = current_price + k_entry * atr
        stop = entry + k_stop * atr
        tp = entry - k_tp * atr
    else:
        raise ValueError("HOLD has no price levels")
    return Levels(
        k_entry=k_entry, k_stop=k_stop, k_tp=k_tp,
        entry_price=entry, stop_loss=stop, take_profit=tp,
    )


def risk_reward(k_tp: float, k_stop: float) -> float:
    """R:R = reward / risk = k_tp / k_stop (the ATR units cancel out)."""
    if k_stop <= 0:
        raise ValueError("k_stop must be positive")
    return k_tp / k_stop


def passes_risk_reward(k_tp: float, k_stop: float, min_rr: float = 1.5) -> bool:
    return risk_reward(k_tp, k_stop) >= min_rr


# ---------------------------------------------------------------------------
# Risk-based position sizing
# ---------------------------------------------------------------------------
@dataclass
class SizingResult:
    quantity: float
    euro_at_risk: float
    risk_pct: float
    position_value: float
    position_pct: float
    capped_by: Optional[str] = None  # None | "portfolio_heat" | "max_position" | "no_budget"


def position_size(
    portfolio_value: float,
    current_price: float,
    stop_distance: float,
    direction: Direction,
    *,
    base_risk_pct: float = 0.01,
    heat_used_pct: float = 0.0,
    heat_max_pct: float = 0.06,
    max_position_pct: float = 0.10,
) -> SizingResult:
    """Decide *how much to risk*, derive quantity from the known stop.

    risk_% = base_risk_% · conviction_multiplier
    euro_at_risk = portfolio_value · risk_%
    quantity = euro_at_risk / stop_distance      (stop_distance = k_stop · ATR)

    Then apply the portfolio-heat cap (sum of open risks) and the per-position
    cap. Volatility-adjustment is free: a wider stop ⇒ fewer shares.
    """
    mult = conviction_multiplier(direction)
    risk_pct = base_risk_pct * mult

    if risk_pct <= 0 or stop_distance <= 0 or current_price <= 0:
        return SizingResult(0.0, 0.0, 0.0, 0.0, 0.0, capped_by="no_budget")

    capped_by: Optional[str] = None

    # Portfolio heat: cannot exceed the remaining aggregate risk budget.
    remaining = max(0.0, heat_max_pct - heat_used_pct)
    if risk_pct > remaining:
        risk_pct = remaining
        capped_by = "portfolio_heat"
    if risk_pct <= 0:
        return SizingResult(0.0, 0.0, 0.0, 0.0, 0.0, capped_by="portfolio_heat")

    euro_at_risk = portfolio_value * risk_pct
    quantity = euro_at_risk / stop_distance
    position_value = quantity * current_price

    # Per-position cap (Statute): never let one name exceed max_position_pct.
    max_value = portfolio_value * max_position_pct
    if position_value > max_value:
        quantity = max_value / current_price
        position_value = quantity * current_price
        euro_at_risk = quantity * stop_distance
        risk_pct = euro_at_risk / portfolio_value if portfolio_value else 0.0
        capped_by = "max_position"

    position_pct = position_value / portfolio_value if portfolio_value else 0.0
    return SizingResult(
        quantity=quantity,
        euro_at_risk=euro_at_risk,
        risk_pct=risk_pct,
        position_value=position_value,
        position_pct=position_pct,
        capped_by=capped_by,
    )


# ---------------------------------------------------------------------------
# Deterministic Statute guardrails (the Risk Analyst's binding checks)
# ---------------------------------------------------------------------------
_EPS = 1e-9


def check_guardrails(
    *,
    levels: Levels,
    sizing: SizingResult,
    charter: Optional[dict[str, Any]] = None,
    portfolio: Optional[dict[str, Any]] = None,
    side: str = "buy",
) -> dict[str, Any]:
    """Run the numeric Statute guardrails. Returns per-check results + all_ok.

    Thresholds come from the parametric Statute (``charter`` table); sensible
    defaults are used when a key is absent. When a ``portfolio`` snapshot is
    given, the 10% cash-reserve rule is enforced too (a buy must not eat into
    the strategic reserve). VaR and sector/geography caps need richer position
    data and are left as follow-ups.
    """
    charter = charter or {}
    min_rr = charter.get("min_risk_reward", 1.5)
    max_pos = charter.get("max_position_pct", 0.10)

    rr = risk_reward(levels.k_tp, levels.k_stop)
    checks: dict[str, Any] = {
        "risk_reward": {
            "ok": rr + _EPS >= min_rr,
            "value": rr,
            "threshold": min_rr,
        },
        "max_position": {
            "ok": sizing.position_pct <= max_pos + _EPS,
            "value": sizing.position_pct,
            "threshold": max_pos,
        },
    }

    if portfolio is not None:
        reserve_pct = charter.get("cash_reserve_pct", 0.10)
        cash = float(portfolio.get("cash", 0.0))
        total = float(portfolio.get("total_value", 0.0))
        # Only a buy consumes cash; a sell frees it.
        projected_cash = cash - (sizing.position_value if side == "buy" else 0.0)
        min_cash = reserve_pct * total
        checks["cash_reserve"] = {
            "ok": total <= 0 or projected_cash + _EPS >= min_cash,
            "projected_cash": projected_cash,
            "min_cash": min_cash,
        }

        # VaR proxy: aggregate open risk (heat) + this trade's risk must stay
        # within the portfolio VaR cap.
        max_var = charter.get("max_portfolio_var", 0.10)
        projected_var = float(portfolio.get("heat_pct", 0.0)) + sizing.risk_pct
        checks["portfolio_var"] = {
            "ok": projected_var <= max_var + _EPS,
            "value": projected_var,
            "threshold": max_var,
        }

        # Sector concentration: existing exposure + this position <= cap.
        sector = portfolio.get("sector")
        if sector:
            max_sector = charter.get("max_sector_pct", 0.30)
            projected_sector = (
                portfolio.get("sector_exposure", {}).get(sector, 0.0) + sizing.position_pct
            )
            checks["sector_concentration"] = {
                "ok": projected_sector <= max_sector + _EPS,
                "value": projected_sector,
                "threshold": max_sector,
            }

    checks["all_ok"] = all(c["ok"] for c in checks.values() if isinstance(c, dict))
    return checks
