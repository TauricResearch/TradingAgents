#!/usr/bin/env python
"""Test the actual market analyst test."""

from unittest.mock import Mock
from tests.conftest import MockResult
from tradingagents.agents.analysts.market_analyst import create_market_analyst

# Recreate the mock_llm fixture logic
mock = Mock()
mock.model_name = "test-model"

# Create a default mock result with proper tool_calls
default_result = MockResult()

# Create a chain mock (what prompt | llm.bind_tools(tools) returns)
chain_mock = Mock()
chain_mock.invoke = Mock(return_value=default_result)

# Store the chain_mock on the mock_llm so tests can configure it
mock._chain_mock = chain_mock

# Mock the bind_tools to return a mock that handles piping
bound_tools_mock = Mock()

# Handle the pipe operation (prompt | llm.bind_tools(tools))
def handle_pipe(self, other):
    # Return the chain_mock that tests can configure
    print(f"handle_pipe called with self={self}, other={other}")
    print(f"Returning chain_mock: {chain_mock}")
    return chain_mock

bound_tools_mock.__ror__ = handle_pipe  # Right-side or (other | bound_tools_mock)
mock.bind_tools = Mock(return_value=bound_tools_mock)

# Create toolkit
toolkit = Mock()
toolkit.config = {"online_tools": False}

# Set up toolkit methods with proper name attributes
toolkit.get_YFin_data = Mock()
toolkit.get_YFin_data.name = "get_YFin_data"
toolkit.get_stockstats_indicators_report = Mock()
toolkit.get_stockstats_indicators_report.name = "get_stockstats_indicators_report"

# Setup like the test does
mock_result = MockResult(content="Market analysis complete", tool_calls=[])
mock._chain_mock.invoke.return_value = mock_result

# Create state
state = {
    "company_of_interest": "AAPL",
    "trade_date": "2024-05-10",
    "messages": [],
}

print(f"mock: {mock}")
print(f"mock._chain_mock: {mock._chain_mock}")
print(f"mock._chain_mock.invoke: {mock._chain_mock.invoke}")
print(f"mock._chain_mock.invoke.return_value: {mock._chain_mock.invoke.return_value}")

analyst_node = create_market_analyst(mock, toolkit)

# Execute
result = analyst_node(state)

print(f"Result messages: {result['messages']}")
print(f"Expected: {[mock_result]}")
print(f"First message: {result['messages'][0]}")
print(f"Are they equal? {result['messages'] == [mock_result]}")
print(f"First item equal? {result['messages'][0] == mock_result}")
print(f"Are they the same object? {result['messages'][0] is mock_result}")