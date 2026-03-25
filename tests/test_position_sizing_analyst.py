import json

from tradingagents.graph.setup import GraphSetup
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.graph.propagation import Propagator


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


def test_position_sizing_tools_route_to_vendor(monkeypatch):
    import tradingagents.dataflows.interface as interface
    from tradingagents.agents.utils.sizing_tools import (
        get_sizing_fundamentals,
        get_sizing_indicator,
        get_sizing_price_history,
    )

    calls = []

    def fake_route_to_vendor(method, *args, **kwargs):
        calls.append((method, args, kwargs))
        return f"{method}-result"

    monkeypatch.setattr(interface, "route_to_vendor", fake_route_to_vendor)

    assert (
        get_sizing_fundamentals.invoke({"ticker": "AAPL", "curr_date": "2026-03-24"})
        == "get_fundamentals-result"
    )
    assert (
        get_sizing_indicator.invoke(
            {
                "symbol": "AAPL",
                "indicator": "atr",
                "curr_date": "2026-03-24",
                "look_back_days": 30,
            }
        )
        == "get_indicators-result"
    )
    assert (
        get_sizing_price_history.invoke(
            {
                "symbol": "AAPL",
                "start_date": "2026-02-01",
                "end_date": "2026-03-24",
            }
        )
        == "get_stock_data-result"
    )
    assert calls == [
        ("get_fundamentals", (), {"ticker": "AAPL", "curr_date": "2026-03-24"}),
        (
            "get_indicators",
            (),
            {
                "symbol": "AAPL",
                "indicator": "atr",
                "curr_date": "2026-03-24",
                "look_back_days": 30,
            },
        ),
        (
            "get_stock_data",
            (),
            {
                "symbol": "AAPL",
                "start_date": "2026-02-01",
                "end_date": "2026-03-24",
            },
        ),
    ]


def test_graph_setup_wires_position_sizing_analyst_and_tools(monkeypatch):
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
        "tradingagents.graph.setup.create_position_sizing_analyst",
        make_factory("Position_sizing Analyst"),
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

        def should_continue_position_sizing(self, _state):
            return "Msg Clear Position_sizing"

        def should_continue_debate(self, _state):
            return "Research Manager"

        def should_continue_risk_analysis(self, _state):
            return "Portfolio Manager"

    setup = GraphSetup(
        quick_thinking_llm="quick-llm",
        deep_thinking_llm="deep-llm",
        tool_nodes={"market": "market-tools", "position_sizing": "position-tools"},
        bull_memory=object(),
        bear_memory=object(),
        trader_memory=object(),
        invest_judge_memory=object(),
        portfolio_manager_memory=object(),
        conditional_logic=PartialConditionalLogic(),
        role_llms={"position_sizing": "position-llm"},
    )

    graph = setup.setup_graph(selected_analysts=["market", "position_sizing"])

    assert recorded_llms["Position_sizing Analyst"] == "position-llm"
    assert graph["nodes"]["Position_sizing Analyst"] == "Position_sizing Analyst"
    assert graph["nodes"]["tools_position_sizing"] == "position-tools"
    assert "Position_sizing Analyst" in graph["conditional_edges"]


def test_trading_graph_creates_position_sizing_tool_node(monkeypatch):
    monkeypatch.setattr("tradingagents.graph.trading_graph.ToolNode", DummyToolNode)

    graph = TradingAgentsGraph.__new__(TradingAgentsGraph)
    tool_nodes = TradingAgentsGraph._create_tool_nodes(graph)

    assert [tool.name for tool in tool_nodes["position_sizing"].tools] == [
        "get_sizing_fundamentals",
        "get_sizing_indicator",
        "get_sizing_price_history",
    ]


class DummyPrompt:
    def __init__(self, result):
        self.result = result

    def partial(self, **_kwargs):
        return self

    def __or__(self, _other):
        return DummyChain(self.result)


class DummyChain:
    def __init__(self, result):
        self.result = result

    def invoke(self, _messages):
        return self.result


class DummyResult:
    def __init__(self, content, tool_calls):
        self.content = content
        self.tool_calls = tool_calls


class DummyLLM:
    def __init__(self, result):
        self.result = result
        self.bound_tool_names = []

    def bind_tools(self, tools):
        self.bound_tool_names = [tool.name for tool in tools]
        return object()


def test_position_sizing_analyst_returns_structured_data(monkeypatch):
    from tradingagents.agents.analysts.position_sizing_analyst import (
        create_position_sizing_analyst,
    )

    result = DummyResult(
        content="""## Position Sizing Summary

High conviction setup with a staged entry and explicit loss budget.

    ```json
    {
      "conviction": "high",
      "target_weight_pct": 8,
      "initial_weight_pct": 4,
      "max_loss_pct": 1.5,
      "sizing_rationale": "Strong setup with manageable downside and room to scale."
    }
    ```""",
        tool_calls=[],
    )

    monkeypatch.setattr(
        "tradingagents.agents.analysts.position_sizing_analyst.ChatPromptTemplate.from_messages",
        lambda *_args, **_kwargs: DummyPrompt(result),
    )

    llm = DummyLLM(result)
    node = create_position_sizing_analyst(llm)

    payload = node(
        {
            "messages": [("human", "AAPL")],
            "trade_date": "2026-03-24",
            "company_of_interest": "AAPL",
        }
    )

    assert llm.bound_tool_names == [
        "get_sizing_fundamentals",
        "get_sizing_indicator",
        "get_sizing_price_history",
    ]
    assert payload["position_sizing_report"] == result.content
    assert payload["position_sizing_data"] == {
        "ticker": "AAPL",
        "analysis_date": "2026-03-24",
        "conviction": "high",
        "target_weight_pct": 8,
        "initial_weight_pct": 4,
        "max_loss_pct": 1.5,
        "sizing_rationale": "Strong setup with manageable downside and room to scale.",
    }


def test_position_sizing_state_fields_are_declared_and_seeded():
    from tradingagents.agents.utils.agent_states import AgentState

    assert "position_sizing_report" in AgentState.__annotations__
    assert "position_sizing_data" in AgentState.__annotations__

    state = Propagator().create_initial_state("AAPL", "2026-03-24")

    assert state["position_sizing_report"] == ""
    assert state["position_sizing_data"] == {
        "ticker": "",
        "analysis_date": "",
        "conviction": "",
        "target_weight_pct": None,
        "initial_weight_pct": None,
        "max_loss_pct": None,
        "sizing_rationale": "",
    }
