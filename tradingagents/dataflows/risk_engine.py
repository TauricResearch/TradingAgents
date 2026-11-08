"""Deterministic risk engine (Phase 2, contract section 5).

Position sizing, stop validation and gap/slippage stress are computed in
code, never in LLM prose. Every function is pure and returns a typed result
the Execution Gate (Phase 3) can read: a plan either passes with its numbers
or fails with machine-readable reason codes. An LLM cannot approve itself a
derogation; there is no path from a rating to a size here.

Key semantics from the contract:

- ``risk_per_share`` uses the *stressed* exit price, not the stop: a stop is
  not a guaranteed execution price. Gap, slippage and spread widen the loss.
- ``qty = floor(risk_budget / stressed_risk_per_share)`` with hard guards:
  never negative, never infinite, never without a known budget.
- The entry-to-stop buffer must clear a minimum in ATR units (parametric,
  default 0.5). Below it the plan is BLOCKED; no self-derogation.
- ``max_portfolio_loss_fraction`` stays ``None`` when the portfolio is
  unknown: a loss quoted against "the standard allocation" is not a loss
  against the whole equity, and this engine never converts one into the
  other without a real base.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import StrEnum

# The contract's parametric minimum entry-to-stop buffer, in ATR units.
# A threshold, not a universal law: callers may configure it, and a blocked
# plan may only proceed through an explicitly approved exception recorded
# outside this module.
DEFAULT_MIN_ENTRY_STOP_ATR = 0.5

# Default stress multipliers applied to the stop distance. Conservative
# starting points: a gap of half an ATR and a slippage/spread allowance of
# 0.05% of the entry price. Callers with real microstructure data override.
DEFAULT_GAP_ATR = 0.5
DEFAULT_SLIPPAGE_PCT = 0.0005


class RiskVerdict(StrEnum):
    """The plan-level verdict the Execution Gate reads."""

    VALID = "VALID"
    BLOCK = "BLOCK"


class RiskReason(StrEnum):
    """Machine-readable reasons a plan failed or was degraded."""

    OK = "OK"
    STOP_BUFFER_TOO_TIGHT = "STOP_BUFFER_TOO_TIGHT"
    RISK_BUDGET_MISSING = "RISK_BUDGET_MISSING"
    RISK_BUDGET_EXCEEDED = "RISK_BUDGET_EXCEEDED"
    INVALID_STOP = "INVALID_STOP"
    INVALID_ENTRY = "INVALID_ENTRY"
    INVALID_ATR = "INVALID_ATR"
    NON_POSITIVE_SIZE = "NON_POSITIVE_SIZE"
    CASH_EXCEEDED = "CASH_EXCEEDED"
    PORTFOLIO_CONTEXT_MISSING = "PORTFOLIO_CONTEXT_MISSING"


@dataclass(frozen=True)
class StopValidation:
    """Whether an entry/stop pair clears the minimum ATR buffer."""

    passed: bool
    entry: float
    stop: float
    atr: float
    distance: float
    atr_multiple: float
    min_atr: float
    reason: RiskReason

    @property
    def blocked(self) -> bool:
        return not self.passed


def validate_stop(
    entry: float,
    stop: float,
    atr: float,
    *,
    min_atr: float = DEFAULT_MIN_ENTRY_STOP_ATR,
) -> StopValidation:
    """Validate an entry/stop pair against the volatility buffer.

    For a long plan the stop must sit below the entry by at least
    ``min_atr`` * ATR. Invalid inputs (non-positive ATR, stop at or above
    entry) fail with their own reason codes rather than raising, so a bad
    plan is a verdict, not an exception.
    """
    if not math.isfinite(entry) or entry <= 0:
        return StopValidation(False, entry, stop, atr, 0.0, 0.0, min_atr,
                              RiskReason.INVALID_ENTRY)
    if not math.isfinite(stop) or stop <= 0:
        return StopValidation(False, entry, stop, atr, 0.0, 0.0, min_atr,
                              RiskReason.INVALID_STOP)
    if not math.isfinite(atr) or atr <= 0:
        return StopValidation(False, entry, stop, atr, 0.0, 0.0, min_atr,
                              RiskReason.INVALID_ATR)
    distance = entry - stop
    if distance <= 0:
        # A stop at or above the entry protects nothing on a long plan.
        return StopValidation(False, entry, stop, atr, distance, 0.0, min_atr,
                              RiskReason.INVALID_STOP)
    atr_multiple = distance / atr
    if atr_multiple < min_atr:
        return StopValidation(False, entry, stop, atr, distance, atr_multiple,
                              min_atr, RiskReason.STOP_BUFFER_TOO_TIGHT)
    return StopValidation(True, entry, stop, atr, distance, atr_multiple,
                          min_atr, RiskReason.OK)


@dataclass(frozen=True)
class StressedExit:
    """The exit price a stop can actually be expected to fill at."""

    stop: float
    gap_atr: float
    slippage_pct: float
    stressed_exit: float
    extra_loss_per_share: float

    @property
    def is_guaranteed(self) -> bool:
        """Always False: a stop is never a guaranteed execution price."""
        return False


def stress_exit(
    entry: float,
    stop: float,
    atr: float,
    *,
    gap_atr: float = DEFAULT_GAP_ATR,
    slippage_pct: float = DEFAULT_SLIPPAGE_PCT,
) -> StressedExit:
    """Stress the stop for gap and slippage (contract: stops are not guarantees).

    The stressed exit is the stop less a gap allowance (``gap_atr`` * ATR)
    and a slippage/spread allowance (``slippage_pct`` of entry). The extra
    loss per share over the nominal stop distance is what sizing must use.
    """
    gap = max(0.0, gap_atr) * atr
    slip = max(0.0, slippage_pct) * entry
    stressed = stop - gap - slip
    return StressedExit(
        stop=stop,
        gap_atr=gap_atr,
        slippage_pct=slippage_pct,
        stressed_exit=stressed,
        extra_loss_per_share=max(0.0, stop - stressed),
    )


@dataclass(frozen=True)
class SizingResult:
    """The deterministic size a risk budget buys, at stressed risk."""

    qty: int
    risk_per_share: float          # nominal: entry - stop
    stressed_risk_per_share: float  # entry - stressed exit
    risk_budget: float
    planned_risk: float            # qty * stressed_risk_per_share
    reasons: tuple[RiskReason, ...] = field(default_factory=tuple)

    @property
    def is_sizable(self) -> bool:
        return self.qty > 0 and not self.reasons


def size_position(
    entry: float,
    stop: float,
    atr: float,
    risk_budget: float | None,
    *,
    cash: float | None = None,
    price_for_cash: float | None = None,
    min_atr: float = DEFAULT_MIN_ENTRY_STOP_ATR,
    gap_atr: float = DEFAULT_GAP_ATR,
    slippage_pct: float = DEFAULT_SLIPPAGE_PCT,
) -> SizingResult:
    """Size a long plan from a risk budget, stressed for gap and slippage.

    ``qty = floor(risk_budget / stressed_risk_per_share)``. A missing budget
    yields qty 0 with ``RISK_BUDGET_MISSING`` — the contract forbids sizing
    without one. When ``cash`` is given, the notional at ``price_for_cash``
    (default: entry) must fit it, else ``CASH_EXCEEDED`` and qty 0.
    """
    reasons: list[RiskReason] = []
    stop_check = validate_stop(entry, stop, atr, min_atr=min_atr)
    if stop_check.blocked:
        # The stop verdict's reason leads; sizing is moot without a valid stop.
        return SizingResult(0, 0.0, 0.0, risk_budget or 0.0, 0.0,
                            (stop_check.reason,))

    if risk_budget is None or not math.isfinite(risk_budget) or risk_budget <= 0:
        return SizingResult(0, 0.0, 0.0, risk_budget or 0.0, 0.0,
                            (RiskReason.RISK_BUDGET_MISSING,))

    stressed = stress_exit(entry, stop, atr, gap_atr=gap_atr,
                           slippage_pct=slippage_pct)
    stressed_risk = entry - stressed.stressed_exit
    if stressed_risk <= 0:
        return SizingResult(0, entry - stop, stressed_risk, risk_budget, 0.0,
                            (RiskReason.INVALID_STOP,))

    qty = int(math.floor(risk_budget / stressed_risk))
    if qty <= 0:
        reasons.append(RiskReason.NON_POSITIVE_SIZE)
        return SizingResult(0, entry - stop, stressed_risk, risk_budget, 0.0,
                            tuple(reasons))

    planned_risk = qty * stressed_risk
    if cash is not None:
        price = price_for_cash if price_for_cash is not None else entry
        if not math.isfinite(cash) or cash < 0 or qty * price > cash:
            reasons.append(RiskReason.CASH_EXCEEDED)
            return SizingResult(0, entry - stop, stressed_risk, risk_budget,
                                0.0, tuple(reasons))

    return SizingResult(qty, entry - stop, stressed_risk, risk_budget,
                        planned_risk, tuple(reasons))


@dataclass(frozen=True)
class PortfolioRisk:
    """Portfolio-level risk read for the Execution Gate."""

    equity_known: bool
    equity: float | None
    max_portfolio_loss_fraction: float | None
    planned_risk: float | None
    planned_risk_pct_equity: float | None
    reasons: tuple[RiskReason, ...]

    @property
    def blocked(self) -> bool:
        """True when the plan may not proceed: no portfolio context, or the
        planned loss exceeds the portfolio's maximum-loss budget."""
        return bool(self.reasons) and self.reasons != (RiskReason.OK,)


