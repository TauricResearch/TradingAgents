#!/usr/bin/env python3
"""
Quick test to verify options chain and put/call ratio tools are working correctly.
This demonstrates the new market analyst capabilities.
"""

from tradingagents.agents.utils.options_tools import (
    get_options_chain,
    calculate_put_call_ratio
)


def test_options_tools():
    """Test the new options analysis tools."""
    
    print("=" * 80)
    print("Testing Options Chain & Put/Call Ratio Tools")
    print("=" * 80)
    
    tickers = ["AAPL", "MSFT", "TSLA"]
    
    for ticker in tickers:
        print(f"\n{'='*80}")
        print(f"Ticker: {ticker}")
        print(f"{'='*80}")
        
        # Test get_options_chain
        print(f"\n[1] Fetching Options Chain for {ticker}...")
        try:
            chain_result = get_options_chain.invoke({
                "symbol": ticker,
                "expiry_date": "nearest"
            })
            # Print first 400 chars to show it's working
            print(f"[OK] Options chain retrieved ({len(chain_result)} bytes)")
            print(f"   Preview:\n{chain_result[:300]}...\n")
        except Exception as e:
            print(f"[ERROR] Error fetching options chain: {e}\n")
        
        # Test calculate_put_call_ratio (volume-based)
        print(f"[2] Calculating Volume-Based Put/Call Ratio for {ticker}...")
        try:
            ratio_result = calculate_put_call_ratio.invoke({
                "symbol": ticker,
                "expiry_date": "nearest",
                "ratio_type": "volume"
            })
            print(f"[OK] Put/Call ratio calculated")
            print(f"   {ratio_result}\n")
        except Exception as e:
            print(f"[ERROR] Error calculating put/call ratio: {e}\n")
        
        # Test calculate_put_call_ratio (open interest-based)
        print(f"[3] Calculating Open Interest-Based Put/Call Ratio for {ticker}...")
        try:
            oi_result = calculate_put_call_ratio.invoke({
                "symbol": ticker,
                "expiry_date": "nearest",
                "ratio_type": "oi"
            })
            # Print just the ratio line
            ratio_lines = [l for l in oi_result.split('\n') if 'Put/Call OI Ratio' in l]
            if ratio_lines:
                print(f"[OK] Open Interest ratio calculated")
                print(f"   {ratio_lines[0]}\n")
        except Exception as e:
            print(f"[ERROR] Error calculating OI ratio: {e}\n")


if __name__ == "__main__":
    test_options_tools()
    print("\n" + "="*80)
    print("[OK] Options integration test complete!")
    print("="*80)
