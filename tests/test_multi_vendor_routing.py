"""
Unit tests for multi-vendor routing logic.

These tests use mocked vendor implementations and can run without API keys,
making them suitable for CI/CD environments.

Run with: pytest tests/test_multi_vendor_routing.py -v
"""

import pytest
from unittest.mock import patch, MagicMock
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def mock_vendors():
    """Create mock vendor functions with __name__ attribute."""
    mock_a = MagicMock(return_value="Result from Vendor A")
    mock_a.__name__ = "mock_vendor_a"
    
    mock_b = MagicMock(return_value="Result from Vendor B")
    mock_b.__name__ = "mock_vendor_b"
    
    mock_c = MagicMock(return_value="Result from Vendor C")
    mock_c.__name__ = "mock_vendor_c"
    
    return {'a': mock_a, 'b': mock_b, 'c': mock_c}


@pytest.fixture
def mock_routing(mock_vendors):
    """Set up mocked routing environment."""
    with patch('tradingagents.dataflows.interface.VENDOR_METHODS', {
        'test_method': {
            'vendor_a': mock_vendors['a'],
            'vendor_b': mock_vendors['b'],
            'vendor_c': mock_vendors['c'],
        }
    }), \
    patch('tradingagents.dataflows.interface.get_category_for_method', return_value='test_category'), \
    patch('tradingagents.dataflows.interface.get_config') as mock_config:
        yield mock_config, mock_vendors


def test_single_vendor_stops_after_success(mock_routing):
    """Test that single vendor config stops after first successful vendor."""
    mock_config, mock_vendors = mock_routing
    
    # Configure single vendor
    mock_config.return_value = {
        'data_vendors': {'test_category': 'vendor_a'},
        'tool_vendors': {}
    }
    
    from tradingagents.dataflows.interface import route_to_vendor
    
    result = route_to_vendor('test_method', 'arg1', 'arg2')
    
    # Assertions
    mock_vendors['a'].assert_called_once_with('arg1', 'arg2')
    mock_vendors['b'].assert_not_called()  # Should not try fallback
    mock_vendors['c'].assert_not_called()  # Should not try fallback
    assert result == 'Result from Vendor A'


def test_multi_vendor_stops_after_all_primaries_success(mock_routing):
    """Test that multi-vendor stops after all primaries when they succeed."""
    mock_config, mock_vendors = mock_routing
    
    # Configure two primary vendors
    mock_config.return_value = {
        'data_vendors': {'test_category': 'vendor_a,vendor_b'},
        'tool_vendors': {}
    }
    
    from tradingagents.dataflows.interface import route_to_vendor
    
    result = route_to_vendor('test_method', 'arg1')
    
    # Assertions
    mock_vendors['a'].assert_called_once_with('arg1')
    mock_vendors['b'].assert_called_once_with('arg1')
    mock_vendors['c'].assert_not_called()  # Should NOT try fallback
    
    # Result should contain both
    assert 'Result from Vendor A' in result
    assert 'Result from Vendor B' in result


def test_multi_vendor_stops_after_all_primaries_failure(mock_routing):
    """Test that multi-vendor stops after all primaries even when they fail."""
    mock_config, mock_vendors = mock_routing
    
    # Configure two primary vendors that will fail
    mock_vendors['a'].side_effect = Exception("Vendor A failed")
    mock_vendors['b'].side_effect = Exception("Vendor B failed")
    
    mock_config.return_value = {
        'data_vendors': {'test_category': 'vendor_a,vendor_b'},
        'tool_vendors': {}
    }
    
    from tradingagents.dataflows.interface import route_to_vendor
    
    # Should raise error after trying all primaries
    with pytest.raises(RuntimeError, match="All vendor implementations failed"):
        route_to_vendor('test_method', 'arg1')
    
    # Assertions
    mock_vendors['a'].assert_called_once_with('arg1')
    mock_vendors['b'].assert_called_once_with('arg1')
    mock_vendors['c'].assert_not_called()  # Should NOT try fallback


def test_multi_vendor_partial_failure_stops_after_primaries(mock_routing):
    """Test that multi-vendor stops after all primaries even if one fails."""
    mock_config, mock_vendors = mock_routing
    
    # First vendor fails, second succeeds
    mock_vendors['a'].side_effect = Exception("Vendor A failed")
    
    mock_config.return_value = {
        'data_vendors': {'test_category': 'vendor_a,vendor_b'},
        'tool_vendors': {}
    }
    
    from tradingagents.dataflows.interface import route_to_vendor
    
    result = route_to_vendor('test_method', 'arg1')
    
    # Assertions
    mock_vendors['a'].assert_called_once_with('arg1')
    mock_vendors['b'].assert_called_once_with('arg1')
    mock_vendors['c'].assert_not_called()  # Should NOT try fallback
    
    assert result == 'Result from Vendor B'


def test_single_vendor_uses_fallback_on_failure(mock_routing):
    """Test that single vendor uses fallback if primary fails."""
    mock_config, mock_vendors = mock_routing
    
    # Primary vendor fails
    mock_vendors['a'].side_effect = Exception("Vendor A failed")
    
    mock_config.return_value = {
        'data_vendors': {'test_category': 'vendor_a'},
        'tool_vendors': {}
    }
    
    from tradingagents.dataflows.interface import route_to_vendor
    
    result = route_to_vendor('test_method', 'arg1')
    
    # Assertions
    mock_vendors['a'].assert_called_once_with('arg1')
    mock_vendors['b'].assert_called_once_with('arg1')  # Should try fallback
    assert result == 'Result from Vendor B'


def test_tool_level_override_takes_precedence(mock_routing):
    """Test that tool-level vendor config overrides category-level."""
    mock_config, mock_vendors = mock_routing
    
    # Category says vendor_a, but tool override says vendor_b
    mock_config.return_value = {
        'data_vendors': {'test_category': 'vendor_a'},
        'tool_vendors': {'test_method': 'vendor_b'}
    }
    
    from tradingagents.dataflows.interface import route_to_vendor
    
    result = route_to_vendor('test_method', 'arg1')
    
    # Assertions
    mock_vendors['a'].assert_not_called()  # Category default ignored
    mock_vendors['b'].assert_called_once_with('arg1')  # Tool override used
    assert result == 'Result from Vendor B'

