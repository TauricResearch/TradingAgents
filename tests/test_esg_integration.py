from datetime import date
from unittest.mock import Mock, patch

import pandas as pd
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda
from langgraph.prebuilt import ToolNode
from cli.main import ANALYST_AGENT_NAMES, ANALYST_ORDER, ANALYST_REPORT_MAP
from cli.models import AnalystType
from cli.utils import ANALYST_ORDER as CLI_ANALYST_ORDER
from tradingagents.agents.analysts.esg_analyst import create_esg_analyst
from tradingagents.agents.utils.esg_data_tools import get_esg_news, get_esg_scores
from tradingagents.graph.conditional_logic import ConditionalLogic
from tradingagents.graph.propagation import Propagator
from tradingagents.graph.setup import ANALYST_NODE_NAMES, GraphSetup


def test_esg_is_selectable_in_cli():
    assert AnalystType.ESG.value == "esg"
    assert ("ESG Analyst", AnalystType.ESG) in CLI_ANALYST_ORDER
    assert "esg" in ANALYST_ORDER
    assert ANALYST_AGENT_NAMES["esg"] == "ESG Analyst"
    assert ANALYST_REPORT_MAP["esg"] == "esg_report"


def test_esg_initial_state_and_graph_names_are_consistent():
    init_state = Propagator().create_initial_state("AAPL", "2025-01-01")
    assert init_state["esg_report"] == ""
    assert ANALYST_NODE_NAMES["esg"] == "ESG Analyst"



class _FakeLLM:
    def invoke(self, prompt):
        return AIMessage(content="fake response")

    def with_structured_output(self, schema):
        raise NotImplementedError("structured output not needed for graph compile")


def test_esg_conditional_logic_and_graph_compile():
    logic = ConditionalLogic()
    tool_state = {"messages": [AIMessage(content="", tool_calls=[{"name": "get_esg_scores", "args": {"ticker": "AAPL", "curr_date": "2025-01-01"}, "id": "call-1"}])]}
    final_state = {"messages": [AIMessage(content="done", tool_calls=[])]}

    assert logic.should_continue_esg(tool_state) == "tools_esg"
    assert logic.should_continue_esg(final_state) == "Msg Clear ESG"

    llm = _FakeLLM()
    setup = GraphSetup(
        quick_thinking_llm=llm,
        deep_thinking_llm=llm,
        tool_nodes={"esg": ToolNode([get_esg_scores, get_esg_news])},
        conditional_logic=logic,
    )
    setup.setup_graph(["esg"]).compile()


class _PromptCaptureLLM:
    def __init__(self):
        self.system_content = None

    def bind_tools(self, tools):
        def capture(prompt_value):
            self.system_content = prompt_value.to_messages()[0].content
            return AIMessage(content="ESG report", tool_calls=[])

        return RunnableLambda(capture)


def test_esg_analyst_system_message_is_rendered_as_string():
    llm = _PromptCaptureLLM()
    node = create_esg_analyst(llm)

    result = node(
        {
            "messages": [("human", "AAPL")],
            "company_of_interest": "AAPL",
            "trade_date": "2025-01-01",
        }
    )

    assert result["esg_report"] == "ESG report"
    assert "You are an ESG" in llm.system_content
    assert "('You are an ESG" not in llm.system_content
    assert "',)" not in llm.system_content

def test_esg_news_parses_nested_yfinance_articles():
    nested_article = {
        "content": {
            "title": "Company expands carbon reduction program",
            "summary": "The new sustainability program targets emissions and climate risk.",
            "provider": {"displayName": "Example News"},
            "canonicalUrl": {"url": "https://example.com/esg"},
            "pubDate": "2025-01-01T12:00:00Z",
        }
    }
    ticker = Mock()
    ticker.get_news.return_value = [nested_article]

    with patch("tradingagents.agents.utils.esg_data_tools.yf.Ticker", return_value=ticker), patch(
        "tradingagents.agents.utils.esg_data_tools.yf_retry", side_effect=lambda call: call()
    ):
        result = get_esg_news.invoke({"ticker": "AAPL", "curr_date": "2025-01-01"})

    assert "Company expands carbon reduction program" in result
    assert "Example News" in result
    assert "https://example.com/esg" in result


def test_esg_news_filters_articles_after_analysis_date():
    past_article = {
        "content": {
            "title": "Company publishes sustainability plan",
            "summary": "A governance and emissions update.",
            "provider": {"displayName": "Past News"},
            "canonicalUrl": {"url": "https://example.com/past"},
            "pubDate": "2025-01-01T12:00:00Z",
        }
    }
    future_article = {
        "content": {
            "title": "Company faces climate investigation",
            "summary": "A future controversy that should not leak into the run.",
            "provider": {"displayName": "Future News"},
            "canonicalUrl": {"url": "https://example.com/future"},
            "pubDate": "2025-01-03T12:00:00Z",
        }
    }
    ticker = Mock()
    ticker.get_news.return_value = [past_article, future_article]

    with patch("tradingagents.agents.utils.esg_data_tools.yf.Ticker", return_value=ticker), patch(
        "tradingagents.agents.utils.esg_data_tools.yf_retry", side_effect=lambda call: call()
    ):
        result = get_esg_news.invoke({"ticker": "AAPL", "curr_date": "2025-01-01"})

    assert "Company publishes sustainability plan" in result
    assert "Company faces climate investigation" not in result
    assert "Filtered out 1 future-dated" in result


def test_esg_scores_skip_current_scores_for_historical_dates():
    with patch("tradingagents.agents.utils.esg_data_tools.yf.Ticker") as ticker_cls:
        result = get_esg_scores.invoke({"ticker": "AAPL", "curr_date": "2000-01-01"})

    ticker_cls.assert_not_called()
    assert "Point-in-time ESG scores are not available" in result
    assert "look-ahead bias" in result


def test_esg_scores_extracts_scalar_values_from_dataframe_rows():
    sustainability = pd.DataFrame(
        {"Value": [18.2, 4.3], "Source": ["Sustainalytics", "Sustainalytics"]},
        index=["totalEsg", "environmentScore"],
    )
    ticker = Mock()
    ticker.sustainability = sustainability

    with patch("tradingagents.agents.utils.esg_data_tools.date") as date_cls, patch(
        "tradingagents.agents.utils.esg_data_tools.yf.Ticker", return_value=ticker
    ):
        date_cls.today.return_value = date(2025, 1, 1)
        result = get_esg_scores.invoke({"ticker": "AAPL", "curr_date": "2025-01-01"})

    assert "Total ESG Score: 18.2" in result
    assert "Environment Score: 4.3" in result
    assert "dtype:" not in result