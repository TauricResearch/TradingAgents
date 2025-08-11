#!/usr/bin/env python
"""Test script to verify mock fixes without full imports."""

from unittest.mock import Mock


def create_mock_toolkit():
    """Create a properly mocked toolkit."""
    toolkit = Mock()
    toolkit.config = {"online_tools": False}
    
    # Create proper mock functions with __name__ attributes
    def mock_get_YFin_data():
        return "Mock YFin data"
    
    def mock_get_stockstats_indicators_report():
        return "Mock stockstats report"
    
    # Wrap functions in Mock but preserve __name__
    toolkit.get_YFin_data = Mock(side_effect=mock_get_YFin_data)
    toolkit.get_YFin_data.name = "get_YFin_data"
    toolkit.get_YFin_data.__name__ = "get_YFin_data"
    
    toolkit.get_stockstats_indicators_report = Mock(
        side_effect=mock_get_stockstats_indicators_report
    )
    toolkit.get_stockstats_indicators_report.name = "get_stockstats_indicators_report"
    toolkit.get_stockstats_indicators_report.__name__ = "get_stockstats_indicators_report"
    
    return toolkit


def test_mock_has_name_attribute():
    """Test that mocked functions have __name__ attribute."""
    toolkit = create_mock_toolkit()
    
    # Check get_YFin_data
    assert hasattr(toolkit.get_YFin_data, '__name__'), "get_YFin_data missing __name__"
    assert toolkit.get_YFin_data.__name__ == "get_YFin_data", "get_YFin_data has wrong __name__"
    assert callable(toolkit.get_YFin_data), "get_YFin_data is not callable"
    
    # Check get_stockstats_indicators_report
    assert hasattr(toolkit.get_stockstats_indicators_report, '__name__'), \
        "get_stockstats_indicators_report missing __name__"
    assert toolkit.get_stockstats_indicators_report.__name__ == "get_stockstats_indicators_report", \
        "get_stockstats_indicators_report has wrong __name__"
    assert callable(toolkit.get_stockstats_indicators_report), \
        "get_stockstats_indicators_report is not callable"
    
    print("✓ All mock functions have proper __name__ attributes")
    return True


def test_mock_can_be_used_as_tool():
    """Test that mocked functions can be used as tools."""
    toolkit = create_mock_toolkit()
    
    # Simulate what happens when tools are collected
    tools = [
        toolkit.get_YFin_data,
        toolkit.get_stockstats_indicators_report
    ]
    
    # Check that we can get names from tools
    tool_names = []
    for tool in tools:
        if hasattr(tool, 'name'):
            tool_names.append(tool.name)
        elif hasattr(tool, '__name__'):
            tool_names.append(tool.__name__)
        else:
            raise ValueError(f"Tool {tool} has neither 'name' nor '__name__' attribute")
    
    assert "get_YFin_data" in tool_names, "get_YFin_data not in tool names"
    assert "get_stockstats_indicators_report" in tool_names, \
        "get_stockstats_indicators_report not in tool names"
    
    print(f"✓ Tools can be collected: {tool_names}")
    return True


def test_mock_functions_return_correct_values():
    """Test that mock functions return expected values."""
    toolkit = create_mock_toolkit()
    
    # Test return values
    result1 = toolkit.get_YFin_data()
    assert result1 == "Mock YFin data", f"Unexpected return: {result1}"
    
    result2 = toolkit.get_stockstats_indicators_report()
    assert result2 == "Mock stockstats report", f"Unexpected return: {result2}"
    
    # Test that Mock tracking works
    assert toolkit.get_YFin_data.called, "get_YFin_data not marked as called"
    assert toolkit.get_stockstats_indicators_report.called, \
        "get_stockstats_indicators_report not marked as called"
    
    print("✓ Mock functions return correct values and track calls")
    return True


if __name__ == "__main__":
    print("Testing mock toolkit fixes...")
    print("-" * 40)
    
    tests = [
        test_mock_has_name_attribute,
        test_mock_can_be_used_as_tool,
        test_mock_functions_return_correct_values
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
    
    print("-" * 40)
    if all_passed:
        print("✅ All tests passed! Mock fixes are working correctly.")
    else:
        print("❌ Some tests failed. Check the output above.")