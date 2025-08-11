#!/usr/bin/env python
"""Test the actual market analyst test."""

import pytest
from tests.conftest import MockResult

# Import test fixtures
pytest_plugins = ["tests.conftest"]

def test_debug():
    from tests.conftest import mock_llm, mock_toolkit, sample_agent_state
    from tradingagents.agents.analysts.market_analyst import create_market_analyst
    
    # Create fixtures
    llm = mock_llm()
    toolkit = mock_toolkit()
    state = sample_agent_state()
    
    # Setup like the test does
    toolkit.config = {"online_tools": False}
    mock_result = MockResult(content="Market analysis complete", tool_calls=[])
    llm._chain_mock.invoke.return_value = mock_result
    
    print(f"llm: {llm}")
    print(f"llm._chain_mock: {llm._chain_mock}")
    print(f"llm._chain_mock.invoke: {llm._chain_mock.invoke}")
    print(f"llm._chain_mock.invoke.return_value: {llm._chain_mock.invoke.return_value}")
    
    analyst_node = create_market_analyst(llm, toolkit)
    
    # Execute
    result = analyst_node(state)
    
    print(f"Result messages: {result['messages']}")
    print(f"Expected: {[mock_result]}")
    print(f"Are they equal? {result['messages'] == [mock_result]}")
    
if __name__ == "__main__":
    test_debug()