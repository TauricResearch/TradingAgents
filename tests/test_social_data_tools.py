from datetime import date
from unittest.mock import Mock, patch

from tradingagents.agents.analysts.social_media_analyst import create_social_media_analyst
from tradingagents.graph.setup import GraphSetup
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.agents.utils.social_data_tools import (
    get_social_sentiment,
    has_social_sentiment_support,
)


class FakePrompt:
    def __init__(self):
        self.partials = {}

    def partial(self, **kwargs):
        self.partials.update(kwargs)
        return self

    def __or__(self, bound_llm):
        bound_llm.prompt_partials = dict(self.partials)
        return bound_llm


class FakeBoundLLM:
    def __init__(self, tools):
        self.tools = tools
        self.prompt_partials = {}

    def invoke(self, _messages):
        return type("Response", (), {"tool_calls": [], "content": "sentiment report"})()


class FakeLLM:
    def __init__(self):
        self.bound_tools = []
        self.bound = None

    def bind_tools(self, tools):
        self.bound_tools = tools
        self.bound = FakeBoundLLM(tools)
        return self.bound


class DummyToolNode:
    def __init__(self, tools):
        self.tools = tools


class DummyStateGraph:
    def __init__(self, _state_type):
        self.nodes = {}

    def add_node(self, name, node):
        self.nodes[name] = node

    def add_edge(self, *_args, **_kwargs):
        return None

    def add_conditional_edges(self, *_args, **_kwargs):
        return None

    def compile(self):
        return {"nodes": self.nodes}


def test_support_flag_requires_api_key():
    with patch.dict("os.environ", {}, clear=True):
        assert has_social_sentiment_support() is False

    with patch.dict("os.environ", {"ADANOS_API_KEY": "sk_test"}, clear=True):
        assert has_social_sentiment_support() is True


@patch("tradingagents.agents.analysts.social_media_analyst.ChatPromptTemplate.from_messages")
def test_social_analyst_hides_sentiment_tool_without_api_key(mock_from_messages):
    llm = FakeLLM()
    mock_from_messages.return_value = FakePrompt()

    with patch.dict("os.environ", {}, clear=True):
        analyst = create_social_media_analyst(llm)
        analyst(
            {
                "trade_date": "2026-03-24",
                "company_of_interest": "TSLA",
                "messages": [],
            }
        )

    assert [tool.name for tool in llm.bound_tools] == ["get_news"]
    assert "get_social_sentiment(" not in llm.bound.prompt_partials["system_message"]


@patch("tradingagents.agents.analysts.social_media_analyst.ChatPromptTemplate.from_messages")
def test_social_analyst_exposes_sentiment_tool_with_api_key(mock_from_messages):
    llm = FakeLLM()
    mock_from_messages.return_value = FakePrompt()

    with patch.dict("os.environ", {"ADANOS_API_KEY": "sk_test"}, clear=True):
        analyst = create_social_media_analyst(llm)
        analyst(
            {
                "trade_date": "2026-03-24",
                "company_of_interest": "TSLA",
                "messages": [],
            }
        )

    assert [tool.name for tool in llm.bound_tools] == [
        "get_social_sentiment",
        "get_news",
    ]
    assert "get_social_sentiment(" in llm.bound.prompt_partials["system_message"]


@patch("tradingagents.agents.analysts.social_media_analyst.ChatPromptTemplate.from_messages")
def test_social_analyst_honors_explicit_support_snapshot(mock_from_messages):
    llm = FakeLLM()
    mock_from_messages.return_value = FakePrompt()

    with patch.dict("os.environ", {}, clear=True):
        analyst = create_social_media_analyst(llm, social_sentiment_available=True)
        analyst(
            {
                "trade_date": "2026-03-24",
                "company_of_interest": "TSLA",
                "messages": [],
            }
        )

    assert [tool.name for tool in llm.bound_tools] == [
        "get_social_sentiment",
        "get_news",
    ]
    assert "get_social_sentiment(" in llm.bound.prompt_partials["system_message"]


def test_social_tool_node_hides_sentiment_tool_without_api_key(monkeypatch):
    monkeypatch.setattr("tradingagents.graph.trading_graph.ToolNode", DummyToolNode)

    graph = object.__new__(TradingAgentsGraph)
    graph.social_sentiment_available = False
    tool_nodes = graph._create_tool_nodes()

    assert [tool.name for tool in tool_nodes["social"].tools] == ["get_news"]


def test_social_tool_node_exposes_sentiment_tool_with_api_key(monkeypatch):
    monkeypatch.setattr("tradingagents.graph.trading_graph.ToolNode", DummyToolNode)

    graph = object.__new__(TradingAgentsGraph)
    graph.social_sentiment_available = True
    tool_nodes = graph._create_tool_nodes()

    assert [tool.name for tool in tool_nodes["social"].tools] == [
        "get_social_sentiment",
        "get_news",
    ]


