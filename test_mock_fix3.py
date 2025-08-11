#!/usr/bin/env python
"""Debug script to test our mock setup."""

from unittest.mock import Mock
from tests.conftest import MockResult

# Recreate our fixture setup
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
    return chain_mock

bound_tools_mock.__ror__ = handle_pipe  # Right-side or (other | bound_tools_mock)
mock.bind_tools = Mock(return_value=bound_tools_mock)

# Now simulate what a test does
mock_result = MockResult(content="Test content", tool_calls=[])
mock._chain_mock.invoke.return_value = mock_result

# Simulate what the production code does
prompt = Mock()
tools = []

# This is what happens in the actual code:
# chain = prompt | llm.bind_tools(tools)
print(f"bind_tools is called with tools: {tools}")
bound_result = mock.bind_tools(tools)
print(f"bind_tools returns: {bound_result}")
print(f"Has __ror__? {hasattr(bound_result, '__ror__')}")

chain = prompt | bound_result
print(f"chain is: {chain}")
print(f"chain_mock is: {chain_mock}")
print(f"Are they the same? {chain is chain_mock}")

result = chain.invoke([])
print(f"Result: {result}")
print(f"Expected: {mock_result}")
print(f"Are they the same? {result is mock_result}")