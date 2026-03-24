import json

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from tradingagents.agents.utils.agent_states import AgentState
from tradingagents.graph.setup import GraphSetup
from tradingagents.graph.trading_graph import TradingAgentsGraph


class DummyStateGraph:
    def __init__(self, _state_type):
        self.nodes = {}
        self.conditional_edges = {}

    def add_node(self, name, node):
        self.nodes[name] = node

    def add_edge(self, *_args, **_kwargs):
        return None

    def add_conditional_edges(self, source, condition, destinations):
        self.conditional_edges[source] = {
            "condition": condition,
            "destinations": destinations,
        }

    def compile(self):
        return {
            "nodes": self.nodes,
            "conditional_edges": self.conditional_edges,
        }


class DummyToolNode:
    def __init__(self, tools):
        self.tools = tools


def test_valuation_tools_route_to_vendor(monkeypatch):
    import tradingagents.dataflows.interface as interface
    from tradingagents.agents.utils.valuation_tools import get_valuation_inputs

    calls = []

    def fake_route_to_vendor(method, *args, **kwargs):
        calls.append((method, args, kwargs))
        return f"{method}-result"

    monkeypatch.setattr(interface, "route_to_vendor", fake_route_to_vendor)

    assert (
        get_valuation_inputs.invoke({"ticker": "NVDA", "curr_date": "2026-03-24"})
        == "get_fundamentals-result"
    )
    assert calls == [
        ("get_fundamentals", (), {"ticker": "NVDA", "curr_date": "2026-03-24"})
    ]


def test_graph_setup_wires_valuation_analyst_and_tools(monkeypatch):
    recorded_llms = {}

    monkeypatch.setattr("tradingagents.graph.setup.StateGraph", DummyStateGraph)
    monkeypatch.setattr("tradingagents.graph.setup.create_msg_delete", lambda: "delete")

    def make_factory(node_name):
        def factory(llm, *_args):
            recorded_llms[node_name] = llm
            return node_name

        return factory

    monkeypatch.setattr(
        "tradingagents.graph.setup.create_market_analyst",
        make_factory("Market Analyst"),
    )
    monkeypatch.setattr(
        "tradingagents.graph.setup.create_valuation_analyst",
        make_factory("Valuation Analyst"),
    )
    monkeypatch.setattr(
        "tradingagents.graph.setup.create_social_media_analyst",
        make_factory("Social Analyst"),
    )
    monkeypatch.setattr(
        "tradingagents.graph.setup.create_news_analyst",
        make_factory("News Analyst"),
    )
    monkeypatch.setattr(
        "tradingagents.graph.setup.create_fundamentals_analyst",
        make_factory("Fundamentals Analyst"),
    )
    monkeypatch.setattr(
        "tradingagents.graph.setup.create_factor_rule_analyst",
        make_factory("Factor Rules Analyst"),
    )
    monkeypatch.setattr(
        "tradingagents.graph.setup.create_macro_analyst",
        make_factory("Macro Analyst"),
    )
    monkeypatch.setattr(
        "tradingagents.graph.setup.create_bull_researcher",
        make_factory("Bull Researcher"),
    )
    monkeypatch.setattr(
        "tradingagents.graph.setup.create_bear_researcher",
        make_factory("Bear Researcher"),
    )
    monkeypatch.setattr(
        "tradingagents.graph.setup.create_research_manager",
        make_factory("Research Manager"),
    )
    monkeypatch.setattr(
        "tradingagents.graph.setup.create_trader",
        make_factory("Trader"),
    )
    monkeypatch.setattr(
        "tradingagents.graph.setup.create_aggressive_debator",
        make_factory("Aggressive Analyst"),
    )
    monkeypatch.setattr(
        "tradingagents.graph.setup.create_neutral_debator",
        make_factory("Neutral Analyst"),
    )
    monkeypatch.setattr(
        "tradingagents.graph.setup.create_conservative_debator",
        make_factory("Conservative Analyst"),
    )
    monkeypatch.setattr(
        "tradingagents.graph.setup.create_portfolio_manager",
        make_factory("Portfolio Manager"),
    )

    class PartialConditionalLogic:
        def should_continue_market(self, _state):
            return "Msg Clear Market"

        def should_continue_debate(self, _state):
            return "Research Manager"

        def should_continue_risk_analysis(self, _state):
            return "Portfolio Manager"

    setup = GraphSetup(
        quick_thinking_llm="quick-llm",
        deep_thinking_llm="deep-llm",
        tool_nodes={"market": "market-tools", "valuation": "valuation-tools"},
        bull_memory=object(),
        bear_memory=object(),
        trader_memory=object(),
        invest_judge_memory=object(),
        portfolio_manager_memory=object(),
        conditional_logic=PartialConditionalLogic(),
        role_llms={"valuation": "valuation-llm"},
    )

    graph = setup.setup_graph(selected_analysts=["market", "valuation"])

    assert recorded_llms["Valuation Analyst"] == "valuation-llm"
    assert graph["nodes"]["Valuation Analyst"] == "Valuation Analyst"
    assert graph["nodes"]["tools_valuation"] == "valuation-tools"
    assert graph["conditional_edges"]["Valuation Analyst"]["destinations"] == [
        "tools_valuation",
        "Msg Clear Valuation",
    ]