def test_graph_setup_passes_shared_social_availability_to_social_analyst(monkeypatch):
    captured = {}

    monkeypatch.setattr("tradingagents.graph.setup.StateGraph", DummyStateGraph)
    monkeypatch.setattr("tradingagents.graph.setup.create_msg_delete", lambda: "delete")

    def simple_factory(name):
        def factory(*_args, **_kwargs):
            return name

        return factory

    def social_factory(llm, social_sentiment_available=None):
        captured["llm"] = llm
        captured["social_sentiment_available"] = social_sentiment_available
        return "Social Analyst"

    monkeypatch.setattr(
        "tradingagents.graph.setup.create_social_media_analyst",
        social_factory,
    )
    monkeypatch.setattr(
        "tradingagents.graph.setup.create_market_analyst",
        simple_factory("Market Analyst"),
    )
    monkeypatch.setattr(
        "tradingagents.graph.setup.create_news_analyst",
        simple_factory("News Analyst"),
    )
    monkeypatch.setattr(
        "tradingagents.graph.setup.create_fundamentals_analyst",
        simple_factory("Fundamentals Analyst"),
    )
    monkeypatch.setattr(
        "tradingagents.graph.setup.create_macro_analyst",
        simple_factory("Macro Analyst"),
    )
    monkeypatch.setattr(
        "tradingagents.graph.setup.create_bull_researcher",
        simple_factory("Bull Researcher"),
    )
    monkeypatch.setattr(
        "tradingagents.graph.setup.create_bear_researcher",
        simple_factory("Bear Researcher"),
    )
    monkeypatch.setattr(
        "tradingagents.graph.setup.create_research_manager",
        simple_factory("Research Manager"),
    )
    monkeypatch.setattr(
        "tradingagents.graph.setup.create_trader",
        simple_factory("Trader"),
    )
    monkeypatch.setattr(
        "tradingagents.graph.setup.create_aggressive_debator",
        simple_factory("Aggressive Analyst"),
    )
    monkeypatch.setattr(
        "tradingagents.graph.setup.create_neutral_debator",
        simple_factory("Neutral Analyst"),
    )
    monkeypatch.setattr(
        "tradingagents.graph.setup.create_conservative_debator",
        simple_factory("Conservative Analyst"),
    )
    monkeypatch.setattr(
        "tradingagents.graph.setup.create_portfolio_manager",
        simple_factory("Portfolio Manager"),
    )

    class PartialConditionalLogic:
        def should_continue_social(self, _state):
            return "Msg Clear Social"

        def should_continue_debate(self, _state):
            return "Research Manager"

        def should_continue_risk_analysis(self, _state):
            return "Portfolio Manager"

    setup = GraphSetup(
        quick_thinking_llm="quick-llm",
        deep_thinking_llm="deep-llm",
        tool_nodes={"social": "social-tools"},
        bull_memory=object(),
        bear_memory=object(),
        trader_memory=object(),
        invest_judge_memory=object(),
        portfolio_manager_memory=object(),
        conditional_logic=PartialConditionalLogic(),
        social_sentiment_available=True,
    )

    graph = setup.setup_graph(selected_analysts=["social"])

    assert captured == {
        "llm": "quick-llm",
        "social_sentiment_available": True,
    }
    assert graph["nodes"]["tools_social"] == "social-tools"


@patch("tradingagents.agents.utils.social_data_tools.requests.get")
def test_historical_trade_dates_do_not_hit_network(mock_get):
    with patch.dict("os.environ", {"ADANOS_API_KEY": "sk_test"}, clear=True):
        result = get_social_sentiment.invoke(
            {"ticker": "TSLA", "curr_date": "2024-01-15", "look_back_days": 7}
        )

    assert "historical trade date" in result
    mock_get.assert_not_called()


@patch("tradingagents.agents.utils.social_data_tools.requests.get")
def test_recent_weekend_trade_dates_still_hit_live_window(mock_get):
    empty_response = Mock()
    empty_response.raise_for_status.return_value = None
    empty_response.json.return_value = {"stocks": []}
    mock_get.return_value = empty_response

    with patch.dict("os.environ", {"ADANOS_API_KEY": "sk_test"}, clear=True):
        with patch("tradingagents.agents.utils.social_data_tools.date") as mock_date:
            mock_date.today.return_value = date(2026, 3, 23)
            result = get_social_sentiment.invoke(
                {"ticker": "TSLA", "curr_date": "2026-03-20", "look_back_days": 7}
            )

    assert "historical trade date" not in result
    assert "## Social sentiment for TSLA" in result
    assert mock_get.call_count == 3


@patch("tradingagents.agents.utils.social_data_tools.requests.get")
def test_formats_cross_source_snapshot(mock_get):
    reddit_response = Mock()
    reddit_response.raise_for_status.return_value = None
    reddit_response.json.return_value = {
        "stocks": [
            {
                "ticker": "TSLA",
                "mentions": 647,
                "buzz_score": 81.2,
                "bullish_pct": 46,
                "trend": "rising",
                "subreddit_count": 23,
                "total_upvotes": 4120,
            }
        ]
    }

    x_response = Mock()
    x_response.raise_for_status.return_value = None
    x_response.json.return_value = {
        "stocks": [
            {
                "ticker": "TSLA",
                "mentions": 2650,
                "buzz_score": 86.4,
                "bullish_pct": 58,
                "trend": "falling",
                "unique_tweets": 392,
                "total_upvotes": 95000,
            }
        ]
    }

    polymarket_response = Mock()
    polymarket_response.raise_for_status.return_value = None
    polymarket_response.json.return_value = {
        "stocks": [
            {
                "ticker": "TSLA",
                "trade_count": 3731,
                "market_count": 71,
                "buzz_score": 55.7,
                "bullish_pct": 72,
                "trend": "stable",
                "total_liquidity": 8400000,
            }
        ]
    }

    mock_get.side_effect = [reddit_response, x_response, polymarket_response]

    with patch.dict("os.environ", {"ADANOS_API_KEY": "sk_test"}, clear=True):
        with patch("tradingagents.agents.utils.social_data_tools.date") as mock_date:
            mock_date.today.return_value = date(2026, 3, 19)
            result = get_social_sentiment.invoke(
                {"ticker": "TSLA", "curr_date": "2026-03-19", "look_back_days": 7}
            )

    assert "## Social sentiment for TSLA" in result
    assert "Average buzz: 74.4/100" in result
    assert "Average bullish: 58.7%" in result
    assert "### Reddit" in result
    assert "### X/Twitter" in result
    assert "### Polymarket" in result
