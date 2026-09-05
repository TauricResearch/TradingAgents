from datetime import date

from tradingagents.research_platform.agent_contracts import TradeDirection
from tradingagents.research_platform.risk_contracts import RiskDecision, RiskPolicy
from tradingagents.research_platform.signal_pipeline import review_legacy_decision


def test_review_legacy_decision_converts_signal_and_caps_risk():
    decision = (
        "**Rating**: Buy\n\n"
        "**Executive Summary**: Strong setup.\n\n"
        "**Position Sizing**: 15% of portfolio."
    )

    result = review_legacy_decision(
        symbol="NVDA",
        as_of_date=date(2026, 1, 5),
        decision_text=decision,
        confidence=0.8,
        policy=RiskPolicy(max_single_position_pct=0.10),
    )

    assert result.signal.direction == TradeDirection.BUY
    assert result.signal.proposed_position_pct == 0.15
    assert result.risk_review.decision == RiskDecision.REDUCE
    assert result.risk_review.approved_position_pct == 0.10


def test_review_legacy_decision_rejects_low_confidence_signal():
    decision = "**Rating**: Overweight\n\n**Position Sizing**: 5% of portfolio."

    result = review_legacy_decision(
        symbol="NVDA",
        as_of_date=date(2026, 1, 5),
        decision_text=decision,
        confidence=0.4,
        policy=RiskPolicy(min_signal_confidence=0.55),
    )

    assert result.signal.direction == TradeDirection.BUY
    assert result.risk_review.decision == RiskDecision.REJECT
    assert result.risk_review.approved_position_pct == 0.0


def test_review_legacy_hold_decision_is_watch_only():
    decision = "**Rating**: Hold\n\nNo edge."

    result = review_legacy_decision(
        symbol="NVDA",
        as_of_date=date(2026, 1, 5),
        decision_text=decision,
        current_position_pct=0.03,
    )

    assert result.signal.direction == TradeDirection.HOLD
    assert result.risk_review.decision == RiskDecision.WATCH
    assert result.risk_review.approved_position_pct == 0.03
