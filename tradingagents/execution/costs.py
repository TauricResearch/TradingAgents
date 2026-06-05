"""Runtime cost guardrail: does the trade's reward cover its costs?

Conservative pre-trade check (cost-accounting). The potential reward at the
take-profit must exceed broker commission + token cost, otherwise the trade is
not worth doing (no-trade). A probability-weighted version can refine this later.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..domain.state import Levels


def expected_reward(levels: Levels, quantity: float) -> float:
    """Potential gross profit if the take-profit is reached."""
    return abs(levels.take_profit - levels.entry_price) * abs(quantity)


def expected_risk(levels: Levels, quantity: float) -> float:
    """Potential loss if the stop is hit (= euro at risk)."""
    return abs(levels.entry_price - levels.stop_loss) * abs(quantity)


@dataclass
class CostAssessment:
    gross_reward: float
    commission: float
    token_cost: float
    net_expected_value: float
    ok: bool


def assess_costs(
    levels: Levels,
    quantity: float,
    *,
    commission: float = 0.0,
    token_cost: float = 0.0,
    min_net: float = 0.0,
) -> CostAssessment:
    """Net-EV = potential reward - commission - token cost; ok if it clears min_net."""
    gross = expected_reward(levels, quantity)
    net = gross - commission - token_cost
    return CostAssessment(
        gross_reward=gross,
        commission=commission,
        token_cost=token_cost,
        net_expected_value=net,
        ok=net > min_net,
    )
