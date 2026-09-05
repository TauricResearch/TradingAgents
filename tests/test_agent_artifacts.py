from datetime import date

import pytest

from tradingagents.research_platform.agent_artifacts import (
    analyst_note_from_legacy_report,
    investment_thesis_from_legacy_plan,
    render_analyst_note,
    render_investment_thesis,
    render_trade_signal,
    trade_direction_from_rating,
    trade_signal_from_legacy_decision,
)
from tradingagents.research_platform.agent_contracts import (
    AnalystNote,
    ConfidenceLevel,
    EvidenceRef,
    InvestmentThesis,
    TradeDirection,
    TradeHorizon,
    TradeSignal,
)


def _evidence() -> EvidenceRef:
    return EvidenceRef(
        source_id="price:NVDA:2026-01-05",
        description="Daily close and volume snapshot",
        as_of_date=date(2026, 1, 5),
        confidence=0.95,
    )


def test_render_analyst_note_includes_evidence_and_risks():
    note = AnalystNote(
        symbol="NVDA",
        analyst_role="Market Analyst",
        as_of_date=date(2026, 1, 5),
        summary="Trend is constructive.",
        evidence=[_evidence()],
        risks=["Gap risk into earnings."],
        confidence=ConfidenceLevel.HIGH,
    )

    md = render_analyst_note(note)

    assert "## Market Analyst Note: NVDA" in md
    assert "**Confidence:** high" in md
    assert "price:NVDA:2026-01-05" in md
    assert "- Gap risk into earnings." in md


def test_render_investment_thesis_includes_cases_and_disconfirming_evidence():
    thesis = InvestmentThesis(
        symbol="NVDA",
        as_of_date=date(2026, 1, 5),
        base_case="Base case.",
        bull_case="Bull case.",
        bear_case="Bear case.",
        catalysts=["Earnings revision."],
        disconfirming_evidence=["Gross margin compression."],
        evidence=[_evidence()],
        confidence=0.7,
    )

    md = render_investment_thesis(thesis)

    assert "### Base Case" in md
    assert "### Bull Case" in md
    assert "### Bear Case" in md
    assert "- Gross margin compression." in md
    assert "**Confidence:** 70%" in md


def test_render_trade_signal_includes_machine_relevant_fields():
    signal = TradeSignal(
        symbol="NVDA",
        as_of_date=date(2026, 1, 5),
        direction=TradeDirection.BUY,
        horizon=TradeHorizon.MEDIUM,
        confidence=0.75,
        rationale="Risk reward is favorable.",
        proposed_position_pct=0.05,
        expected_return_pct=0.12,
        stop_loss_pct=0.08,
        evidence=[_evidence()],
        invalidation_triggers=["Breaks below support."],
    )

    md = render_trade_signal(signal)

    assert "**Direction:** buy" in md
    assert "**Proposed Position:** 5.0%" in md
    assert "**Expected Return:** 12.0%" in md
    assert "- Breaks below support." in md


def test_legacy_analyst_report_wraps_as_note():
    note = analyst_note_from_legacy_report(
        symbol="NVDA",
        analyst_role="News Analyst",
        as_of_date=date(2026, 1, 5),
        report="News flow is constructive.",
        evidence=[_evidence()],
    )

    assert note.symbol == "NVDA"
    assert note.summary == "News flow is constructive."
    assert note.evidence[0].source_id == "price:NVDA:2026-01-05"


def test_legacy_investment_plan_becomes_conservative_thesis():
    plan = (
        "**Recommendation**: Overweight\n\n"
        "**Rationale**: Bull case carried the debate.\n\n"
        "**Strategic Actions**: Build gradually."
    )

    thesis = investment_thesis_from_legacy_plan(
        symbol="NVDA",
        as_of_date=date(2026, 1, 5),
        plan=plan,
        confidence=0.65,
    )

    assert "Bull case carried" in thesis.base_case
    assert "Build gradually" in thesis.base_case
    assert thesis.confidence == 0.65
    assert "legacy research plan" in thesis.bull_case


@pytest.mark.parametrize(
    ("rating", "direction"),
    [
        ("Buy", TradeDirection.BUY),
        ("Overweight", TradeDirection.BUY),
        ("Hold", TradeDirection.HOLD),
        ("Underweight", TradeDirection.SELL),
        ("Sell", TradeDirection.SELL),
    ],
)
def test_trade_direction_from_rating_maps_5_tier_to_3_way(rating, direction):
    assert trade_direction_from_rating(rating) == direction


def test_legacy_final_decision_becomes_trade_signal():
    decision = (
        "**Rating**: Overweight\n\n"
        "**Executive Summary**: Build exposure after confirmation.\n\n"
        "**Position Sizing**: 6% of portfolio.\n\n"
        "**Expected Return**: 14% over the horizon.\n\n"
        "**Stop Loss**: 8% below entry.\n\n"
        "**Invalidation Triggers**:\n"
        "- Data-center guidance rolls over.\n"
        "- Breaks below the 200-day average."
    )

    signal = trade_signal_from_legacy_decision(
        symbol="NVDA",
        as_of_date=date(2026, 1, 5),
        decision_text=decision,
        confidence=0.7,
    )

    assert signal.direction == TradeDirection.BUY
    assert signal.proposed_position_pct == 0.06
    assert signal.expected_return_pct == 0.14
    assert signal.stop_loss_pct == 0.08
    assert signal.invalidation_triggers == [
        "Data-center guidance rolls over.",
        "Breaks below the 200-day average.",
    ]


def test_legacy_decision_rejects_empty_text():
    with pytest.raises(ValueError):
        trade_signal_from_legacy_decision(
            symbol="NVDA",
            as_of_date=date(2026, 1, 5),
            decision_text=" ",
        )
