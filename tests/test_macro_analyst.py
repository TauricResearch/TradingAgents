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


def test_macro_tools_route_to_vendor(monkeypatch):
    import tradingagents.dataflows.interface as interface
    from tradingagents.agents.utils.macro_data_tools import (
        get_economic_indicators,
        get_fed_calendar,
        get_yield_curve,
    )

    calls = []

    def fake_route_to_vendor(method, *args, **kwargs):
        calls.append((method, args, kwargs))
        return f"{method}-result"

    monkeypatch.setattr(interface, "route_to_vendor", fake_route_to_vendor)

    assert (
        get_economic_indicators.invoke(
            {"curr_date": "2026-03-24", "lookback_days": 30}
        )
        == "get_economic_indicators-result"
    )
    assert (
        get_yield_curve.invoke({"curr_date": "2026-03-24"})
        == "get_yield_curve-result"
    )
    assert (
        get_fed_calendar.invoke({"curr_date": "2026-03-24"})
        == "get_fed_calendar-result"
    )
    assert calls == [
        (
            "get_economic_indicators",
            (),
            {"curr_date": "2026-03-24", "lookback_days": 30},
        ),
        ("get_yield_curve", (), {"curr_date": "2026-03-24"}),
        ("get_fed_calendar", (), {"curr_date": "2026-03-24"}),
    ]


def test_graph_setup_wires_macro_analyst_and_macro_tools(monkeypatch):
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
        "tradingagents.graph.setup.create_macro_analyst",
        make_factory("Macro Analyst"),
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

        def should_continue_debate(self, _state):
            return "Research Manager"

        def should_continue_risk_analysis(self, _state):
            return "Portfolio Manager"

    setup = GraphSetup(
        quick_thinking_llm="quick-llm",
        deep_thinking_llm="deep-llm",
        tool_nodes={"market": "market-tools", "macro": "macro-tools"},
        bull_memory=object(),
        bear_memory=object(),
        trader_memory=object(),
        invest_judge_memory=object(),
        portfolio_manager_memory=object(),
        conditional_logic=PartialConditionalLogic(),
        role_llms={"macro": "macro-llm"},
    )

    graph = setup.setup_graph(selected_analysts=["market", "macro"])

    assert recorded_llms["Macro Analyst"] == "macro-llm"
    assert graph["nodes"]["Macro Analyst"] == "Macro Analyst"
    assert graph["nodes"]["tools_macro"] == "macro-tools"
    assert "Macro Analyst" in graph["conditional_edges"]


def test_trading_graph_creates_macro_tool_node(monkeypatch):
    monkeypatch.setattr("tradingagents.graph.trading_graph.ToolNode", DummyToolNode)

    graph = TradingAgentsGraph.__new__(TradingAgentsGraph)
    tool_nodes = TradingAgentsGraph._create_tool_nodes(graph)

    assert [tool.name for tool in tool_nodes["macro"].tools] == [
        "get_economic_indicators",
        "get_yield_curve",
        "get_fed_calendar",
    ]
