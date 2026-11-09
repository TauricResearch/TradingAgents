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
    EXPOSURE_CAP_EXCEEDED = "EXPOSURE_CAP_EXCEEDED"
    EXPOSURE_CAP_INVALID = "EXPOSURE_CAP_INVALID"
    DIRECTION_INVALID = "DIRECTION_INVALID"


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


def validate_stop_side(
    entry: float,
    stop: float,
    direction: str = "LONG",
) -> object:
    """Whether the stop sits on the protective side of the entry.

    A LONG's stop is below the entry; a SHORT's is above. A stop on the
    wrong side protects nothing — it is an error, not a wide stop. Returns
    a :class:`ValidationResult` from the shared validator vocabulary so the
    caller can collect the issue with the rest of the data-quality checks.
    """
    from tradingagents.dataflows.validator import ValidationResult

    result = ValidationResult()
    if direction not in ("LONG", "SHORT"):
        result.add("STOP_DIRECTION_UNKNOWN", "error",
                   f"direction {direction!r} is not LONG or SHORT")
        return result
    if not (math.isfinite(entry) and math.isfinite(stop)) \
            or entry <= 0 or stop <= 0:
        result.add("STOP_LEVELS_INVALID", "error",
                   f"entry {entry} / stop {stop} must be positive finite prices")
        return result
    if direction == "LONG" and stop >= entry:
        result.add(
            "STOP_WRONG_SIDE", "error",
            f"a LONG stop ({stop}) must sit below the entry ({entry}); at or "
            "above it protects nothing",
            field="stop", expected="< entry", actual=stop,
        )
    if direction == "SHORT" and stop <= entry:
        result.add(
            "STOP_WRONG_SIDE", "error",
            f"a SHORT stop ({stop}) must sit above the entry ({entry}); at or "
            "below it protects nothing",
            field="stop", expected="> entry", actual=stop,
        )
    return result


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


@dataclass(frozen=True)
class ExposureSizingResult:
    """Sizing subject to the stop-budget AND the per-symbol exposure cap.

    ``binding_constraint`` records which limit actually bound the size
    (``RISK_BUDGET`` or ``EXPOSURE_CAP``): the cap binding is the policy
    working as intended, not a failure. ``exposure_cap_applied`` is True
    whenever a cap was in force, so the audit can show the notional was
    capped, not merely affordable.
    """

    qty: int
    notional: float
    planned_risk: float
    binding_constraint: str | None    # "RISK_BUDGET" | "EXPOSURE_CAP" | None
    reasons: tuple[RiskReason, ...] = field(default_factory=tuple)
    exposure_cap_applied: bool = False

    @property
    def blocked(self) -> bool:
        return self.qty <= 0 or bool(self.reasons)


