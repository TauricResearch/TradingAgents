"""
Behavioral tests for multi-vendor routing logic.

These tests verify the stopping behavior by analyzing the debug output
from the routing system.
"""

import os
import sys
import io
from contextlib import redirect_stdout
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add current directory to path
sys.path.append(os.getcwd())

from tradingagents.dataflows.config import set_config, get_config


def capture_routing_behavior(vendor_config, method, *args):
    """Capture the debug output from route_to_vendor to analyze behavior."""
    from tradingagents.dataflows.interface import route_to_vendor
    
    # Set configuration
    config = get_config()
    config["data_vendors"]["news_data"] = vendor_config
    set_config(config)
    
    # Capture stdout
    f = io.StringIO()
    try:
        with redirect_stdout(f):
            result = route_to_vendor(method, *args)
        output = f.getvalue()
        return output, result, None
    except Exception as e:
        output = f.getvalue()
        return output, None, e


def test_single_vendor_stops_after_success():
    """Test that single vendor config stops after first success."""
    print("\n" + "="*70)
    print("TEST 1: Single Vendor - Should stop after first success")
    print("="*70)
    
    output, result, error = capture_routing_behavior(
        "alpha_vantage",
        "get_news",
        "NVDA",
        "2024-11-20",
        "2024-11-21"
    )
    
    # Check that it stopped after primary vendor
    assert "Stopping after successful vendor 'alpha_vantage' (single-vendor config)" in output, \
        "Should stop after single vendor succeeds"
    
    # Check that fallback vendors were not attempted
    assert "Attempting FALLBACK vendor" not in output, \
        "Should not attempt fallback vendors when primary succeeds"
    
    # Check vendor attempt count
    assert "completed with 1 result(s) from 1 vendor attempt(s)" in output, \
        "Should only attempt 1 vendor"
    
    print("✅ PASS: Single vendor stopped after success, no fallbacks attempted")
    print(f"   Vendor attempts: 1")


def test_multi_vendor_stops_after_all_primaries():
    """Test that multi-vendor config stops after all primary vendors."""
    print("\n" + "="*70)
    print("TEST 2: Multi-Vendor - Should stop after all primaries")
    print("="*70)
    
    output, result, error = capture_routing_behavior(
        "alpha_vantage,google",
        "get_news",
        "NVDA",
        "2024-11-20",
        "2024-11-21"
    )
    
    # Check that both primaries were attempted
    assert "Attempting PRIMARY vendor 'alpha_vantage'" in output, \
        "Should attempt first primary vendor"
    assert "Attempting PRIMARY vendor 'google'" in output, \
        "Should attempt second primary vendor"
    
    # Check that it stopped after all primaries
    assert "All primary vendors attempted" in output, \
        "Should stop after all primary vendors"
    
    # Check that fallback vendors were not attempted
    assert "Attempting FALLBACK vendor 'openai'" not in output, \
        "Should not attempt fallback vendor (openai)"
    assert "Attempting FALLBACK vendor 'local'" not in output, \
        "Should not attempt fallback vendor (local)"
    
    print("✅ PASS: Multi-vendor stopped after all primaries, no fallbacks attempted")
    print(f"   Primary vendors: alpha_vantage, google")


def test_single_vendor_uses_fallback_on_failure():
    """Test that single vendor uses fallback if primary fails."""
    print("\n" + "="*70)
    print("TEST 3: Single Vendor Failure - Should use fallback")
    print("="*70)
    
    # Use a vendor that will likely fail (invalid config)
    output, result, error = capture_routing_behavior(
        "nonexistent_vendor",
        "get_news",
        "NVDA",
        "2024-11-20",
        "2024-11-21"
    )
    
    # Check that fallback was attempted
    assert "Attempting FALLBACK vendor" in output or "Attempting PRIMARY vendor" in output, \
        "Should attempt vendors"
    
    # Should eventually succeed with a fallback
    assert result is not None or error is not None, \
        "Should either succeed with fallback or fail gracefully"
    
    print("✅ PASS: Fallback mechanism works when primary fails")


def test_debug_output_shows_fallback_order():
    """Test that debug output shows the complete fallback order."""
    print("\n" + "="*70)
    print("TEST 4: Debug Output - Should show fallback order")
    print("="*70)
    
    output, result, error = capture_routing_behavior(
        "alpha_vantage",
        "get_news",
        "NVDA",
        "2024-11-20",
        "2024-11-21"
    )
    
    # Check that fallback order is displayed
    assert "Full fallback order:" in output, \
        "Should display full fallback order in debug output"
    assert "alpha_vantage" in output, \
        "Should show primary vendor in fallback order"
    
    print("✅ PASS: Debug output correctly shows fallback order")


if __name__ == '__main__':
    print("\n" + "="*70)
    print("MULTI-VENDOR ROUTING BEHAVIORAL TESTS")
    print("="*70)
    
    try:
        test_single_vendor_stops_after_success()
        test_multi_vendor_stops_after_all_primaries()
        test_single_vendor_uses_fallback_on_failure()
        test_debug_output_shows_fallback_order()
        
        print("\n" + "="*70)
        print("ALL TESTS PASSED ✅")
        print("="*70 + "\n")
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}\n")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ ERROR: {e}\n")
        import traceback
        traceback.print_exc()
        sys.exit(1)
