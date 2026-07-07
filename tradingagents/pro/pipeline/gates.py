"""Deterministic gates: code decides pass/fail, LLMs never override them."""

from __future__ import annotations

from dataclasses import dataclass, field

from tradingagents.contracts import MetricReading, ProConfig, TradeAction


@dataclass(frozen=True)
class GateResult:
    passed: bool
    checks: dict[str, bool] = field(default_factory=dict)
    reasons: tuple[str, ...] = ()


def risk_gate(
    risk_metrics: dict[str, MetricReading],
    config: ProConfig,
    proposed_action: TradeAction | None = None,
) -> GateResult:
    """Hard risk checks before any qualitative judgment happens.

    - VaR(95) per bar must not exceed the configured max daily loss.
    - CVaR must not exceed twice the daily-loss limit (tail sanity).
    - A directional trade needs engine levels (entry/stop) to exist —
      without them Constraint 2 leaves nothing valid to execute against.
    """
    checks: dict[str, bool] = {}
    reasons: list[str] = []

    var = risk_metrics.get("VAR_95")
    daily_limit = config.risk.max_daily_loss_pct / 100.0
    if var is None:
        checks["var_available"] = False
        reasons.append("VAR_95 unavailable (insufficient return history)")
    else:
        checks["var_available"] = True
        checks["var_within_limit"] = var.value <= daily_limit
        if not checks["var_within_limit"]:
            reasons.append(
                f"VaR95 {var.value:.4f} exceeds max daily loss {daily_limit:.4f}"
            )

    cvar = risk_metrics.get("CVAR_95")
    if cvar is not None:
        checks["cvar_within_limit"] = cvar.value <= 2 * daily_limit
        if not checks["cvar_within_limit"]:
            reasons.append(
                f"CVaR95 {cvar.value:.4f} exceeds 2x max daily loss {2 * daily_limit:.4f}"
            )

    if proposed_action in (TradeAction.BUY, TradeAction.SELL):
        has_levels = "ATR_STOP" in risk_metrics and "ENTRY_REF_PRICE" in risk_metrics
        checks["levels_available"] = has_levels
        if not has_levels:
            reasons.append("no engine-computed entry/stop levels (ATR missing)")

    passed = all(checks.values()) if checks else False
    if not checks:
        reasons.append("risk gate had nothing to check; failing closed")
    return GateResult(passed=passed, checks=checks, reasons=tuple(reasons))