def test_trading_graph_creates_valuation_tool_node(monkeypatch):
    monkeypatch.setattr("tradingagents.graph.trading_graph.ToolNode", DummyToolNode)

    graph = TradingAgentsGraph.__new__(TradingAgentsGraph)
    tool_nodes = TradingAgentsGraph._create_tool_nodes(graph)

    assert [tool.name for tool in tool_nodes["valuation"].tools] == [
        "get_valuation_inputs"
    ]


def test_valuation_analyst_returns_structured_valuation_data():
    from tradingagents.agents.analysts.valuation_analyst import create_valuation_analyst

    response = {
        "fair_value_range": {"low": 120.5, "high": 145.0},
        "expected_return_pct": 18.2,
        "primary_method": "discounted cash flow",
        "thesis": "Free cash flow implies upside versus the current price.",
    }

    class FakeLLM:
        def bind_tools(self, _tools):
            return RunnableLambda(
                lambda _inputs: AIMessage(content=json.dumps(response), tool_calls=[])
            )

    node = create_valuation_analyst(FakeLLM())
    result = node(
        {
            "trade_date": "2026-03-24",
            "company_of_interest": "NVDA",
            "messages": [("human", "Value NVDA")],
        }
    )

    assert result["valuation_data"] == response
    assert list(result) == ["messages", "valuation_data"]


def test_valuation_analyst_marks_parse_failure_without_changing_shape():
    from tradingagents.agents.analysts.valuation_analyst import create_valuation_analyst

    class FakeLLM:
        def bind_tools(self, _tools):
            return RunnableLambda(
                lambda _inputs: AIMessage(content="not valid json", tool_calls=[])
            )

    node = create_valuation_analyst(FakeLLM())
    result = node(
        {
            "trade_date": "2026-03-24",
            "company_of_interest": "NVDA",
            "messages": [("human", "Value NVDA")],
        }
    )

    assert set(result["valuation_data"]) == {
        "fair_value_range",
        "expected_return_pct",
        "primary_method",
        "thesis",
    }
    assert result["valuation_data"]["fair_value_range"] == {"low": None, "high": None}
    assert result["valuation_data"]["expected_return_pct"] is None
    assert result["valuation_data"]["primary_method"] == "parse_error"
    assert result["valuation_data"]["thesis"] == "not valid json"


def test_valuation_analyst_populates_structured_data_after_tool_loop(monkeypatch):
    import tradingagents.dataflows.interface as interface
    from tradingagents.agents.analysts.valuation_analyst import create_valuation_analyst
    from tradingagents.agents.utils.valuation_tools import get_valuation_inputs

    llm_responses = iter(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "get_valuation_inputs",
                        "args": {"ticker": "NVDA", "curr_date": "2026-03-24"},
                        "id": "call_1",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(
                content=json.dumps(
                    {
                        "fair_value_range": {"low": 120.5, "high": 145.0},
                        "expected_return_pct": 18.2,
                        "primary_method": "discounted cash flow",
                        "thesis": "Free cash flow implies upside versus the current price.",
                    }
                ),
                tool_calls=[],
            ),
        ]
    )

    calls = []

    def fake_route_to_vendor(method, *args, **kwargs):
        calls.append((method, args, kwargs))
        return "valuation inputs"

    monkeypatch.setattr(interface, "route_to_vendor", fake_route_to_vendor)

    class FakeLLM:
        def bind_tools(self, _tools):
            return RunnableLambda(lambda _inputs: next(llm_responses))

    node = create_valuation_analyst(FakeLLM())
    workflow = StateGraph(AgentState)
    workflow.add_node("Valuation Analyst", node)
    workflow.add_node("tools_valuation", ToolNode([get_valuation_inputs]))
    workflow.add_node("Msg Clear Valuation", lambda _state: {})
    workflow.add_edge(START, "Valuation Analyst")
    workflow.add_conditional_edges(
        "Valuation Analyst",
        lambda state: (
            "tools_valuation"
            if getattr(state["messages"][-1], "tool_calls", None)
            else "Msg Clear Valuation"
        ),
        ["tools_valuation", "Msg Clear Valuation"],
    )
    workflow.add_edge("tools_valuation", "Valuation Analyst")
    workflow.add_edge("Msg Clear Valuation", END)

    final_state = workflow.compile().invoke(
        {
            "trade_date": "2026-03-24",
            "company_of_interest": "NVDA",
            "messages": [("human", "Value NVDA")],
        }
    )

    assert final_state["valuation_data"] == {
        "fair_value_range": {"low": 120.5, "high": 145.0},
        "expected_return_pct": 18.2,
        "primary_method": "discounted cash flow",
        "thesis": "Free cash flow implies upside versus the current price.",
    }
    assert calls == [
        ("get_fundamentals", (), {"ticker": "NVDA", "curr_date": "2026-03-24"})
    ]