def portfolio_risk_check(
    planned_risk: float | None,
    equity: float | None,
    max_loss_fraction: float | None = None,
) -> PortfolioRisk:
    """Check planned risk against a known portfolio, or refuse without one.

    With no equity the fraction stays ``None`` and the check blocks with
    ``PORTFOLIO_CONTEXT_MISSING``: a "2.28% of the standard allocation" is
    not convertible to a fraction of total wealth without the real base
    (contract §5). With equity known, the planned fraction is computed and,
    when a ``max_loss_fraction`` limit is given, exceeded budget blocks.
    """
    if equity is None or not math.isfinite(equity) or equity <= 0:
        return PortfolioRisk(
            equity_known=False, equity=None,
            max_portfolio_loss_fraction=None, planned_risk=None,
            planned_risk_pct_equity=None,
            reasons=(RiskReason.PORTFOLIO_CONTEXT_MISSING,),
        )
    if planned_risk is None or not math.isfinite(planned_risk) or planned_risk < 0:
        return PortfolioRisk(
            equity_known=True, equity=equity,
            max_portfolio_loss_fraction=max_loss_fraction, planned_risk=None,
            planned_risk_pct_equity=None,
            reasons=(RiskReason.RISK_BUDGET_MISSING,),
        )
    fraction = planned_risk / equity
    reasons: list[RiskReason] = []
    if max_loss_fraction is not None and math.isfinite(max_loss_fraction) \
            and fraction > max_loss_fraction:
        reasons.append(RiskReason.RISK_BUDGET_EXCEEDED)
    return PortfolioRisk(
        equity_known=True, equity=equity,
        max_portfolio_loss_fraction=max_loss_fraction,
        planned_risk=planned_risk, planned_risk_pct_equity=fraction,
        reasons=tuple(reasons) or (RiskReason.OK,),
    )
