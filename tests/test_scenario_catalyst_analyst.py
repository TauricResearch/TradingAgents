import json

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


def test_scenario_tools_route_to_vendor(monkeypatch):
    import tradingagents.dataflows.interface as interface
    from tradingagents.agents.utils.scenario_tools import (
        get_catalyst_calendar,
        get_scenario_fundamentals,
        get_scenario_news,
    )

    calls = []

    def fake_route_to_vendor(method, *args, **kwargs):
        calls.append((method, args, kwargs))
        return f"{method}-result"

    monkeypatch.setattr(interface, "route_to_vendor", fake_route_to_vendor)

    assert (
        get_scenario_fundamentals.invoke({"ticker": "AAPL", "curr_date": "2026-03-24"})
        == "get_fundamentals-result"
    )
    assert (
        get_scenario_news.invoke(
            {"query": "AAPL product launch catalyst", "start_date": "2026-03-01", "end_date": "2026-03-24"}
        )
        == "get_news-result"
    )
    assert (
        get_catalyst_calendar.invoke({"curr_date": "2026-03-24"})
        == "get_fed_calendar-result"
    )
    assert calls == [
        (
            "get_fundamentals",
            (),
            {"ticker": "AAPL", "curr_date": "2026-03-24"},
        ),
        (
            "get_news",
            (),
            {
                "query": "AAPL product launch catalyst",
                "start_date": "2026-03-01",
                "end_date": "2026-03-24",
            },
        ),
        ("get_fed_calendar", (), {"curr_date": "2026-03-24"}),
    ]


def test_graph_setup_wires_scenario_catalyst_analyst_and_tools(monkeypatch):
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
        "tradingagents.graph.setup.create_scenario_catalyst_analyst",
        make_factory("Scenario Analyst"),
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

        def should_continue_scenario(self, _state):
            return "Msg Clear Scenario"

        def should_continue_debate(self, _state):
            return "Research Manager"

        def should_continue_risk_analysis(self, _state):
            return "Portfolio Manager"

    setup = GraphSetup(
        quick_thinking_llm="quick-llm",
        deep_thinking_llm="deep-llm",
        tool_nodes={"market": "market-tools", "scenario": "scenario-tools"},
        bull_memory=object(),
        bear_memory=object(),
        trader_memory=object(),
        invest_judge_memory=object(),
        portfolio_manager_memory=object(),
        conditional_logic=PartialConditionalLogic(),
        role_llms={"scenario": "scenario-llm"},
    )

    graph = setup.setup_graph(selected_analysts=["market", "scenario"])

    assert recorded_llms["Scenario Analyst"] == "scenario-llm"
    assert graph["nodes"]["Scenario Analyst"] == "Scenario Analyst"
    assert graph["nodes"]["tools_scenario"] == "scenario-tools"
    assert "Scenario Analyst" in graph["conditional_edges"]


