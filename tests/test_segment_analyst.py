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


def test_segment_tools_route_to_vendor(monkeypatch):
    import tradingagents.dataflows.interface as interface
    from tradingagents.agents.utils.segment_tools import (
        get_segment_fundamentals,
        get_segment_income_statement,
        get_segment_news,
    )

    calls = []

    def fake_route_to_vendor(method, *args, **kwargs):
        calls.append((method, args, kwargs))
        return f"{method}-result"

    monkeypatch.setattr(interface, "route_to_vendor", fake_route_to_vendor)

    assert (
        get_segment_fundamentals.invoke({"ticker": "AAPL", "curr_date": "2026-03-24"})
        == "get_fundamentals-result"
    )
    assert (
        get_segment_income_statement.invoke(
            {"ticker": "AAPL", "curr_date": "2026-03-24", "freq": "quarterly"}
        )
        == "get_income_statement-result"
    )
    assert (
        get_segment_news.invoke(
            {"query": "AAPL product segment demand", "start_date": "2026-03-01", "end_date": "2026-03-24"}
        )
        == "get_news-result"
    )
    assert calls == [
        (
            "get_fundamentals",
            (),
            {"ticker": "AAPL", "curr_date": "2026-03-24"},
        ),
        (
            "get_income_statement",
            (),
            {"ticker": "AAPL", "freq": "quarterly", "curr_date": "2026-03-24"},
        ),
        (
            "get_news",
            (),
            {
                "query": "AAPL product segment demand",
                "start_date": "2026-03-01",
                "end_date": "2026-03-24",
            },
        ),
    ]


def test_graph_setup_wires_segment_analyst_and_segment_tools(monkeypatch):
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
        "tradingagents.graph.setup.create_segment_analyst",
        make_factory("Segment Analyst"),
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

        def should_continue_segment(self, _state):
            return "Msg Clear Segment"

        def should_continue_debate(self, _state):
            return "Research Manager"

        def should_continue_risk_analysis(self, _state):
            return "Portfolio Manager"

    setup = GraphSetup(
        quick_thinking_llm="quick-llm",
        deep_thinking_llm="deep-llm",
        tool_nodes={"market": "market-tools", "segment": "segment-tools"},
        bull_memory=object(),
        bear_memory=object(),
        trader_memory=object(),
        invest_judge_memory=object(),
        portfolio_manager_memory=object(),
        conditional_logic=PartialConditionalLogic(),
        role_llms={"segment": "segment-llm"},
    )

    graph = setup.setup_graph(selected_analysts=["market", "segment"])

    assert recorded_llms["Segment Analyst"] == "segment-llm"
    assert graph["nodes"]["Segment Analyst"] == "Segment Analyst"
    assert graph["nodes"]["tools_segment"] == "segment-tools"
    assert "Segment Analyst" in graph["conditional_edges"]


