import pytest

from tradingagents.agents.schemas import (
    DecisionDriver,
    PortfolioDecision,
    PortfolioRating,
    RiskDebateSignal,
    render_pm_decision,
)
from tradingagents.portfolio import ConvictionSignal, aggregate_risk_convictions


def test_abstained_risk_role_does_not_dilute_conviction():
    aggregate = aggregate_risk_convictions(
        [
            ConvictionSignal("aggressive", 0.7, 0.8),
            ConvictionSignal("conservative", None, 1.0),
            ConvictionSignal("neutral", 0.3, 0.2),
        ]
    )

    assert aggregate.conviction == 0.62
    assert aggregate.abstained_roles == ("conservative",)
    assert aggregate.disagreement == "tight"


def test_pm_render_includes_public_risk_aggregate_and_cited_drivers():
    decision = PortfolioDecision(
        rating=PortfolioRating.HOLD,
        executive_summary="Wait for evidence.",
        investment_thesis="The risk debate is unresolved.",
        risk_signals=[
            RiskDebateSignal(role="aggressive", conviction=0.8, confidence=0.8),
            RiskDebateSignal(role="conservative", conviction=-0.9, confidence=0.9),
            RiskDebateSignal(role="neutral", abstain=True, confidence=0.5),
        ],
        top_drivers=[
            DecisionDriver(
                label="operating cash flow deteriorated",
                importance=0.9,
                evidence_ref="fundamentals_report#cash-flow",
                direction="risk",
            )
        ],
    )

    rendered = render_pm_decision(decision)

    assert "**Risk Conviction Aggregate**" in rendered
    assert "disagreement=mixed" in rendered
    assert "**Top Evidence-backed Drivers**" in rendered
    assert "evidence=fundamentals_report#cash-flow" in rendered


def test_risk_signal_requires_explicit_abstention():
    with pytest.raises(ValueError, match="non-abstaining"):
        RiskDebateSignal(role="neutral", confidence=0.3)