def size_with_exposure_cap(
    *,
    entry: float,
    stop: float,
    atr: float,
    risk_budget: float | None,
    equity: float | None,
    max_symbol_exposure: float | None,
    direction: str = "LONG",
    cash: float | None = None,
    existing_notional: float = 0.0,
    gap_atr: float = 0.0,
    slippage_pct: float = 0.0,
    min_atr: float = DEFAULT_MIN_ENTRY_STOP_ATR,
) -> ExposureSizingResult:
    """Size a tranche under BOTH the stop-distance budget and the exposure cap.

    Sizing to the stop-distance alone can produce an enormous position: a
    100,000 USD portfolio with a 1,000 USD risk budget, entry 560 and stop
    552.07 gives floor(1000 / 7.93) = 126 shares — about 70,600 USD of
    notional, 70% of the portfolio in one ticker. The per-symbol exposure
    cap is the binding constraint that must also apply: with a 5% cap the
    same plan is capped at floor(5000 / 560) = 8 shares (4,480 USD).

    The engine applies the *most binding* constraint and reports which one
    bound the size. All limits are caller-configured — nothing is
    hardcoded per ticker. Without portfolio context (no equity) no size is
    invented: the result is qty 0 with ``PORTFOLIO_CONTEXT_MISSING``.
    """
    reasons: list[RiskReason] = []

    # Direction sanity: the stop must protect the position's side.
    if direction not in ("LONG", "SHORT"):
        return ExposureSizingResult(0, 0.0, 0.0, None,
                                    (RiskReason.DIRECTION_INVALID,))
    if not (math.isfinite(entry) and entry > 0) \
            or not (math.isfinite(stop) and stop > 0):
        return ExposureSizingResult(0, 0.0, 0.0, None,
                                    (RiskReason.INVALID_ENTRY,))
    if direction == "LONG" and stop >= entry:
        return ExposureSizingResult(0, 0.0, 0.0, None,
                                    (RiskReason.INVALID_STOP,))
    if direction == "SHORT" and stop <= entry:
        return ExposureSizingResult(0, 0.0, 0.0, None,
                                    (RiskReason.INVALID_STOP,))
    if risk_budget is None or not math.isfinite(risk_budget) or risk_budget <= 0:
        return ExposureSizingResult(0, 0.0, 0.0, None,
                                    (RiskReason.RISK_BUDGET_MISSING,))

    risk_per_share = abs(entry - stop)
    stressed_extra = max(0.0, gap_atr) * atr + max(0.0, slippage_pct) * entry
    stressed_risk = risk_per_share + stressed_extra

    qty_risk = int(math.floor(risk_budget / stressed_risk)) \
        if stressed_risk > 0 else 0

    # Exposure cap: notional at entry (plus what is already held) must stay
    # within the configured fraction of equity.
    qty_exposure = None
    cap_applied = False
    if max_symbol_exposure is not None:
        if equity is None or not math.isfinite(equity) or equity <= 0:
            return ExposureSizingResult(
                0, 0.0, 0.0, None, (RiskReason.PORTFOLIO_CONTEXT_MISSING,))
        if not (0 < max_symbol_exposure <= 1):
            return ExposureSizingResult(
                0, 0.0, 0.0, None, (RiskReason.EXPOSURE_CAP_INVALID,))
        cap_applied = True
        max_notional = equity * max_symbol_exposure - max(0.0, existing_notional)
        qty_exposure = int(math.floor(max_notional / entry)) \
            if max_notional > 0 else 0

    if qty_exposure is not None:
        qty = min(qty_risk, qty_exposure)
        binding = "EXPOSURE_CAP" if qty_exposure < qty_risk else "RISK_BUDGET"
    else:
        qty = qty_risk
        binding = "RISK_BUDGET"

    if qty <= 0:
        reasons.append(RiskReason.NON_POSITIVE_SIZE)
        return ExposureSizingResult(0, 0.0, 0.0, None, tuple(reasons),
                                    cap_applied)

    notional = qty * entry
    if cash is not None and (not math.isfinite(cash) or cash < 0 or notional > cash):
        reasons.append(RiskReason.CASH_EXCEEDED)
        return ExposureSizingResult(0, 0.0, 0.0, None, tuple(reasons),
                                    cap_applied)

    planned_risk = qty * stressed_risk
    return ExposureSizingResult(qty, notional, planned_risk, binding,
                                tuple(reasons), cap_applied)


# ---------------------------------------------------------------------------
# Multi-tranche risk (P0-C): per-leg risk and aggregate exposure
# ---------------------------------------------------------------------------

# A leg whose stop sits closer than this many ATRs is flagged for policy:
# the distance is too tight to survive normal noise. A threshold, not a
# universal law — the caller may override it per strategy.
DEFAULT_MIN_TRANCHE_ATR = 0.25


@dataclass(frozen=True)
class TrancheRisk:
    """One tranche's risk, priced on its own entry and stop.

    ``atr_multiple`` is the stop distance in ATR units — the number the
    policy threshold judges. ``valid`` is False when the stop sits on the
    wrong side for the direction; ``reason_code`` carries why.
    """

    entry: float
    stop: float
    atr: float
    direction: str
    risk_per_share: float
    atr_multiple: float
    valid: bool
    reason_code: str

    @property
    def blocked(self) -> bool:
        return not self.valid

    def summary(self) -> dict:
        return {
            "entry": self.entry,
            "stop": self.stop,
            "atr": self.atr,
            "direction": self.direction,
            "risk_per_share": self.risk_per_share,
            "atr_multiple": self.atr_multiple,
            "valid": self.valid,
            "reason_code": self.reason_code,
        }