def test_trading_graph_creates_segment_tool_node(monkeypatch):
    monkeypatch.setattr("tradingagents.graph.trading_graph.ToolNode", DummyToolNode)

    graph = TradingAgentsGraph.__new__(TradingAgentsGraph)
    tool_nodes = TradingAgentsGraph._create_tool_nodes(graph)

    assert [tool.name for tool in tool_nodes["segment"].tools] == [
        "get_segment_fundamentals",
        "get_segment_income_statement",
        "get_segment_news",
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


def test_segment_analyst_returns_structured_segment_data(monkeypatch):
    from tradingagents.agents.analysts.segment_analyst import create_segment_analyst

    result = DummyResult(
        content="""## Segment Summary

Apple's iPhone remains the primary demand engine, Services is the highest-quality
profit pool, and Wearables is a smaller but defensible ecosystem layer.

```json
{
  "business_unit_decomposition": [
    {
      "segment": "iPhone",
      "revenue_share_pct": 52,
      "growth_trend": "stable",
      "strategic_role": "core hardware platform"
    },
    {
      "segment": "Services",
      "revenue_share_pct": 23,
      "growth_trend": "expanding",
      "strategic_role": "high-margin recurring engine"
    }
  ],
  "segment_economics": {
    "margin_profile": {
      "iPhone": "mid-margin, scale-driven",
      "Services": "high-margin recurring"
    },
    "capital_intensity": {
      "iPhone": "high",
      "Services": "low"
    },
    "cyclicality": {
      "iPhone": "medium",
      "Services": "low"
    }
  },
  "value_driver_map": [
    {
      "driver": "AI-enabled upgrade cycle",
      "impacted_segments": ["iPhone"],
      "direction": "upside",
      "horizon": "6-12m",
      "evidence": "on-device feature expansion supports ASP and volume"
    },
    {
      "driver": "App Store regulatory pressure",
      "impacted_segments": ["Services"],
      "direction": "downside",
      "horizon": "12-24m",
      "evidence": "potential take-rate compression in key regions"
    }
  ]
}
```""",
        tool_calls=[],
    )
    llm = DummyLLM(result)
    monkeypatch.setattr(
        "tradingagents.agents.analysts.segment_analyst.ChatPromptTemplate.from_messages",
        lambda _messages: DummyPrompt(result),
    )

    node = create_segment_analyst(llm)
    output = node(
        {
            "trade_date": "2026-03-24",
            "company_of_interest": "AAPL",
            "messages": ["analyze segment exposure"],
        }
    )

    assert llm.bound_tool_names == [
        "get_segment_fundamentals",
        "get_segment_income_statement",
        "get_segment_news",
    ]
    assert output["segment_report"] == result.content
    assert output["segment_data"] == {
        "ticker": "AAPL",
        "analysis_date": "2026-03-24",
        "business_unit_decomposition": [
            {
                "segment": "iPhone",
                "revenue_share_pct": 52,
                "growth_trend": "stable",
                "strategic_role": "core hardware platform",
            },
            {
                "segment": "Services",
                "revenue_share_pct": 23,
                "growth_trend": "expanding",
                "strategic_role": "high-margin recurring engine",
            },
        ],
        "segment_economics": {
            "margin_profile": {
                "iPhone": "mid-margin, scale-driven",
                "Services": "high-margin recurring",
            },
            "capital_intensity": {
                "iPhone": "high",
                "Services": "low",
            },
            "cyclicality": {
                "iPhone": "medium",
                "Services": "low",
            },
        },
        "value_driver_map": [
            {
                "driver": "AI-enabled upgrade cycle",
                "impacted_segments": ["iPhone"],
                "direction": "upside",
                "horizon": "6-12m",
                "evidence": "on-device feature expansion supports ASP and volume",
            },
            {
                "driver": "App Store regulatory pressure",
                "impacted_segments": ["Services"],
                "direction": "downside",
                "horizon": "12-24m",
                "evidence": "potential take-rate compression in key regions",
            },
        ],
    }
    assert output["messages"] == [result]


def test_extract_segment_payload_tolerates_common_model_json_variants():
    from tradingagents.agents.analysts.segment_analyst import _extract_segment_payload

    expected = {
        "business_unit_decomposition": [{"segment": "Services"}],
        "segment_economics": {"margin_profile": {"Services": "high"}},
        "value_driver_map": [{"driver": "pricing"}],
    }

    uppercase_fence = """
```JSON
{"business_unit_decomposition":[{"segment":"Services"}],"segment_economics":{"margin_profile":{"Services":"high"}},"value_driver_map":[{"driver":"pricing"}]}
```
"""
    plain_fence = """
```
{"business_unit_decomposition":[{"segment":"Services"}],"segment_economics":{"margin_profile":{"Services":"high"}},"value_driver_map":[{"driver":"pricing"}]}
```
"""
    raw_json = """
Narrative intro before payload.
{"business_unit_decomposition":[{"segment":"Services"}],"segment_economics":{"margin_profile":{"Services":"high"}},"value_driver_map":[{"driver":"pricing"}]}
Tail note after payload.
"""

    assert _extract_segment_payload(uppercase_fence) == expected
    assert _extract_segment_payload(plain_fence) == expected
    assert _extract_segment_payload(raw_json) == expected


def test_propagator_initial_state_seeds_segment_defaults():
    from tradingagents.graph.propagation import Propagator

    state = Propagator().create_initial_state("AAPL", "2026-03-24")

    assert state["segment_report"] == ""
    assert state["segment_data"] == {
        "ticker": "",
        "analysis_date": "",
        "business_unit_decomposition": [],
        "segment_economics": {},
        "value_driver_map": [],
    }
