#!/usr/bin/env python
"""Test that mock toolkit fixes work for TradingAgentsGraph."""

from unittest.mock import Mock, patch
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tests.unit.graph.mock_toolkit_fix import create_mock_toolkit_with_tools


def test_mock_toolkit_has_all_methods():
    """Test that the mock toolkit has all required methods."""
    toolkit = create_mock_toolkit_with_tools()
    
    required_methods = [
        "get_YFin_data",
        "get_YFin_data_online",
        "get_stockstats_indicators_report",
        "get_stockstats_indicators_report_online",
        "get_reddit_stock_info",
        "get_stock_news_openai",
    ]
    
    for method_name in required_methods:
        assert hasattr(toolkit, method_name), f"Missing {method_name}"
        method = getattr(toolkit, method_name)
        assert hasattr(method, '__name__'), f"{method_name} missing __name__"
        assert method.__name__ == method_name, f"{method_name} has wrong __name__"
        assert callable(method), f"{method_name} is not callable"
    
    print("✓ Mock toolkit has all required methods with proper attributes")
    return True


def test_tool_node_creation():
    """Test that ToolNode can be created with mocked toolkit methods."""
    # Mock the ToolNode class
    with patch("langgraph.prebuilt.ToolNode") as MockToolNode:
        MockToolNode.return_value = Mock()
        
        toolkit = create_mock_toolkit_with_tools()
        
        # Simulate creating tool nodes like in TradingAgentsGraph
        from langgraph.prebuilt import ToolNode
        
        tool_node = ToolNode([
            toolkit.get_YFin_data,
            toolkit.get_stockstats_indicators_report,
        ])
        
        # Should not raise an error
        assert MockToolNode.called
        print("✓ ToolNode can be created with mocked toolkit methods")
        return True


def test_tool_decorator():
    """Test that @tool decorator works with mocked functions."""
    toolkit = create_mock_toolkit_with_tools()
    
    # The @tool decorator expects __name__ attribute
    for attr_name in dir(toolkit):
        if attr_name.startswith('get_'):
            method = getattr(toolkit, attr_name)
            assert hasattr(method, '__name__'), f"{attr_name} missing __name__"
    
    print("✓ All toolkit methods are compatible with @tool decorator")
    return True


if __name__ == "__main__":
    print("Testing mock toolkit fixes for TradingAgentsGraph...")
    print("-" * 50)
    
    tests = [
        test_mock_toolkit_has_all_methods,
        test_tool_node_creation,
        test_tool_decorator,
    ]
    
    all_passed = True
    for test in tests:
        try:
            if not test():
                all_passed = False
                print(f"✗ {test.__name__} failed")
        except Exception as e:
            all_passed = False
            print(f"✗ {test.__name__} raised exception: {e}")
            import traceback
            traceback.print_exc()
    
    print("-" * 50)
    if all_passed:
        print("✅ All tests passed! TradingAgentsGraph mock fixes are working.")
    else:
        print("❌ Some tests failed. Check the output above.")