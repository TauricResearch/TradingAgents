from unittest.mock import MagicMock
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

def test_fundamentals_analyst_tool_loop(mock_state, mock_llm_with_tool_call):
    node = create_fundamentals_analyst(mock_llm_with_tool_call)
    result = node(mock_state)
    assert "This is the final report after running the tool." in result["fundamentals_report"]

def test_market_analyst_tool_loop(mock_state, mock_llm_with_tool_call):
    node = create_market_analyst(mock_llm_with_tool_call)
    result = node(mock_state)
    assert "This is the final report after running the tool." in result["market_report"]

def test_social_media_analyst_tool_loop(mock_state, mock_llm_with_tool_call):
    node = create_social_media_analyst(mock_llm_with_tool_call)
    result = node(mock_state)
    assert "This is the final report after running the tool." in result["sentiment_report"]

def test_news_analyst_tool_loop(mock_state, mock_llm_with_tool_call):
    node = create_news_analyst(mock_llm_with_tool_call)
    result = node(mock_state)
    assert "This is the final report after running the tool." in result["news_report"]