def tranche_risk(
    entry: float | None,
    stop: float | None,
    atr: float | None,
    *,
    direction: str = "LONG",
    min_atr: float = DEFAULT_MIN_TRANCHE_ATR,
) -> TrancheRisk:
    """Price one tranche's risk on its own entry and stop.

    A stop-distance risk is *theoretical*: the worst case at the stop, not a
    guaranteed fill (gap and slippage widen it — see ``stress_exit``). Each
    leg keeps its own numbers: a second tranche entered lower must never
    inherit the first leg's risk per share.
    """
    if direction not in ("LONG", "SHORT"):
        return TrancheRisk(entry or 0.0, stop or 0.0, atr or 0.0, direction,
                           0.0, 0.0, False, RiskReason.DIRECTION_INVALID.value)
    if not (math.isfinite(entry or 0) and entry > 0) \
            or not (math.isfinite(stop or 0) and stop > 0):
        return TrancheRisk(entry or 0.0, stop or 0.0, atr or 0.0, direction,
                           0.0, 0.0, False, RiskReason.INVALID_ENTRY.value)
    wrong_side = (direction == "LONG" and stop >= entry) \
        or (direction == "SHORT" and stop <= entry)
    if wrong_side:
        return TrancheRisk(entry, stop, atr or 0.0, direction, 0.0, 0.0,
                           False, "INVALID_STOP_SIDE")

    distance = abs(entry - stop)
    multiple = distance / atr if math.isfinite(atr or 0) and atr > 0 else 0.0
    if multiple and multiple < min_atr:
        # Valid geometry, but too tight to be a sensible protective stop.
        return TrancheRisk(entry, stop, atr, direction, distance, multiple,
                           True, "STOP_TOO_TIGHT_FOR_POLICY")
    return TrancheRisk(entry, stop, atr or 0.0, direction, distance, multiple,
                       True, "OK")


@dataclass(frozen=True)
class TrancheOutcome:
    """One tranche's sizing within an aggregate plan."""

    entry: float
    stop: float
    qty: int
    notional: float
    risk: float
    risk_per_share: float
    atr_multiple: float
    reason_code: str | None = None    # None when the tranche is fine

    @property
    def blocked(self) -> bool:
        return self.qty <= 0 and self.reason_code is not None

    def summary(self) -> dict:
        return {
            "entry": self.entry,
            "stop": self.stop,
            "qty": self.qty,
            "notional": self.notional,
            "risk": self.risk,
            "risk_per_share": self.risk_per_share,
            "atr_multiple": self.atr_multiple,
            "reason_code": self.reason_code,
        }


@dataclass(frozen=True)
class AggregateRiskResult:
    """Aggregate sizing over all tranches plus existing exposure."""

    tranches: list[TrancheOutcome] = field(default_factory=list)
    total_qty: int = 0
    total_notional: float = 0.0
    total_risk: float = 0.0
    blocked: bool = False
    reasons: tuple[str, ...] = field(default_factory=tuple)

    def summary(self) -> dict:
        return {
            "tranches": [t.summary() for t in self.tranches],
            "total_qty": self.total_qty,
            "total_notional": self.total_notional,
            "total_risk": self.total_risk,
            "blocked": self.blocked,
            "reasons": list(self.reasons),
        }


def _as_tranche(leg) -> dict:
    """Accept a TranchePlan, a mapping, or an object with the same fields."""
    if isinstance(leg, dict):
        return leg
    return {
        "entry": getattr(leg, "entry", None),
        "stop": getattr(leg, "stop", None),
        "atr": getattr(leg, "atr", None),
        "direction": getattr(leg, "direction", "LONG"),
        "strategy_id": getattr(leg, "strategy_id", None),
        "trigger": getattr(leg, "trigger", None),
    }


