"""
Test script for crypto data infrastructure (Phase 1)
Validates CCXT, Glassnode, and Messari integrations
"""
import os
import sys
from datetime import datetime, timedelta

# Add project root to path (go up 3 levels: tests -> crypto_trading -> TradingAgents)
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

from tradingagents.dataflows.ccxt_vendor import (
    CCXTVendor,
    get_crypto_ohlcv,
    get_crypto_ticker,
    get_crypto_order_book,
    get_crypto_fundamentals
)
from tradingagents.dataflows.glassnode_vendor import (
    GlassnodeVendor,
    get_onchain_metrics,
    get_exchange_flow_analysis,
    get_whale_activity
)
from tradingagents.dataflows.messari_vendor import (
    MessariVendor,
    get_crypto_fundamentals_messari,
    get_crypto_news_messari,
    get_crypto_market_overview,
    get_tokenomics_analysis
)


def print_section(title):
    """Print formatted section header."""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80 + "\n")


def test_ccxt():
    """Test CCXT integration for crypto market data."""
    print_section("TESTING CCXT - Multi-Exchange Crypto Data")

    try:
        # Test 1: OHLCV Data
        print("Test 1: Fetching BTC/USDT OHLCV data from Binance...")
        result = get_crypto_ohlcv(
            symbol="BTC/USDT",
            timeframe="1d",
            limit=7,
            exchange="binance"
        )
        print(result[:500])  # Print first 500 chars
        print("✅ CCXT OHLCV test passed\n")

        # Test 2: Ticker
        print("Test 2: Fetching ETH/USDT ticker...")
        ticker = get_crypto_ticker("ETH/USDT", "binance")
        print(ticker[:300])
        print("✅ CCXT Ticker test passed\n")

        # Test 3: Order Book
        print("Test 3: Fetching order book...")
        order_book = get_crypto_order_book("BTC/USDT", limit=10, exchange="binance")
        print(order_book[:400])
        print("✅ CCXT Order Book test passed\n")

        # Test 4: Fundamentals (exchange-level)
        print("Test 4: Fetching crypto fundamentals...")
        fundamentals = get_crypto_fundamentals("BTC/USDT", "binance")
        print(fundamentals[:400])
        print("✅ CCXT Fundamentals test passed\n")

        return True

    except Exception as e:
        print(f"❌ CCXT test failed: {e}")
        return False


def test_glassnode():
    """Test Glassnode integration for on-chain metrics."""
    print_section("TESTING GLASSNODE - On-Chain Analytics")

    # Check if API key is set
    api_key = os.getenv("GLASSNODE_API_KEY", "")
    if not api_key or api_key == "glassnode_api_key_placeholder":
        print("⚠️  GLASSNODE_API_KEY not set in environment")
        print("   Skipping Glassnode tests (requires paid API key)")
        print("   Set GLASSNODE_API_KEY to enable on-chain analytics\n")
        return None

    try:
        # Test 1: On-chain metrics
        print("Test 1: Fetching on-chain metrics for BTC...")
        metrics = get_onchain_metrics("BTC", days=7)
        print(metrics[:500])
        print("✅ Glassnode on-chain metrics test passed\n")

        # Test 2: Exchange flows
        print("Test 2: Analyzing exchange flows...")
        flows = get_exchange_flow_analysis("BTC", days=7)
        print(flows[:400])
        print("✅ Glassnode exchange flows test passed\n")

        # Test 3: Whale activity
        print("Test 3: Analyzing whale activity...")
        whales = get_whale_activity("BTC", days=7)
        print(whales[:400])
        print("✅ Glassnode whale activity test passed\n")

        return True

    except Exception as e:
        print(f"❌ Glassnode test failed: {e}")
        print("   Note: Glassnode requires a paid API key")
        return False


def test_messari():
    """Test Messari integration for crypto fundamentals."""
    print_section("TESTING MESSARI - Crypto Fundamentals & News")

    try:
        # Test 1: Crypto fundamentals
        print("Test 1: Fetching Bitcoin fundamentals...")
        fundamentals = get_crypto_fundamentals_messari("bitcoin")
        print(fundamentals[:600])
        print("✅ Messari fundamentals test passed\n")

        # Test 2: Crypto news
        print("Test 2: Fetching crypto news...")
        news = get_crypto_news_messari("bitcoin", limit=3)
        print(news[:500])
        print("✅ Messari news test passed\n")

        # Test 3: Market overview
        print("Test 3: Fetching market overview...")
        overview = get_crypto_market_overview(limit=5)
        print(overview[:500])
        print("✅ Messari market overview test passed\n")

        # Test 4: Tokenomics
        print("Test 4: Analyzing tokenomics...")
        tokenomics = get_tokenomics_analysis("ethereum")
        print(tokenomics[:500])
        print("✅ Messari tokenomics test passed\n")

        return True

    except Exception as e:
        print(f"❌ Messari test failed: {e}")
        print("   Note: Some features may require Messari API key")
        return False


def test_ccxt_object_oriented():
    """Test CCXT vendor using object-oriented interface."""
    print_section("TESTING CCXT - Object-Oriented Interface")

    try:
        vendor = CCXTVendor(exchange_id="binance")

        print("Test: Fetching markets list...")
        markets = vendor.get_markets()
        print(f"Available markets: {len(markets)}")
        print(f"Sample markets: {markets[:5]}")
        print("✅ CCXT OOP test passed\n")

        return True

    except Exception as e:
        print(f"❌ CCXT OOP test failed: {e}")
        return False


def main():
    """Run all crypto data tests."""
    print("\n" + "=" * 80)
    print("  CRYPTO DATA INFRASTRUCTURE TEST SUITE - PHASE 1")
    print("=" * 80)
    print("\nThis test validates:")
    print("  ✓ CCXT integration (multi-exchange data)")
    print("  ✓ Glassnode integration (on-chain metrics)")
    print("  ✓ Messari integration (fundamentals & news)")
    print("\nNote: CCXT works without API keys (public data)")
    print("      Glassnode requires API key (optional)")
    print("      Messari works without API key (limited data)\n")

    results = {}

    # Run tests
    results['ccxt'] = test_ccxt()
    results['ccxt_oop'] = test_ccxt_object_oriented()
    results['messari'] = test_messari()
    results['glassnode'] = test_glassnode()

    # Summary
    print_section("TEST SUMMARY")

    total_tests = len([r for r in results.values() if r is not None])
    passed_tests = len([r for r in results.values() if r is True])

    for name, result in results.items():
        if result is True:
            print(f"✅ {name.upper()}: PASSED")
        elif result is False:
            print(f"❌ {name.upper()}: FAILED")
        else:
            print(f"⚠️  {name.upper()}: SKIPPED (API key required)")

    print(f"\nResults: {passed_tests}/{total_tests} tests passed")

    if passed_tests == total_tests:
        print("\n🎉 All crypto data tests passed! Phase 1 implementation complete.")
    elif passed_tests > 0:
        print(f"\n✅ {passed_tests} core tests passed. Optional features require API keys.")
    else:
        print("\n❌ Tests failed. Check your internet connection and dependencies.")

    print("\nNext steps:")
    print("  1. Install dependencies: pip install -r requirements.txt")
    print("  2. Set API keys in .env file (optional)")
    print("  3. Run: python test_crypto_data.py")
    print("  4. Proceed to Phase 2: Agent Adaptation\n")


if __name__ == "__main__":
    main()
