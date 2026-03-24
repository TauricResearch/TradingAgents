from copy import deepcopy

from tradingagents.agents.managers.portfolio_manager import create_portfolio_manager
from tradingagents.agents.managers.research_manager import create_research_manager
from tradingagents.graph.propagation import Propagator


EXPECTED_VALUATION_DATA = {
    "fair_value_range": {"low": None, "high": None},
    "expected_return_pct": None,
    "primary_method": "",
    "thesis": "",
}

EXPECTED_SEGMENT_DATA = {
    "segments": [],
    "dominant_segment": "",
    "thesis": "",
}

EXPECTED_SCENARIO_CATALYST_DATA = {
    "bull_case": {"probability": None, "price_target": None, "thesis": ""},
    "base_case": {"probability": None, "price_target": None, "thesis": ""},
    "bear_case": {"probability": None, "price_target": None, "thesis": ""},
    "catalysts": [],
    "invalidation_triggers": [],
}

EXPECTED_POSITION_SIZING_DATA = {
    "conviction": "",
    "target_weight_pct": None,
    "initial_weight_pct": None,
    "max_loss_pct": None,
}

EXPECTED_CHIEF_ANALYST_DATA = {
    "action": "",
    "summary": "",
    "thesis": "",
    "confidence": "",
}


class DummyMemory:
    def get_memories(self, _situation, n_matches=2):
        return []


class DummyResponse:
    def __init__(self, content):
        self.content = content


class DummyLLM:
    def __init__(self, content):
        self.content = content

    def invoke(self, _prompt):
        return DummyResponse(self.content)


def assert_structured_stock_fields(payload):
    assert payload["valuation_data"] == EXPECTED_VALUATION_DATA
    assert payload["segment_data"] == EXPECTED_SEGMENT_DATA
    assert payload["scenario_catalyst_data"] == EXPECTED_SCENARIO_CATALYST_DATA
    assert payload["position_sizing_data"] == EXPECTED_POSITION_SIZING_DATA
    assert payload["chief_analyst_data"] == EXPECTED_CHIEF_ANALYST_DATA


def test_propagator_initializes_structured_stock_underwriting_fields():
    initial_state = Propagator().create_initial_state("NVDA", "2026-03-24")

    assert_structured_stock_fields(initial_state)


def test_manager_nodes_preserve_structured_stock_underwriting_fields(monkeypatch):
    monkeypatch.setattr(
        "tradingagents.agents.managers.research_manager.build_instrument_context",
        lambda _ticker: "instrument context",
    )
    monkeypatch.setattr(
        "tradingagents.agents.managers.portfolio_manager.build_instrument_context",
        lambda _ticker: "instrument context",
    )

    state = Propagator().create_initial_state("NVDA", "2026-03-24")
    state["investment_plan"] = "Existing investment plan"

    research_manager = create_research_manager(
        DummyLLM("Research manager output"),
        DummyMemory(),
    )
    research_result = research_manager(deepcopy(state))

    assert research_result["investment_plan"] == "Research manager output"
    assert research_result["investment_debate_state"]["judge_decision"] == (
        "Research manager output"
    )
    assert_structured_stock_fields(research_result)

    portfolio_manager = create_portfolio_manager(
        DummyLLM("Portfolio manager output"),
        DummyMemory(),
    )
    portfolio_result = portfolio_manager(deepcopy(state))

    assert portfolio_result["final_trade_decision"] == "Portfolio manager output"
    assert portfolio_result["risk_debate_state"]["judge_decision"] == (
        "Portfolio manager output"
    )
    assert_structured_stock_fields(portfolio_result)
