from copy import deepcopy

from tradingagents.agents.managers.portfolio_manager import create_portfolio_manager
from tradingagents.agents.managers.research_manager import create_research_manager
from tradingagents.agents.researchers.bear_researcher import create_bear_researcher
from tradingagents.agents.researchers.bull_researcher import create_bull_researcher
from tradingagents.agents.risk_mgmt.aggressive_debator import create_aggressive_debator
from tradingagents.agents.risk_mgmt.conservative_debator import (
    create_conservative_debator,
)
from tradingagents.agents.risk_mgmt.neutral_debator import create_neutral_debator
from tradingagents.graph.propagation import Propagator


class DummyMemory:
    def get_memories(self, _situation, n_matches=2):
        return []


class DummyResponse:
    def __init__(self, content):
        self.content = content


class RecordingLLM:
    def __init__(self, content):
        self.content = content
        self.prompts = []

    def invoke(self, prompt):
        self.prompts.append(prompt)
        return DummyResponse(self.content)


def build_state():
    state = Propagator().create_initial_state("NVDA", "2026-03-24")
    state.update(
        {
            "market_report": "Market report",
            "sentiment_report": "Sentiment report",
            "news_report": "News report",
            "fundamentals_report": "Fundamentals report",
            "segment_report": "Segment report",
            "segment_data": {
                "ticker": "NVDA",
                "analysis_date": "2026-03-24",
                "business_unit_decomposition": [
                    {
                        "segment": "Alpha Widget",
                        "revenue_share_pct": 61,
                        "growth_trend": "expanding",
                        "strategic_role": "primary compute engine",
                    }
                ],
                "segment_economics": {
                    "margin_profile": "elite",
                    "capital_intensity": "moderate",
                    "cyclicality": "medium",
                },
                "value_driver_map": [
                    {
                        "driver": "AI rack demand",
                        "impacted_segments": ["Alpha Widget"],
                        "direction": "positive",
                        "horizon": "6-12 months",
                        "evidence": "backlog remains elevated",
                    }
                ],
            },
            "scenario_catalyst_report": "Scenario report",
            "scenario_catalyst_data": {
                "ticker": "NVDA",
                "analysis_date": "2026-03-24",
                "scenario_map": [
                    {
                        "name": "bull",
                        "probability_pct": 35,
                        "thesis": "AI demand acceleration",
                        "valuation_implication": "re-rating higher",
                        "signposts": ["order lead-times extend"],
                    }
                ],
                "dated_catalyst_map": [
                    {
                        "catalyst": "Lunar-launch catalyst",
                        "date_or_window": "2026-05",
                        "related_scenarios": ["bull"],
                        "expected_impact": "positive",
                        "confidence": "medium",
                    }
                ],
                "invalidation_triggers": [
                    {
                        "trigger": "gross margin drops below 70%",
                        "affected_scenarios": ["bull"],
                        "severity": "high",
                        "evidence_to_watch": "earnings release",
                    }
                ],
            },
            "position_sizing_report": "Sizing report",
            "position_sizing_data": {
                "ticker": "NVDA",
                "analysis_date": "2026-03-24",
                "conviction": "high",
                "target_weight_pct": 11.5,
                "initial_weight_pct": 6.0,
                "max_loss_pct": 1.25,
                "sizing_rationale": "Stage in but preserve dry powder for confirmation.",
            },
            "investment_plan": "Existing investment plan",
            "trader_investment_plan": "Trader plan",
        }
    )
    return state


def assert_prompt_mentions_structured_fields(prompt):
    text = str(prompt)
    assert "Prioritize the structured stock underwriting outputs below as primary evidence." in text
    assert "Alpha Widget" in text
    assert "AI rack demand" in text
    assert "Lunar-launch catalyst" in text
    assert "revenue_share_pct" in text
    assert "probability_pct" in text
    assert "target_weight_pct" in text
    assert "11.5" in text
    assert "1.25" in text


def test_research_side_prompts_consume_structured_fields(monkeypatch):
    monkeypatch.setattr(
        "tradingagents.agents.managers.research_manager.build_instrument_context",
        lambda _ticker: "instrument context",
    )

    state = build_state()

    bull_llm = RecordingLLM("Bull case")
    create_bull_researcher(bull_llm, DummyMemory())(deepcopy(state))
    assert_prompt_mentions_structured_fields(bull_llm.prompts[0])

    bear_llm = RecordingLLM("Bear case")
    create_bear_researcher(bear_llm, DummyMemory())(deepcopy(state))
    assert_prompt_mentions_structured_fields(bear_llm.prompts[0])

    research_llm = RecordingLLM("Research manager output")
    research_result = create_research_manager(research_llm, DummyMemory())(
        deepcopy(state)
    )
    assert_prompt_mentions_structured_fields(research_llm.prompts[0])
    assert research_result["investment_plan"] == "Research manager output"


def test_risk_and_portfolio_prompts_consume_structured_fields(monkeypatch):
    monkeypatch.setattr(
        "tradingagents.agents.managers.portfolio_manager.build_instrument_context",
        lambda _ticker: "instrument context",
    )

    state = build_state()

    aggressive_llm = RecordingLLM("Aggressive case")
    create_aggressive_debator(aggressive_llm)(deepcopy(state))
    assert_prompt_mentions_structured_fields(aggressive_llm.prompts[0])

    conservative_llm = RecordingLLM("Conservative case")
    create_conservative_debator(conservative_llm)(deepcopy(state))
    assert_prompt_mentions_structured_fields(conservative_llm.prompts[0])

    neutral_llm = RecordingLLM("Neutral case")
    create_neutral_debator(neutral_llm)(deepcopy(state))
    assert_prompt_mentions_structured_fields(neutral_llm.prompts[0])

    portfolio_llm = RecordingLLM("Portfolio output")
    portfolio_result = create_portfolio_manager(portfolio_llm, DummyMemory())(
        deepcopy(state)
    )
    assert_prompt_mentions_structured_fields(portfolio_llm.prompts[0])
    assert portfolio_result["final_trade_decision"] == "Portfolio output"