def aggregate_tranche_risk(
    tranches: list,
    *,
    risk_budget: float | None,
    equity: float | None,
    max_symbol_exposure: float | None,
    existing_notional: float = 0.0,
    existing_risk: float = 0.0,
    min_atr: float = DEFAULT_MIN_TRANCHE_ATR,
) -> AggregateRiskResult:
    """Size every tranche on its own stop and enforce the AGGREGATE budgets.

    Each leg is priced from its own entry and stop — a second leg entered
    lower does not inherit the first's risk. Then, simultaneously:

    - total risk (all legs + the existing open risk) stays within
      ``risk_budget``;
    - total notional (all legs + the existing notional) stays within
      ``max_symbol_exposure`` * equity.

    A leg that cannot be sized because a budget is exhausted is skipped, not
    an error: the *alternative* scenarios simply do not both fire. Only
    invalid geometry (wrong-side stop, invalid price) blocks the plan.

    Without portfolio context (no equity, no budget) nothing is invented:
    the result is blocked with ``PORTFOLIO_CONTEXT_MISSING``.
    """
    reasons: list[str] = []
    if risk_budget is None or not math.isfinite(risk_budget) or risk_budget <= 0:
        return AggregateRiskResult(reasons=(RiskReason.RISK_BUDGET_MISSING.value,),
                                   blocked=True)
    if equity is None or not math.isfinite(equity) or equity <= 0:
        return AggregateRiskResult(
            reasons=(RiskReason.PORTFOLIO_CONTEXT_MISSING.value,), blocked=True)
    if max_symbol_exposure is None or not (0 < max_symbol_exposure <= 1):
        return AggregateRiskResult(
            reasons=(RiskReason.EXPOSURE_CAP_INVALID.value,), blocked=True)

    outcomes: list[TrancheOutcome] = []
    total_qty = 0
    total_notional = max(0.0, existing_notional)
    total_risk = max(0.0, existing_risk)
    remaining_risk = risk_budget - max(0.0, existing_risk)
    remaining_notional = equity * max_symbol_exposure - max(0.0, existing_notional)

    for leg in tranches:
        spec = _as_tranche(leg)
        priced = tranche_risk(
            spec.get("entry"), spec.get("stop"), spec.get("atr"),
            direction=spec.get("direction") or "LONG", min_atr=min_atr,
        )
        if priced.reason_code == "INVALID_STOP_SIDE":
            outcomes.append(TrancheOutcome(
                priced.entry, priced.stop, 0, 0.0, 0.0, 0.0, 0.0,
                "INVALID_STOP_SIDE"))
            reasons.append("INVALID_STOP_SIDE")
            continue
        if priced.reason_code in ("INVALID_ENTRY", "DIRECTION_INVALID"):
            outcomes.append(TrancheOutcome(
                priced.entry, priced.stop, 0, 0.0, 0.0, 0.0, 0.0,
                priced.reason_code))
            reasons.append(priced.reason_code)
            continue

        risk_per_share = priced.risk_per_share
        qty_risk = int(math.floor(remaining_risk / risk_per_share)) \
            if risk_per_share > 0 and remaining_risk > 0 else 0
        qty_exposure = int(math.floor(remaining_notional / priced.entry)) \
            if remaining_notional > 0 else 0
        qty = min(qty_risk, qty_exposure)

        if qty <= 0:
            # A budget-exhausted leg is simply not taken; the plan is not
            # invalid because two alternatives cannot both fire.
            outcomes.append(TrancheOutcome(
                priced.entry, priced.stop, 0, 0.0, 0.0, risk_per_share,
                priced.atr_multiple, None))
            continue

        notional = qty * priced.entry
        risk = qty * risk_per_share
        outcomes.append(TrancheOutcome(
            priced.entry, priced.stop, qty, notional, risk, risk_per_share,
            priced.atr_multiple, None))
        total_qty += qty
        total_notional += notional
        total_risk += risk
        remaining_risk -= risk
        remaining_notional -= notional

    return AggregateRiskResult(
        tranches=outcomes,
        total_qty=total_qty,
        total_notional=total_notional,
        total_risk=total_risk,
        blocked=bool(reasons),
        reasons=tuple(dict.fromkeys(reasons)),
    )


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


@dataclass(frozen=True)
class QuantitySensitivity:
    """How a quantity changes when one sizing input changes (§2 case E).

    The 19:24 report asserted that a quantity falls "40-50%" when ATR rises
    from 6.36 to 9.524, with no calculation behind it. The engine can answer
    exactly: the size is inversely proportional to the stop distance, so with
    a fixed monetary risk and the same ATR multiple the quantity scales by
    ``atr_old / atr_new`` — a 33.22% reduction here.

    This is deliberately a *reported consequence*, not a new sizing rule: the
    quantity itself still comes from ``size_with_exposure_cap``.
    """

    previous_qty: int
    new_qty: int
    reduction_pct: float | None
    ratio: float | None

    def summary(self) -> dict:
        return {
            "previous_qty": self.previous_qty,
            "new_qty": self.new_qty,
            "quantity_ratio": self.ratio,
            "reduction_pct": self.reduction_pct,
            "formula_id": "qty_scales_inversely_with_stop_distance",
        }


def quantity_sensitivity_to_atr(
    previous_atr: float,
    new_atr: float,
    *,
    previous_qty: int,
) -> QuantitySensitivity:
    """The quantity implied by a changed ATR at constant monetary risk.

    ``new_qty = previous_qty * (previous_atr / new_atr)`` — because the stop
    distance in currency units scales with ATR, and a fixed risk budget
    divided by a wider per-share risk buys proportionally fewer shares.

    A non-positive ATR yields ``None`` rather than an infinite ratio: the
    question is then not answerable, and inventing a number is what the
    report did.
    """
    if (previous_atr is None or new_atr is None
            or not math.isfinite(previous_atr) or not math.isfinite(new_atr)
            or previous_atr <= 0 or new_atr <= 0 or previous_qty <= 0):
        return QuantitySensitivity(previous_qty, 0, None, None)
    ratio = previous_atr / new_atr
    new_qty = int(math.floor(previous_qty * ratio))
    reduction = (1.0 - ratio) * 100.0
    return QuantitySensitivity(
        previous_qty=previous_qty,
        new_qty=new_qty,
        reduction_pct=round(reduction, 2),
        ratio=round(ratio, 6),
    )
