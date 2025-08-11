#!/usr/bin/env python
"""Debug script to understand the mock chain behavior."""

from unittest.mock import Mock
from tests.conftest import MockResult

# Recreate the mock_llm setup
mock = Mock()
mock.model_name = "test-model"

# Create a default mock result with proper tool_calls
default_result = MockResult()

# Mock the bind_tools to return a mock that handles piping
bound_mock = Mock()
bound_mock.invoke = Mock(return_value=default_result)

# Handle the pipe operation (prompt | llm.bind_tools(tools))
def handle_pipe(self, other):
    # Return a mock that will use the bound_mock's invoke method
    pipe_result = Mock()
    pipe_result.invoke = bound_mock.invoke
    return pipe_result

bound_mock.__ror__ = handle_pipe
mock.bind_tools.return_value = bound_mock

# Now simulate what a test does
mock_result = MockResult(content="Test content", tool_calls=[])
mock.bind_tools.return_value.invoke.return_value = mock_result

# Simulate what the code does
prompt = Mock()  # Simulate a prompt
tools = []  # Simulate tools
chain = prompt | mock.bind_tools(tools)

# Invoke the chain
result = chain.invoke([])

print(f"Expected: {mock_result}")
print(f"Got: {result}")
print(f"Are they the same? {result is mock_result}")
print(f"bound_mock.invoke: {bound_mock.invoke}")
print(f"chain.invoke: {chain.invoke}")
print(f"Are invoke methods the same? {chain.invoke is bound_mock.invoke}")