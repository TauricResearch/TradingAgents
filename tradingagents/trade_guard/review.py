"""Connect crypto agent ratings to deterministic PAPER risk checks without guessing an order.

A Portfolio Manager rating is NOT a broker instruction, even if it reads Sell.
The automated final-state review is *always* blocked. A separate, explicitly
supplied TradeIntent and verified market/portfolio snapshots are required to
call validate_paper_decision. No trade execution is implemented here.
"""

from __future__ import annotations

import re
from datetime import datetime

from tradingagents.agents.rating import run_rating

from .risk import (
    MarketSnapshot,
    PortfolioSnapshot,
    RiskLimits,
    TradeIntent,
    TradeVerdict,
    validate_intent,
)

_TRADER_ACTION = re.compile(
    r"^\s*\*{0,2}Action\*{0,2}:\s*\*{0,2}(Buy|Sell|Hold)\b",
    re.IGNORECASE | re.MULTILINE,
)


def read_trader_action(report: str) -> str | None:
    """Only parse the Trader's explicit Action field, not speculative prose."""
    match = _TRADER_ACTION.search(report or "")
    return match.group(1).capitalize() if match else None


def agent_decision_review(state: dict) -> dict | None:
    """Read-only guard evaluation for crypto runs; never creates a TradeIntent."""
    if state.get("asset_type") != "crypto":
        return None
    rating = run_rating(state)
    trader = read_trader_action(state.get("trader_investment_plan", ""))
    reasons = ["NO_EXPLICIT_TRADE_INTENT", "NO_VERIFIED_MARKET_AND_PORTFOLIO_SNAPSHOTS"]
    if rating == "REVIEW":
        reasons.append("UNREADABLE_PORTFOLIO_RATING")
    if trader is None:
        reasons.append("UNREADABLE_TRADER_ACTION")
    if rating in ("Sell", "Underweight"):
        reasons.append("SELL_DOES_NOT_IDENTIFY_SPOT_EXIT_OR_SHORT")
    if (
        (rating in ("Sell", "Underweight") and trader == "Buy")
        or (rating in ("Buy", "Overweight") and trader == "Sell")
    ):
        reasons.append("TRADER_PORTFOLIO_DIRECTION_CONFLICT")
    if rating == "Hold" or trader == "Hold":
        reasons.append("NO_TRADE_HOLD_SIGNAL")
    return {
        "status": "BLOCKED",
        "approved": False,
        "execution_mode": "NONE",
        "portfolio_rating": rating,
        "trader_action": trader,
        "reasons": reasons,
    }


def render_decision_review(review: dict) -> str:
    """Human-readable section generated only from deterministic, sanitized fields."""
    reasons = "\n".join(f"- {reason}" for reason in review["reasons"])
    return (
        "**Status**: BLOCKED — not an executable order\n\n"
        f"**Portfolio rating**: {review['portfolio_rating']}\n\n"
        f"**Trader action**: {review['trader_action'] or 'not provided'}\n\n"
        "**Execution mode**: NONE (paper-only validation available separately)\n\n"
        "**Blocking reasons**:\n"
        f"{reasons}\n\n"
        "To evaluate a simulated order, explicitly supply a TradeIntent, a "
        "timestamped independent MarketSnapshot and a PortfolioSnapshot, then "
        "call validate_paper_decision(). This report never executes orders."
    )


def attach_decision_review(state: dict) -> None:
    """Annotate the final state in both CLI and programmatic record paths."""
    review = agent_decision_review(state)
    if review is not None:
        state["trade_guard_review"] = review
        state["trade_guard_report"] = render_decision_review(review)


def validate_paper_decision(
    state: dict,
    intent: TradeIntent,
    market: MarketSnapshot,
    portfolio: PortfolioSnapshot,
    *,
    now: datetime,
    limits: RiskLimits | None = None,
) -> TradeVerdict:
    """Paper-only gate requiring *both* coherent agent direction and valid numbers.

    This does not construct an order from text; the caller must explicitly select
    SPOT_BUY, SPOT_SELL or SHORT_OPEN. Approval here is only for paper simulation.
    """
    reasons: list[str] = []
    if state.get("asset_type") != "crypto":
        reasons.append("NOT_A_CRYPTO_ANALYSIS")
    if state.get("company_of_interest") != intent.symbol:
        reasons.append("ORDER_SYMBOL_DIFFERS_FROM_ANALYSIS")

    rating = run_rating(state)
    action = read_trader_action(state.get("trader_investment_plan", ""))
    if rating not in ("Buy", "Sell") or action not in ("Buy", "Sell"):
        reasons.append("NO_CONSISTENT_ACTIONABLE_AGENT_DIRECTION")
    elif rating != action:
        reasons.append("TRADER_PORTFOLIO_DIRECTION_CONFLICT")
    elif (
        (rating == "Buy" and intent.action != "SPOT_BUY")
        or (rating == "Sell" and intent.action not in ("SPOT_SELL", "SHORT_OPEN"))
    ):
        reasons.append("INTENT_CONTRADICTS_AGENT_DIRECTION")

    numeric_verdict = validate_intent(intent, market, portfolio, now=now, limits=limits)
    reasons.extend(numeric_verdict.reasons)
    return TradeVerdict(
        approved=not reasons,
        reasons=tuple(reasons),
        notional_quote=numeric_verdict.notional_quote,
        theoretical_stop_loss_quote=numeric_verdict.theoretical_stop_loss_quote,
    )
