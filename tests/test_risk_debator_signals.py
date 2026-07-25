from __future__ import annotations

import pytest

from tradingagents.agents.managers.portfolio_manager import create_portfolio_manager
from tradingagents.agents.risk_mgmt.aggressive_debator import create_aggressive_debator
from tradingagents.agents.risk_mgmt.conservative_debator import create_conservative_debator
from tradingagents.agents.risk_mgmt.neutral_debator import create_neutral_debator
from tradingagents.agents.risk_mgmt.signals import RiskDebatorOutput
from tradingagents.agents.schemas import (
    PortfolioDecision,
    PortfolioRating,
    RiskDebateSignal,
)


def _state() -> dict:
    return {
        "company_of_interest": "600000.SH",
        "instrument_context": "Instrument: 600000.SH",
        "market_report": "Market report: supportive trend.",
        "sentiment_report": "Sentiment report: mixed.",
        "news_report": "News report: no new catalyst.",
        "fundamentals_report": "Fundamentals: stable cash flow.",
        "investment_plan": "Hold pending clearer evidence.",
        "trader_investment_plan": "HOLD",
        "past_context": "",
        "portfolio_context": None,
        "risk_debate_state": {
            "history": "",
            "aggressive_history": "",
            "conservative_history": "",
            "neutral_history": "",
            "latest_speaker": "",
            "current_aggressive_response": "",
            "current_conservative_response": "",
            "current_neutral_response": "",
            "risk_signals": [],
            "judge_decision": "",
            "count": 0,
        },
    }


class _StructuredRiskLlm:
    def __init__(self, signal: RiskDebateSignal):
        self.signal = signal
        self.prompts: list[str] = []

    def with_structured_output(self, _schema):
        return self

    def invoke(self, prompt):
        self.prompts.append(prompt)
        return RiskDebatorOutput(response="Public conclusion grounded in the reports.", signal=self.signal)


@pytest.mark.parametrize(
    ("factory", "role", "conviction"),
    [
        (create_aggressive_debator, "aggressive", 0.7),
        (create_conservative_debator, "conservative", -0.8),
        (create_neutral_debator, "neutral", 0.0),
    ],
)
def test_each_risk_debator_persists_its_own_validated_public_signal(
    factory, role, conviction
):
    llm = _StructuredRiskLlm(
        RiskDebateSignal(
            role=role,
            conviction=conviction,
            confidence=0.75,
            evidence_summary="Reported market and fundamentals facts.",
        )
    )

    result = factory(llm)(_state())

    assert result["risk_debate_state"]["risk_signals"] == [
        {
            "role": role,
            "conviction": conviction,
            "confidence": 0.75,
            "abstain": False,
            "evidence_summary": "Reported market and fundamentals facts.",
        }
    ]
    assert "private reasoning" in llm.prompts[0]
    assert "Public conclusion" in result["risk_debate_state"]["history"]


class _PlainRiskLlm:
    def with_structured_output(self, _schema):
        raise NotImplementedError

    def invoke(self, _prompt):
        return type("Response", (), {"content": "A public plain-text risk response."})()


def test_unstructured_risk_response_records_abstention_instead_of_parsing_prose():
    result = create_aggressive_debator(_PlainRiskLlm())(_state())

    signal = result["risk_debate_state"]["risk_signals"][0]
    assert signal["role"] == "aggressive"
    assert signal["abstain"] is True
    assert signal["conviction"] is None
    assert signal["confidence"] == 0.0


def test_three_risk_debators_keep_one_independent_signal_per_role():
    state = _state()
    turns = (
        (create_aggressive_debator, "aggressive", 0.6),
        (create_conservative_debator, "conservative", -0.7),
        (create_neutral_debator, "neutral", 0.1),
    )
    for factory, role, conviction in turns:
        llm = _StructuredRiskLlm(
            RiskDebateSignal(
                role=role,
                conviction=conviction,
                confidence=0.8,
                evidence_summary=f"Public {role} evidence.",
            )
        )
        state["risk_debate_state"] = factory(llm)(state)["risk_debate_state"]

    signals = state["risk_debate_state"]["risk_signals"]
    assert [signal["role"] for signal in signals] == [
        "aggressive",
        "conservative",
        "neutral",
    ]


class _PortfolioLlm:
    def with_structured_output(self, _schema):
        return self

    def invoke(self, _prompt):
        return PortfolioDecision(
            rating=PortfolioRating.HOLD,
            executive_summary="Maintain exposure.",
            investment_thesis="The decision follows the supplied public signals.",
        )


def test_pm_aggregates_persisted_risk_signals_not_model_supplied_reconstruction():
    state = _state()
    state["risk_debate_state"]["risk_signals"] = [
        {
            "role": "aggressive",
            "conviction": 0.8,
            "confidence": 0.6,
            "abstain": False,
            "evidence_summary": "Reported upside catalyst.",
        },
        {
            "role": "conservative",
            "conviction": -0.8,
            "confidence": 0.9,
            "abstain": False,
            "evidence_summary": "Reported downside risk.",
        },
        {
            "role": "neutral",
            "conviction": None,
            "confidence": 0.0,
            "abstain": True,
            "evidence_summary": "No independently sufficient evidence.",
        },
    ]
    state["risk_debate_state"]["history"] = "Debate text cannot replace typed signals."

    result = create_portfolio_manager(_PortfolioLlm())(state)

    assert "**Risk Conviction Aggregate**: -0.16" in result["final_trade_decision"]
    assert "disagreement=mixed" in result["final_trade_decision"]
    assert "abstained=neutral" in result["final_trade_decision"]
