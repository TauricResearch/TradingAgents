"""Structured execution verdict (P0-D).

The decision chain ends in one machine-readable record: what was decided,
what the desk may do now, and — when nothing may happen — exactly why. No
LLM writes this record: it is assembled from the typed verdicts of the
gates, and ``execution_approved`` is a boolean derived from them, never a
field an agent can set.

The shape follows the contract's example (instrument, rating, action,
approval, authorized orders, blocking reasons) extended with the audit
identity the observability section requires: ``run_id``, ``checked_at``,
``policy_version``. ``authorized_orders`` is empty unless the verdict is
an approved proposal — an unauthorized verdict carrying an order would be
a contradiction, and the constructor refuses to build one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

# Actions the desk can take. Storage and reporting only: nothing here
# submits an order.
WAIT = "WAIT"
BLOCK = "BLOCK"
PROPOSE_PAPER_ORDER = "PROPOSE_PAPER_ORDER"
SUBMIT_PAPER_ORDER = "SUBMIT_PAPER_ORDER"

# The only action that may carry authorized orders.
_ORDER_BEARING = frozenset({PROPOSE_PAPER_ORDER, SUBMIT_PAPER_ORDER})


def _utc_now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class ExecutionVerdictError(ValueError):
    """A verdict was built with contradictory fields."""


@dataclass(frozen=True)
class ExecutionVerdict:
    """The run's execution verdict, JSON-ready and auditable."""

    run_id: str
    instrument: str
    analysis_as_of: str
    strategic_rating: str
    execution_action: str
    blocking_reasons: tuple[str, ...]
    policy_version: str
    authorized_orders: tuple[dict, ...] = ()
    checked_at: str = field(default_factory=_utc_now_iso)

    def __post_init__(self):
        if self.execution_action not in (WAIT, BLOCK, PROPOSE_PAPER_ORDER,
                                        SUBMIT_PAPER_ORDER):
            raise ExecutionVerdictError(
                f"action {self.execution_action!r} is not one of "
                f"{WAIT}, {BLOCK}, {PROPOSE_PAPER_ORDER}, {SUBMIT_PAPER_ORDER}"
            )
        # An order-bearing action must not also carry blockers, and a
        # non-order action must not carry orders: both are contradictions
        # that would let an unvalidated order look authorized.
        if self.execution_action in _ORDER_BEARING and self.blocking_reasons:
            raise ExecutionVerdictError(
                f"{self.execution_action} cannot carry blocking reasons "
                f"{list(self.blocking_reasons)}"
            )
        if self.execution_action not in _ORDER_BEARING and self.authorized_orders:
            raise ExecutionVerdictError(
                f"{self.execution_action} cannot authorize orders; "
                "a blocked or waiting verdict creates none"
            )

    @property
    def execution_approved(self) -> bool:
        """True only for an order-bearing action with nothing blocking it."""
        return (self.execution_action in _ORDER_BEARING
                and not self.blocking_reasons)

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "instrument": self.instrument,
            "analysis_as_of": self.analysis_as_of,
            "strategic_rating": self.strategic_rating,
            "execution_action": self.execution_action,
            "execution_approved": self.execution_approved,
            "authorized_orders": [dict(o) for o in self.authorized_orders],
            "blocking_reasons": list(self.blocking_reasons),
            "checked_at": self.checked_at,
            "policy_version": self.policy_version,
        }

    def summary(self) -> str:
        """The few-second read for a human report."""
        if self.execution_approved:
            return (
                f"{self.instrument}: {self.strategic_rating} -> "
                f"{self.execution_action}, {len(self.authorized_orders)} "
                "authorized paper order(s)"
            )
        reasons = ", ".join(self.blocking_reasons) or "none"
        return (
            f"{self.instrument}: {self.strategic_rating} -> "
            f"{self.execution_action} (approved: false; reasons: {reasons})"
        )


def build_verdict(
    *,
    run_id: str,
    instrument: str,
    analysis_as_of: str,
    strategic_rating: str,
    execution_action: str,
    blocking_reasons,
    policy_version: str,
    authorized_orders=(),
) -> ExecutionVerdict:
    """Assemble the verdict from the gates' typed results.

    The caller passes what the gates decided; this function enforces the
    invariants (no orders with blockers, no approval without an
    order-bearing action) rather than trusting the caller's intent.
    """
    return ExecutionVerdict(
        run_id=run_id,
        instrument=instrument,
        analysis_as_of=analysis_as_of,
        strategic_rating=strategic_rating,
        execution_action=execution_action,
        blocking_reasons=tuple(blocking_reasons or ()),
        policy_version=policy_version,
        authorized_orders=tuple(dict(o) for o in (authorized_orders or ())),
    )


# Reasons that describe a passing check rather than a block. They are not
# blocking reasons, so they never belong in ``blocking_reasons``.
_NON_BLOCKING_REASONS = frozenset({
    "OK", "NO_TRIGGER", "ENTRY_TRIGGER_NOT_MET", "MARKET_CLOSED",
})


def verdict_from_gate(
    *,
    run_id: str,
    instrument: str,
    analysis_as_of: str,
    strategic_rating: str,
    decision,
    policy_version: str,
    blocking_reasons=(),
    authorized_orders=(),
) -> ExecutionVerdict:
    """Build a verdict from an :class:`ExecutionGate` decision.

    The gate's action becomes the verdict's action; a gate that did not
    propose cannot authorize anything, whatever the caller passed. Passing
    reasons (``OK``, an unmet trigger, a closed market) are filtered out:
    they describe a valid plan, not a block.
    """
    action = getattr(decision, "action", None)
    action_value = str(getattr(action, "value", action) or BLOCK)
    raw_reasons = tuple(blocking_reasons or ()) or tuple(
        str(getattr(r, "value", r)) for r in getattr(decision, "reasons", ())
    )
    # A waiting or blocked decision keeps its real reasons; passing codes
    # are dropped in either case so an approval never looks blocked.
    reasons = tuple(r for r in raw_reasons if r not in _NON_BLOCKING_REASONS)
    orders = authorized_orders if action_value in _ORDER_BEARING else ()
    return build_verdict(
        run_id=run_id,
        instrument=instrument,
        analysis_as_of=analysis_as_of,
        strategic_rating=strategic_rating,
        execution_action=action_value,
        blocking_reasons=reasons,
        policy_version=policy_version,
        authorized_orders=orders,
    )
