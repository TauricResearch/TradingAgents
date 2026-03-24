from unittest.mock import MagicMock, patch
import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.runnables import Runnable
from tradingagents.agents.analysts.fundamentals_analyst import create_fundamentals_analyst
from tradingagents.agents.analysts.market_analyst import create_market_analyst
from tradingagents.agents.analysts.social_media_analyst import create_social_media_analyst
from tradingagents.agents.analysts.news_analyst import create_news_analyst


class MockRunnable(Runnable):
    def __init__(self, invoke_responses):
        self.invoke_responses = invoke_responses
        self.call_count = 0

    def invoke(self, input, config=None, **kwargs):
        response = self.invoke_responses[self.call_count]
        self.call_count += 1
        return response


class MockLLM(Runnable):
    def __init__(self, invoke_responses):
        self.runnable = MockRunnable(invoke_responses)
        self.tools_bound = None

    def invoke(self, input, config=None, **kwargs):
        return self.runnable.invoke(input, config=config, **kwargs)

    def bind_tools(self, tools):
        self.tools_bound = tools
        return self.runnable


@pytest.fixture
def mock_state():
    return {
        "messages": [HumanMessage(content="Analyze AAPL.")],
        "trade_date": "2024-05-15",
        "company_of_interest": "AAPL",
    }


@pytest.fixture
def mock_llm_with_tool_call():
    """LLM that makes one tool call then writes the final report (iterative loop)."""
    # 1. First call: The LLM decides to use a tool
    tool_call_msg = AIMessage(
        content="",
        tool_calls=[
            {"name": "mock_tool", "args": {"query": "test"}, "id": "call_123"}
        ]
    )
    # 2. Second call: The LLM receives the tool output and writes the report
    final_report_msg = AIMessage(
        content="This is the final report after running the tool."
    )
    return MockLLM([tool_call_msg, final_report_msg])


@pytest.fixture
def mock_llm_direct_report():
    """LLM that returns the final report directly (no tool calls — full pre-fetch path)."""
    final_report_msg = AIMessage(
        content="This is the final report after running the tool."
    )
    return MockLLM([final_report_msg])


def test_fundamentals_analyst_tool_loop(mock_state, mock_llm_with_tool_call):
    """Fundamentals analyst: pre-fetches 4 tools, runs iterative loop for raw statements."""
    node = create_fundamentals_analyst(mock_llm_with_tool_call)
    result = node(mock_state)
    assert "This is the final report after running the tool." in result["fundamentals_report"]


def test_market_analyst_tool_loop(mock_state, mock_llm_with_tool_call):
    """Market analyst: pre-fetches macro + stock data, keeps indicator selection iterative."""
    node = create_market_analyst(mock_llm_with_tool_call)
    result = node(mock_state)
    assert "This is the final report after running the tool." in result["market_report"]


def test_social_media_analyst_direct_invoke(mock_state, mock_llm_direct_report):
    """Social analyst: full pre-fetch, direct LLM invoke (no tool loop)."""
    node = create_social_media_analyst(mock_llm_direct_report)
    result = node(mock_state)
    assert "This is the final report after running the tool." in result["sentiment_report"]


def test_news_analyst_direct_invoke(mock_state, mock_llm_direct_report):
    """News analyst: full pre-fetch, direct LLM invoke (no tool loop)."""
    node = create_news_analyst(mock_llm_direct_report)
    result = node(mock_state)
    assert "This is the final report after running the tool." in result["news_report"]


def test_market_analyst_macro_regime_from_prefetch(mock_state, mock_llm_with_tool_call):
    """Market analyst populates macro_regime_report from pre-fetched data when available."""
    with patch(
        "tradingagents.agents.analysts.market_analyst.prefetch_tools_parallel",
        return_value={
            "Macro Regime Classification": "## Risk-On\nMarket is RISK-ON.",
            "Stock Price Data": "Date,Close\n2024-05-14,189.0",
        },
    ):
        node = create_market_analyst(mock_llm_with_tool_call)
        result = node(mock_state)
    assert result["macro_regime_report"] == "## Risk-On\nMarket is RISK-ON."


def test_social_media_analyst_no_bind_tools(mock_state, mock_llm_direct_report):
    """Social analyst must not call bind_tools since there are no tools."""
    node = create_social_media_analyst(mock_llm_direct_report)
    node(mock_state)
    # bind_tools should never have been called (no tools in the list)
    assert mock_llm_direct_report.tools_bound is None


def test_prefetched_context_injected_into_prompt(mock_state, mock_llm_with_tool_call):
    """Market analyst injects pre-fetched context into the prompt sent to the LLM."""
    captured_inputs = []

    class CapturingRunnable(Runnable):
        def invoke(self, input, config=None, **kwargs):
            captured_inputs.append(input)
            # Return final report directly to end the loop early
            return AIMessage(content="This is the final report after running the tool.")

    class CapturingLLM(Runnable):
        def invoke(self, input, config=None, **kwargs):
            captured_inputs.append(input)
            return AIMessage(content="This is the final report after running the tool.")

        def bind_tools(self, tools):
            return CapturingRunnable()

    with patch(
        "tradingagents.agents.analysts.market_analyst.prefetch_tools_parallel",
        return_value={
            "Macro Regime Classification": "**RISK-ON** regime detected.",
            "Stock Price Data": "Date,Close\n2024-05-14,189.0",
        },
    ):
        node = create_market_analyst(CapturingLLM())
        node(mock_state)

    # The prompt was captured; find the system message and verify injected context
    assert captured_inputs, "LLM was never called"
    # The input to the runnable is a list of messages; find the system message text
    messages = captured_inputs[0]
    full_text = " ".join(
        m.content if hasattr(m, "content") else str(m)
        for m in messages
    )
    assert "RISK-ON" in full_text
    assert "Pre-loaded Context" in full_text


def test_news_analyst_no_bind_tools(mock_state, mock_llm_direct_report):
    """News analyst must not call bind_tools since there are no tools."""
    node = create_news_analyst(mock_llm_direct_report)
    node(mock_state)
    assert mock_llm_direct_report.tools_bound is None
