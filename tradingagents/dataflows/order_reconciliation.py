"""Final order reconciliation (P0.6): the last validated decision wins.

A run produces a chain of proposals — the analysts' signal, the Research
Manager's strategic decision, the Trader's plan, the risk analysts'
amendments, the Portfolio Manager's final decision — and only the last
*validated* stage may become the order candidate. The 18:53 report let the
Trader's tranche plan stand even where the Portfolio Manager's HOLD
disagreed with it.

Rules:

- **The Portfolio Manager prevails.** The reconciled candidate carries the
  PM's quantity, entry, stop and side — never the Trader's earlier
  proposal.
- **A revision invalidates prior authorizations.** Any change to
  quantity, entry, stop or side between stages marks the candidate as
  requiring full revalidation before it may be submitted; a stale
  authorization is never carried forward.
- **A HOLD never becomes an order.** A PM decision to hold/maintain
  reconciles to a zero-quantity, unauthorized candidate, whatever the
  Trader proposed.
- **A conditional plan stays distinct from an executable order.** The
  candidate records whether it is immediate or conditional; only an
  immediate, authorized, revalidated candidate may reach the Execution
  Gate's submission step.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# The stages of the decision chain, in order.
STAGES = ("analysts", "research_manager", "trader", "risk_analysts",
          "portfolio_manager")

# Actions that mean "no order".
_NON_ORDER_ACTIONS = frozenset({"HOLD", "MAINTAIN", "MONITOR", "AVOID",
                                "REDUCE", "WAIT"})


@dataclass(frozen=True)
class OrderCandidate:
    """One stage's proposal as an order-shaped candidate.

    ``quantity`` 0 with a non-order ``action`` means the stage proposes no
    trade. ``conditional`` marks a plan that needs its trigger evaluated
    before execution — it is never an immediately executable order.
    """

    stage: str                        # one of STAGES
    ticker: str
    side: str                         # "LONG" | "SHORT"
    quantity: int
    entry: float | None = None
    stop: float | None = None
    action: str = "BUY"               # "BUY" | "SELL" | "HOLD" | …
    conditional: bool = False
    reason: str = ""

    def __post_init__(self):
        if self.stage not in STAGES:
            raise ValueError(
                f"stage {self.stage!r} is not one of {STAGES}"
            )
        if self.side not in ("LONG", "SHORT"):
            raise ValueError(f"side must be LONG or SHORT, got {self.side!r}")
        if self.quantity < 0:
            raise ValueError(f"quantity must be >= 0, got {self.quantity}")

    @property
    def is_non_order(self) -> bool:
        return self.action.upper() in _NON_ORDER_ACTIONS or self.quantity == 0

    def differs_from(self, other: OrderCandidate) -> bool:
        """Whether the plan's numbers changed between two stages."""
        return (
            self.quantity != other.quantity
            or self.entry != other.entry
            or self.stop != other.stop
            or self.side != other.side
        )


@dataclass
class ReconciliationResult:
    """The reconciled order candidate, with the audit trail of the chain."""

    final: OrderCandidate
    chain: list[OrderCandidate] = field(default_factory=list)
    pm_prevailed: bool = False
    requires_revalidation: bool = False
    authorized: bool = False
    reason: str = ""

    def summary(self) -> dict:
        return {
            "final": {
                "stage": self.final.stage,
                "side": self.final.side,
                "quantity": self.final.quantity,
                "entry": self.final.entry,
                "stop": self.final.stop,
                "action": self.final.action,
                "conditional": self.final.conditional,
            },
            "chain": [
                {"stage": c.stage, "quantity": c.quantity, "action": c.action}
                for c in self.chain
            ],
            "pm_prevailed": self.pm_prevailed,
            "requires_revalidation": self.requires_revalidation,
            "authorized": self.authorized,
            "reason": self.reason,
        }


def reconcile_order(
    trader: OrderCandidate,
    pm: OrderCandidate,
    *,
    prior_authorized: bool = False,
) -> ReconciliationResult:
    """Reconcile the Trader's proposal with the PM's final decision.

    The PM's candidate is the order candidate — its quantity, entry, stop
    and side win. When the PM revised the plan's numbers (or the plan was
    previously authorized and anything changed), the result requires full
    revalidation before submission. A PM hold/maintain decision reconciles
    to an unauthorized zero-quantity candidate: a HOLD never becomes a
    BUY or SELL.
    """
    chain = [trader, pm]
    revised = pm.differs_from(trader)
    requires_revalidation = revised or (prior_authorized and revised)

    if pm.is_non_order:
        final = OrderCandidate(
            stage="portfolio_manager", ticker=pm.ticker, side=pm.side,
            quantity=0, entry=pm.entry, stop=pm.stop, action=pm.action,
            conditional=pm.conditional,
            reason=pm.reason or "the Portfolio Manager decided not to trade",
        )
        return ReconciliationResult(
            final=final, chain=chain, pm_prevailed=True,
            requires_revalidation=requires_revalidation,
            authorized=False,
            reason=(
                f"the Portfolio Manager's {pm.action} decision produces no "
                "order; the Trader's earlier proposal is discarded"
            ),
        )

    final = OrderCandidate(
        stage="portfolio_manager", ticker=pm.ticker, side=pm.side,
        quantity=pm.quantity, entry=pm.entry, stop=pm.stop,
        action=pm.action, conditional=pm.conditional, reason=pm.reason,
    )
    return ReconciliationResult(
        final=final, chain=chain, pm_prevailed=True,
        requires_revalidation=requires_revalidation,
        # Authorized only when the PM's plan is unchanged from an already
        # authorized proposal: any revision needs fresh validation.
        authorized=prior_authorized and not revised,
        reason=(
            "the Portfolio Manager's decision prevails"
            + ("; the plan was revised, so prior authorizations are void "
               "and full revalidation is required" if revised else "")
        ),
    )
