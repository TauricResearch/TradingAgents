from copy import deepcopy

from langgraph.graph import END, START, StateGraph

from tradingagents.agents.utils.agent_states import AgentState
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
    "ticker": "",
    "analysis_date": "",
    "business_unit_decomposition": [],
    "segment_economics": {},
    "value_driver_map": [],
}

EXPECTED_SCENARIO_CATALYST_DATA = {
    "ticker": "",
    "analysis_date": "",
    "scenario_map": [],
    "dated_catalyst_map": [],
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

STRUCTURED_PASSTHROUGH_KEYS = {
    "valuation_data",
    "segment_data",
    "scenario_catalyst_data",
    "position_sizing_data",
    "chief_analyst_data",
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


def assert_manager_update_omits_structured_passthrough(
    payload, expected_present_keys
):
    for key in expected_present_keys:
        assert key in payload
    assert STRUCTURED_PASSTHROUGH_KEYS.isdisjoint(payload)


def compile_single_node_graph(node_name, node):
    workflow = StateGraph(AgentState)
    workflow.add_node(node_name, node)
    workflow.add_edge(START, node_name)
    workflow.add_edge(node_name, END)
    return workflow.compile()


def test_propagator_initializes_structured_stock_underwriting_fields():
    initial_state = Propagator().create_initial_state("NVDA", "2026-03-24")

    assert_structured_stock_fields(initial_state)


def test_research_manager_update_omits_structured_stock_passthrough_fields(monkeypatch):
    monkeypatch.setattr(
        "tradingagents.agents.managers.research_manager.build_instrument_context",
        lambda _ticker: "instrument context",
    )

    state = Propagator().create_initial_state("NVDA", "2026-03-24")
    research_manager = create_research_manager(
        DummyLLM("Research manager output"),
        DummyMemory(),
    )
    research_result = research_manager(deepcopy(state))

    assert research_result["investment_plan"] == "Research manager output"
    assert research_result["investment_debate_state"]["judge_decision"] == (
        "Research manager output"
    )
    assert_manager_update_omits_structured_passthrough(
        research_result,
        {"investment_debate_state", "investment_plan"},
    )


def test_research_manager_graph_preserves_structured_stock_underwriting_fields(
    monkeypatch,
):
    monkeypatch.setattr(
        "tradingagents.agents.managers.research_manager.build_instrument_context",
        lambda _ticker: "instrument context",
    )

    research_manager = create_research_manager(
        DummyLLM("Research manager output"),
        DummyMemory(),
    )
    state = Propagator().create_initial_state("NVDA", "2026-03-24")

    final_state = compile_single_node_graph("Research Manager", research_manager).invoke(
        state
    )

    assert final_state["investment_plan"] == "Research manager output"
    assert final_state["investment_debate_state"]["judge_decision"] == (
        "Research manager output"
    )
    assert_structured_stock_fields(final_state)


def test_portfolio_manager_update_omits_structured_stock_passthrough_fields(
    monkeypatch,
):
    monkeypatch.setattr(
        "tradingagents.agents.managers.portfolio_manager.build_instrument_context",
        lambda _ticker: "instrument context",
    )

    state = Propagator().create_initial_state("NVDA", "2026-03-24")
    state["investment_plan"] = "Existing investment plan"
    portfolio_manager = create_portfolio_manager(
        DummyLLM("Portfolio manager output"),
        DummyMemory(),
    )
    portfolio_result = portfolio_manager(deepcopy(state))

    assert portfolio_result["final_trade_decision"] == "Portfolio manager output"
    assert portfolio_result["risk_debate_state"]["judge_decision"] == (
        "Portfolio manager output"
    )
    assert_manager_update_omits_structured_passthrough(
        portfolio_result,
        {"risk_debate_state", "final_trade_decision"},
    )


def test_portfolio_manager_graph_preserves_structured_stock_underwriting_fields(
    monkeypatch,
):
    monkeypatch.setattr(
        "tradingagents.agents.managers.portfolio_manager.build_instrument_context",
        lambda _ticker: "instrument context",
    )

    portfolio_manager = create_portfolio_manager(
        DummyLLM("Portfolio manager output"),
        DummyMemory(),
    )
    state = Propagator().create_initial_state("NVDA", "2026-03-24")
    state["investment_plan"] = "Existing investment plan"

    final_state = compile_single_node_graph(
        "Portfolio Manager", portfolio_manager
    ).invoke(state)

    assert final_state["final_trade_decision"] == "Portfolio manager output"
    assert final_state["risk_debate_state"]["judge_decision"] == (
        "Portfolio manager output"
    )
    assert_structured_stock_fields(final_state)
