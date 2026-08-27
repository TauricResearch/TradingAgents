from unittest.mock import MagicMock

import pytest

from tradingagents.agents.managers.portfolio_manager import create_portfolio_manager
from tradingagents.agents.schemas import (
    DataQuality,
    DecisionStatus,
    EvidenceItem,
    EvidenceKind,
    EvidenceStrength,
    PortfolioDecision,
    PortfolioRating,
    ResearchPlan,
    TraderAction,
    TraderProposal,
    render_pm_decision,
    render_research_plan,
    render_trader_proposal,
)
from tradingagents.graph.signal_processing import SignalProcessor
from tradingagents.research import (
    build_research_decision_record,
    collect_evidence_context,
    parse_portfolio_decision,
    parse_research_signal,
)


def _ledger_report() -> str:
    return """Analysis based on the supplied data.

## Evidence Ledger
| Claim | Source | As Of | Evidence Type | Strength | Limitations |
|---|---|---|---|---|---|
| Revenue grew | SEC 10-Q | 2026-05-01 | Sourced Fact | High | Unaudited quarter |
"""


def _state(**overrides):
    state = {
        "company_of_interest": "NVDA",
        "trade_date": "2026-06-01",
        "market_report": _ledger_report(),
        "sentiment_report": _ledger_report(),
        "news_report": _ledger_report(),
        "fundamentals_report": _ledger_report(),
        "research_run_metadata": {
            "schema_version": "research-decision-v1",
            "prompt_version": "evidence-contract-v1",
            "model_provider": "test-provider",
            "models": {"quick": "test-quick", "deep": "test-deep"},
            "selected_analysts": ["market", "social", "news", "fundamentals"],
            "data_vendors": {"core_stock_apis": "fixture"},
        },
    }
    state.update(overrides)
    return state


def _decision(*, confidence=0.72, status=DecisionStatus.RESEARCH_COMPLETE):
    return PortfolioDecision(
        rating=PortfolioRating.OVERWEIGHT,
        executive_summary="Research scenario only; reassess at the stated triggers.",
        investment_thesis="The supplied reports support a moderately positive view.",
        decision_status=status,
        time_horizon="20 trading days",
        expected_return_low=-0.03,
        expected_return_high=0.09,
        confidence=confidence,
        data_quality=DataQuality.HIGH,
        invalidation_conditions=["Close below 90 on verified daily data"],
        key_risks=["Earnings guidance misses consensus"],
        evidence=[
            EvidenceItem(
                claim="Latest close was 100",
                kind=EvidenceKind.SOURCED_FACT,
                source="verified market snapshot",
                as_of="2026-06-01",
                strength=EvidenceStrength.HIGH,
            )
        ],
    )


@pytest.mark.unit
def test_uncertainty_fields_render_without_changing_rating_enums():
    plan = ResearchPlan(
        recommendation=PortfolioRating.BUY,
        rationale="Evidence favors the upside case.",
        strategic_actions="Research scenario for human review.",
        decision_status=DecisionStatus.HUMAN_REVIEW_REQUIRED,
        time_horizon="3 months",
        expected_return_low=-0.05,
        expected_return_high=0.15,
        confidence=0.6,
        invalidation_conditions=["Demand falls below plan"],
    )
    proposal = TraderProposal(
        action=TraderAction.HOLD,
        reasoning="Wait for verification.",
        decision_status=DecisionStatus.NO_TRADE,
        time_horizon="3 months",
        expected_return_low=-0.05,
        expected_return_high=0.15,
        confidence=0.4,
        invalidation_conditions=["Guidance is unavailable"],
    )
    assert "**Recommendation**: Buy" in render_research_plan(plan)
    trader_markdown = render_trader_proposal(proposal)
    assert "**Decision Status**: No Trade" in trader_markdown
    assert "FINAL TRANSACTION PROPOSAL: **HOLD**" in trader_markdown


@pytest.mark.unit
def test_portfolio_decision_round_trips_uncertainty_and_evidence():
    markdown = render_pm_decision(_decision())
    parsed = parse_portfolio_decision(markdown)
    assert parsed["rating"] == "Overweight"
    assert parsed["expected_return_low"] == pytest.approx(-0.03)
    assert parsed["expected_return_high"] == pytest.approx(0.09)
    assert parsed["confidence"] == pytest.approx(0.72)
    assert parsed["invalidation_conditions"] == ["Close below 90 on verified daily data"]
    assert parsed["evidence"][0]["kind"] == "Sourced Fact"


