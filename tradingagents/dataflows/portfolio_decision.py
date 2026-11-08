"""Portfolio decision: three separated levels (Phase 4, contract section 4).

The BRK-B report treated ``HOLD``, ``BUY`` and ``Overweight`` as equivalent
actions while its own plan forbade buying at 570.89. This module makes the
separation the contract requires explicit and typed:

1. **Strategic rating** — ``UNDERWEIGHT | NEUTRAL | OVERWEIGHT`` over a
   declared horizon. An opinion.
2. **Investment intent** — ``AVOID | MONITOR | ACCUMULATE_CONDITIONALLY |
   MAINTAIN | REDUCE``. A posture.
3. **Execution action** — ``WAIT | BLOCK | PROPOSE_PAPER_ORDER |
   SUBMIT_PAPER_ORDER``. What the desk may actually do, decided by the
   Execution Gate, never by the rating.

``OVERWEIGHT`` does not imply ``BUY NOW``. Legacy reports keep their 5-tier
labels (``Buy``/``Hold``/...); :func:`map_legacy_rating` converts them to
the strategic vocabulary *explicitly*, carrying the legacy label along so
nothing is silently renamed.
"""

from __future__ import annotations

from dataclasses import dataclass

from tradingagents.dataflows.execution_gate import (
    INVESTMENT_INTENTS,
    STRATEGIC_RATINGS,
    ExecutionAction,
)

# The legacy 5-tier labels the existing system produces (agents.rating).
LEGACY_RATINGS = ("Buy", "Overweight", "Hold", "Underweight", "Sell")

# Legacy -> strategic rating. The mapping is a policy, written here once:
# "Buy" and "Overweight" are both bullish postures, but only at different
# conviction; both map to OVERWEIGHT as the strategic ceiling, with the
# legacy label preserved on the decision.
_LEGACY_TO_STRATEGIC = {
    "Buy": "OVERWEIGHT",
    "Overweight": "OVERWEIGHT",
    "Hold": "NEUTRAL",
    "Underweight": "UNDERWEIGHT",
    "Sell": "UNDERWEIGHT",
}

# Legacy -> investment intent. "Buy" without a conditional plan is not an
# executable instruction, so it maps to ACCUMULATE_CONDITIONALLY: the desk
# may accumulate when triggers and policy allow, never on the label alone.
_LEGACY_TO_INTENT = {
    "Buy": "ACCUMULATE_CONDITIONALLY",
    "Overweight": "ACCUMULATE_CONDITIONALLY",
    "Hold": "MAINTAIN",
    "Underweight": "REDUCE",
    "Sell": "AVOID",
}


@dataclass(frozen=True)
class StrategicDecision:
    """The decision's three levels, separated and typed.

    ``legacy_label`` carries the original 5-tier rating when the decision
    came from a legacy report, so the audit trail shows both what was said
    and what it means now. ``execution_action`` is filled by the Execution
    Gate; this module never invents one from the rating.
    """

    ticker: str
    rating: str                    # strategic: UNDERWEIGHT/NEUTRAL/OVERWEIGHT
    intent: str                    # AVOID/MONITOR/ACCUMULATE_CONDITIONALLY/...
    horizon_months: tuple[int, int] | None = None
    legacy_label: str | None = None
    execution_action: ExecutionAction | None = None
    reason_codes: tuple[str, ...] = ()

    def __post_init__(self):
        if self.rating not in STRATEGIC_RATINGS:
            raise ValueError(
                f"rating {self.rating!r} is not strategic vocabulary "
                f"{sorted(STRATEGIC_RATINGS)}"
            )
        if self.intent not in INVESTMENT_INTENTS:
            raise ValueError(
                f"intent {self.intent!r} is not intent vocabulary "
                f"{sorted(INVESTMENT_INTENTS)}"
            )
        if self.horizon_months is not None:
            lo, hi = self.horizon_months
            if not (0 <= lo <= hi):
                raise ValueError(
                    f"horizon_months {self.horizon_months!r} must satisfy 0 <= lo <= hi"
                )

    @property
    def is_executable_action(self) -> bool:
        """Whether the action vocabulary (not the rating) authorizes a desk step."""
        return self.execution_action in (
            ExecutionAction.PROPOSE_PAPER_ORDER,
            ExecutionAction.SUBMIT_PAPER_ORDER,
        )

    def render(self) -> str:
        """The decision as markdown, with the three levels visibly distinct."""
        horizon = (
            f"{self.horizon_months[0]}-{self.horizon_months[1]} months"
            if self.horizon_months else "not provided"
        )
        legacy = f" (legacy label: {self.legacy_label})" if self.legacy_label else ""
        action = self.execution_action.value if self.execution_action else "not evaluated"
        reasons = ", ".join(self.reason_codes) if self.reason_codes else "none"
        return "\n".join([
            f"**Strategic rating**: {self.rating}{legacy}",
            f"**Investment intent**: {self.intent}",
            f"**Horizon**: {horizon}",
            f"**Execution action**: {action}",
            f"**Reason codes**: {reasons}",
            "",
            "The strategic rating is an opinion over the horizon; the execution "
            "action is what the desk may do now. An OVERWEIGHT rating does not "
            "authorize a market order.",
        ])


def map_legacy_rating(
    legacy: str,
    ticker: str,
    *,
    horizon_months: tuple[int, int] | None = None,
) -> StrategicDecision:
    """Convert a legacy 5-tier rating into the separated decision explicitly.

    The legacy label is preserved on the decision; the mapping itself is the
    policy table above. An unknown label raises: silently mapping an
    unreadable decision would repeat the #1170 mistake of inventing a call
    nobody made.
    """
    key = legacy.strip().capitalize()
    if key not in _LEGACY_TO_STRATEGIC:
        raise ValueError(
            f"legacy rating {legacy!r} is not one of {LEGACY_RATINGS}; "
            f"an unreadable decision must be reviewed, not guessed"
        )
    return StrategicDecision(
        ticker=ticker,
        rating=_LEGACY_TO_STRATEGIC[key],
        intent=_LEGACY_TO_INTENT[key],
        horizon_months=horizon_months,
        legacy_label=key,
    )


def with_execution_action(
    decision: StrategicDecision,
    action: ExecutionAction,
    reason_codes: tuple[str, ...] = (),
) -> StrategicDecision:
    """Attach the Execution Gate's action to a strategic decision.

    The only way ``execution_action`` is filled: the gate decides, this
    records. The rating is untouched — an OVERWEIGHT decision may carry a
    WAIT action, and that coexistence is the point (contract §4).
    """
    return StrategicDecision(
        ticker=decision.ticker,
        rating=decision.rating,
        intent=decision.intent,
        horizon_months=decision.horizon_months,
        legacy_label=decision.legacy_label,
        execution_action=action,
        reason_codes=reason_codes,
    )