def test_trading_graph_creates_scenario_tool_node(monkeypatch):
    monkeypatch.setattr("tradingagents.graph.trading_graph.ToolNode", DummyToolNode)

    graph = TradingAgentsGraph.__new__(TradingAgentsGraph)
    tool_nodes = TradingAgentsGraph._create_tool_nodes(graph)

    assert [tool.name for tool in tool_nodes["scenario"].tools] == [
        "get_scenario_fundamentals",
        "get_scenario_news",
        "get_catalyst_calendar",
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


def test_scenario_catalyst_analyst_returns_structured_data(monkeypatch):
    from tradingagents.agents.analysts.scenario_catalyst_analyst import (
        create_scenario_catalyst_analyst,
    )

    result = DummyResult(
        content="""## Scenario and Catalyst Summary

Bull case is an AI-led re-rating with operating leverage, base case is steady
execution with modest multiple expansion, and bear case is demand rollover.

```json
{
  "scenario_map": [
    {
      "name": "bull",
      "probability_pct": 30,
      "thesis": "AI-driven demand acceleration",
      "valuation_implication": "multiple expansion toward upper historical range",
      "signposts": ["order lead-times extend", "gross margin beats guidance"]
    },
    {
      "name": "base",
      "probability_pct": 50,
      "thesis": "stable demand and disciplined opex",
      "valuation_implication": "range-bound multiple with EPS carry",
      "signposts": ["in-line guidance", "services growth steady"]
    },
    {
      "name": "bear",
      "probability_pct": 20,
      "thesis": "weaker upgrade cycle and pricing pressure",
      "valuation_implication": "derating to cycle-low valuation band",
      "signposts": ["inventory builds", "discounting rises"]
    }
  ],
  "dated_catalyst_map": [
    {
      "catalyst": "FOMC rate decision",
      "date_or_window": "2026-05-06",
      "related_scenarios": ["bull", "base", "bear"],
      "expected_impact": "changes discount-rate pressure on valuation",
      "confidence": "medium"
    }
  ],
  "invalidation_triggers": [
    {
      "trigger": "two consecutive quarters of revenue miss versus guidance midpoint",
      "affected_scenarios": ["bull", "base"],
      "severity": "high",
      "evidence_to_watch": "quarterly filings and management commentary"
    }
  ]
}
```""",
        tool_calls=[],
    )
    llm = DummyLLM(result)
    monkeypatch.setattr(
        "tradingagents.agents.analysts.scenario_catalyst_analyst.ChatPromptTemplate.from_messages",
        lambda _messages: DummyPrompt(result),
    )

    node = create_scenario_catalyst_analyst(llm)
    output = node(
        {
            "trade_date": "2026-03-24",
            "company_of_interest": "AAPL",
            "messages": ["analyze scenario tree"],
        }
    )

    assert llm.bound_tool_names == [
        "get_scenario_fundamentals",
        "get_scenario_news",
        "get_catalyst_calendar",
    ]
    assert output["scenario_catalyst_report"] == result.content
    assert output["scenario_catalyst_data"] == {
        "ticker": "AAPL",
        "analysis_date": "2026-03-24",
        "scenario_map": [
            {
                "name": "bull",
                "probability_pct": 30,
                "thesis": "AI-driven demand acceleration",
                "valuation_implication": "multiple expansion toward upper historical range",
                "signposts": [
                    "order lead-times extend",
                    "gross margin beats guidance",
                ],
            },
            {
                "name": "base",
                "probability_pct": 50,
                "thesis": "stable demand and disciplined opex",
                "valuation_implication": "range-bound multiple with EPS carry",
                "signposts": ["in-line guidance", "services growth steady"],
            },
            {
                "name": "bear",
                "probability_pct": 20,
                "thesis": "weaker upgrade cycle and pricing pressure",
                "valuation_implication": "derating to cycle-low valuation band",
                "signposts": ["inventory builds", "discounting rises"],
            },
        ],
        "dated_catalyst_map": [
            {
                "catalyst": "FOMC rate decision",
                "date_or_window": "2026-05-06",
                "related_scenarios": ["bull", "base", "bear"],
                "expected_impact": "changes discount-rate pressure on valuation",
                "confidence": "medium",
            }
        ],
        "invalidation_triggers": [
            {
                "trigger": "two consecutive quarters of revenue miss versus guidance midpoint",
                "affected_scenarios": ["bull", "base"],
                "severity": "high",
                "evidence_to_watch": "quarterly filings and management commentary",
            }
        ],
    }
    assert output["messages"] == [result]


def test_extract_scenario_payload_tolerates_common_model_json_variants():
    from tradingagents.agents.analysts.scenario_catalyst_analyst import (
        _extract_scenario_catalyst_payload,
    )

    expected = {
        "scenario_map": [{"name": "base", "probability_pct": 60}],
        "dated_catalyst_map": [{"catalyst": "earnings", "date_or_window": "Q2"}],
        "invalidation_triggers": [{"trigger": "demand miss"}],
    }

    uppercase_fence = """
```JSON
{"scenario_map":[{"name":"base","probability_pct":60}],"dated_catalyst_map":[{"catalyst":"earnings","date_or_window":"Q2"}],"invalidation_triggers":[{"trigger":"demand miss"}]}
```
"""
    plain_fence = """
```
{"scenario_map":[{"name":"base","probability_pct":60}],"dated_catalyst_map":[{"catalyst":"earnings","date_or_window":"Q2"}],"invalidation_triggers":[{"trigger":"demand miss"}]}
```
"""
    raw_json = """
Narrative intro before payload.
{"scenario_map":[{"name":"base","probability_pct":60}],"dated_catalyst_map":[{"catalyst":"earnings","date_or_window":"Q2"}],"invalidation_triggers":[{"trigger":"demand miss"}]}
Tail note after payload.
"""

    assert _extract_scenario_catalyst_payload(uppercase_fence) == expected
    assert _extract_scenario_catalyst_payload(plain_fence) == expected
    assert _extract_scenario_catalyst_payload(raw_json) == expected


def test_propagator_initial_state_seeds_scenario_defaults():
    from tradingagents.graph.propagation import Propagator

    state = Propagator().create_initial_state("AAPL", "2026-03-24")

    assert state["scenario_catalyst_report"] == ""
    assert state["scenario_catalyst_data"] == {
        "ticker": "",
        "analysis_date": "",
        "scenario_map": [],
        "dated_catalyst_map": [],
        "invalidation_triggers": [],
    }


def test_log_state_persists_scenario_catalyst_report_and_data(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    graph = TradingAgentsGraph.__new__(TradingAgentsGraph)
    graph.ticker = "AAPL"
    graph.log_states_dict = {}

    final_state = {
        "company_of_interest": "Apple",
        "trade_date": "2026-03-24",
        "market_report": "market",
        "sentiment_report": "sentiment",
        "news_report": "news",
        "fundamentals_report": "fundamentals",
        "segment_report": "segment report",
        "segment_data": {"ticker": "AAPL"},
        "macro_report": "macro report",
        "scenario_catalyst_report": "scenario report",
        "scenario_catalyst_data": {
            "ticker": "AAPL",
            "analysis_date": "2026-03-24",
            "scenario_map": [{"name": "base", "probability_pct": 60}],
            "dated_catalyst_map": [{"catalyst": "earnings", "date_or_window": "Q2"}],
            "invalidation_triggers": [{"trigger": "demand miss"}],
        },
        "investment_debate_state": {
            "bull_history": "bull",
            "bear_history": "bear",
            "history": "debate history",
            "current_response": "current",
            "judge_decision": "judge",
        },
        "trader_investment_plan": "trader plan",
        "risk_debate_state": {
            "aggressive_history": "agg",
            "conservative_history": "cons",
            "neutral_history": "neutral",
            "history": "risk history",
            "judge_decision": "risk judge",
        },
        "investment_plan": "investment plan",
        "final_trade_decision": "buy",
    }

    graph._log_state("2026-03-24", final_state)

    output_path = (
        tmp_path
        / "eval_results"
        / "AAPL"
        / "TradingAgentsStrategy_logs"
        / "full_states_log_2026-03-24.json"
    )
    payload = json.loads(output_path.read_text())
    logged = payload["2026-03-24"]

    assert logged["scenario_catalyst_report"] == "scenario report"
    assert logged["scenario_catalyst_data"] == final_state["scenario_catalyst_data"]