@pytest.mark.unit
def test_actionable_record_passes_when_contract_is_complete():
    markdown = render_pm_decision(_decision())
    record = build_research_decision_record(_state(), markdown)
    assert record["rating"] == "Overweight"
    assert record["decision_status"] == DecisionStatus.RESEARCH_COMPLETE.value
    assert record["safety_gate"]["passed"] is True
    assert record["research_only"] is True


@pytest.mark.unit
def test_portfolio_context_includes_only_bounded_evidence_ledgers():
    state = _state(market_report="Narrative that should not be copied.\n\n" + _ledger_report())
    context = collect_evidence_context(state)
    assert "SEC 10-Q" in context
    assert "Narrative that should not be copied" not in context
    assert len(context) <= 10_000


@pytest.mark.unit
def test_low_confidence_preserves_rating_but_forces_no_trade():
    markdown = render_pm_decision(_decision(confidence=0.3))
    record = build_research_decision_record(_state(), markdown)
    assert record["rating"] == "Overweight"
    assert record["decision_status"] == DecisionStatus.NO_TRADE.value
    assert any("below" in reason for reason in record["safety_gate"]["reasons"])


@pytest.mark.unit
def test_missing_or_unavailable_report_forces_data_insufficient():
    state = _state(news_report="DATA_UNAVAILABLE: provider rate limited")
    record = build_research_decision_record(state, render_pm_decision(_decision()))
    assert record["decision_status"] == DecisionStatus.DATA_INSUFFICIENT.value
    assert record["requires_human_confirmation"] is True


@pytest.mark.unit
def test_legacy_rating_text_remains_compatible():
    text = "Rating: **Sell**\nExit if the thesis breaks."
    assert SignalProcessor().process_signal(text) == "Sell"
    parsed = parse_research_signal(text)
    assert parsed["rating"] == "Sell"
    assert parsed["decision_status"] == DecisionStatus.HUMAN_REVIEW_REQUIRED.value


@pytest.mark.unit
def test_portfolio_manager_adds_record_and_safety_block_when_policy_is_present():
    structured = MagicMock()
    structured.invoke.return_value = _decision(confidence=0.3)
    llm = MagicMock()
    llm.with_structured_output.return_value = structured
    state = _state(
        company_of_interest="NVDA",
        instrument_context="Ticker: NVDA",
        investment_plan="research plan",
        trader_investment_plan="trader proposal",
        past_context="",
        research_safety_policy={"enabled": True, "min_confidence": 0.55},
        risk_debate_state={
            "history": "risk discussion",
            "aggressive_history": "a",
            "conservative_history": "c",
            "neutral_history": "n",
            "current_aggressive_response": "a",
            "current_conservative_response": "c",
            "current_neutral_response": "n",
            "count": 1,
        },
    )
    result = create_portfolio_manager(llm)(state)
    assert "SEC 10-Q" in structured.invoke.call_args.args[0]
    assert result["research_result"]["decision_status"] == DecisionStatus.NO_TRADE.value
    assert result["research_signal"]["rating"] == "Overweight"
    assert result["research_signal"]["decision_status"] == DecisionStatus.NO_TRADE.value
    assert "### Deterministic Research Safety Gate" in result["final_trade_decision"]
    assert result["risk_debate_state"]["judge_decision"] == result["final_trade_decision"]


@pytest.mark.unit
def test_reversed_expected_return_bounds_are_rejected():
    with pytest.raises(ValueError, match="expected_return_low"):
        PortfolioDecision(
            rating=PortfolioRating.HOLD,
            executive_summary="x",
            investment_thesis="y",
            expected_return_low=0.2,
            expected_return_high=-0.1,
        )


@pytest.mark.unit
def test_invalid_safety_configuration_is_rejected():
    with pytest.raises(ValueError, match="min_confidence"):
        build_research_decision_record(
            _state(),
            render_pm_decision(_decision()),
            policy={"min_confidence": 1.5},
        )
