#!/usr/bin/env python
"""Debug script to understand the mock chain behavior."""

from unittest.mock import Mock, patch
from tests.conftest import MockResult

# Let's create a test to see what happens
def test_mock():
    mock_llm = Mock()
    mock_llm.model_name = "test-model"
    
    # Create a mock result
    test_result = MockResult(content="Test content", tool_calls=[])
    
    # Create the chain mock (what prompt | llm.bind_tools(tools) returns)
    chain_mock = Mock()
    chain_mock.invoke = Mock(return_value=test_result)
    
    # Make bind_tools return a mock that when piped, returns our chain_mock
    bound_tools_mock = Mock()
    
    # This is the key: when something is piped to bound_tools_mock,
    # it should return our chain_mock
    def pipe_handler(self, other):
        return chain_mock
    
    bound_tools_mock.__ror__ = pipe_handler
    mock_llm.bind_tools = Mock(return_value=bound_tools_mock)
    
    # Now simulate what the production code does
    prompt = Mock()
    tools = []
    
    # This is what happens in the actual code
    chain = prompt | mock_llm.bind_tools(tools)
    result = chain.invoke([])
    
    print(f"Expected: {test_result}")
    print(f"Got: {result}")
    print(f"Are they the same? {result is test_result}")
    
test_mock()