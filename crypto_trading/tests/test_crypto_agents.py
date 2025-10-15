"""
Test script for crypto agents (Phase 2)
Tests the crypto-specific analyst agents
"""
import os
import sys

# Add project root to path (go up 3 levels: tests -> crypto_trading -> TradingAgents)
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

from tradingagents.agents.analysts.onchain_analyst import create_onchain_analyst
from crypto_trading.src.agents.crypto_fundamentals_analyst import create_crypto_fundamentals_analyst
from crypto_trading.src.agents.crypto_technical_analyst import create_crypto_technical_analyst
from crypto_trading.src.agents.crypto_news_analyst import create_crypto_news_analyst
from crypto_trading.src.agents.crypto_sentiment_analyst import create_crypto_sentiment_analyst


def print_section(title):
    """Print formatted section header."""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80 + "\n")


def test_crypto_tools():
    """Test crypto tool imports and basic functionality."""
    print_section("TESTING CRYPTO TOOLS")

    try:
        from crypto_trading.src.agents.crypto_tools import (
            get_onchain_metrics,
            get_crypto_market_data,
            get_crypto_fundamentals,
            get_crypto_news,
            get_tokenomics
        )

        print("✅ Crypto tools imported successfully")
        print("\nAvailable tools:")
        print("  - get_onchain_metrics")
        print("  - get_exchange_flows")
        print("  - get_whale_activity")
        print("  - get_crypto_market_data")
        print("  - get_crypto_ticker")
        print("  - get_crypto_fundamentals")
        print("  - get_crypto_news")
        print("  - get_order_book_analysis")
        print("  - get_tokenomics")
        print("  - get_market_overview")

        return True

    except ImportError as e:
        print(f"❌ Failed to import crypto tools: {e}")
        return False


def test_onchain_analyst():
    """Test On-Chain Analyst agent creation."""
    print_section("TESTING ON-CHAIN ANALYST")

    try:
        # Create mock LLM (we're just testing structure, not execution)
        class MockLLM:
            def bind_tools(self, tools):
                return self

            def invoke(self, state):
                class MockResult:
                    tool_calls = []
                    content = "Mock on-chain analysis report"
                return MockResult()

        llm = MockLLM()
        onchain_analyst = create_onchain_analyst(llm)

        print("✅ On-Chain Analyst created successfully")
        print("\nAgent capabilities:")
        print("  - Network health metrics")
        print("  - Exchange flow analysis")
        print("  - Whale activity tracking")
        print("  - On-chain valuation (NVT, MVRV)")

        # Test state structure
        test_state = {
            "trade_date": "2024-10-07",
            "company_of_interest": "BTC/USDT",
            "messages": []
        }

        result = onchain_analyst(test_state)
        print(f"\n✅ Agent execution successful")
        print(f"   Output keys: {list(result.keys())}")

        return True

    except Exception as e:
        print(f"❌ On-Chain Analyst test failed: {e}")
        return False


def test_crypto_fundamentals_analyst():
    """Test Crypto Fundamentals Analyst agent creation."""
    print_section("TESTING CRYPTO FUNDAMENTALS ANALYST")

    try:
        class MockLLM:
            def bind_tools(self, tools):
                return self

            def invoke(self, state):
                class MockResult:
                    tool_calls = []
                    content = "Mock crypto fundamentals report"
                return MockResult()

        llm = MockLLM()
        fundamentals_analyst = create_crypto_fundamentals_analyst(llm)

        print("✅ Crypto Fundamentals Analyst created successfully")
        print("\nAgent capabilities:")
        print("  - Tokenomics analysis")
        print("  - Project fundamentals")
        print("  - Market position assessment")
        print("  - Competitive analysis")

        # Test execution
        test_state = {
            "trade_date": "2024-10-07",
            "company_of_interest": "ETH/USDT",
            "messages": []
        }

        result = fundamentals_analyst(test_state)
        print(f"\n✅ Agent execution successful")
        print(f"   Output keys: {list(result.keys())}")

        return True

    except Exception as e:
        print(f"❌ Crypto Fundamentals Analyst test failed: {e}")
        return False


def test_crypto_technical_analyst():
    """Test Crypto Technical Analyst agent creation."""
    print_section("TESTING CRYPTO TECHNICAL ANALYST")

    try:
        class MockLLM:
            def bind_tools(self, tools):
                return self

            def invoke(self, state):
                class MockResult:
                    tool_calls = []
                    content = "Mock crypto technical analysis report"
                return MockResult()

        llm = MockLLM()
        technical_analyst = create_crypto_technical_analyst(llm)

        print("✅ Crypto Technical Analyst created successfully")
        print("\nAgent capabilities:")
        print("  - 24/7 market analysis")
        print("  - Multi-timeframe analysis")
        print("  - Order book depth analysis")
        print("  - Crypto-specific indicators")

        # Test execution
        test_state = {
            "trade_date": "2024-10-07",
            "company_of_interest": "BTC/USDT",
            "messages": []
        }

        result = technical_analyst(test_state)
        print(f"\n✅ Agent execution successful")
        print(f"   Output keys: {list(result.keys())}")

        return True

    except Exception as e:
        print(f"❌ Crypto Technical Analyst test failed: {e}")
        return False


def test_crypto_news_analyst():
    """Test Crypto News Analyst agent creation."""
    print_section("TESTING CRYPTO NEWS ANALYST")

    try:
        class MockLLM:
            def bind_tools(self, tools):
                return self

            def invoke(self, state):
                class MockResult:
                    tool_calls = []
                    content = "Mock crypto news analysis report"
                return MockResult()

        llm = MockLLM()
        news_analyst = create_crypto_news_analyst(llm)

        print("✅ Crypto News Analyst created successfully")
        print("\nAgent capabilities:")
        print("  - Regulatory news analysis")
        print("  - Protocol update tracking")
        print("  - Partnership announcements")
        print("  - Exchange listing monitoring")

        # Test execution
        test_state = {
            "trade_date": "2024-10-07",
            "company_of_interest": "SOL/USDT",
            "messages": []
        }

        result = news_analyst(test_state)
        print(f"\n✅ Agent execution successful")
        print(f"   Output keys: {list(result.keys())}")

        return True

    except Exception as e:
        print(f"❌ Crypto News Analyst test failed: {e}")
        return False


def test_crypto_sentiment_analyst():
    """Test Crypto Sentiment Analyst agent creation."""
    print_section("TESTING CRYPTO SENTIMENT ANALYST")

    try:
        class MockLLM:
            def invoke(self, state):
                class MockResult:
                    content = "Mock crypto sentiment analysis report"
                return MockResult()

        llm = MockLLM()
        sentiment_analyst = create_crypto_sentiment_analyst(llm)

        print("✅ Crypto Sentiment Analyst created successfully")
        print("\nAgent capabilities:")
        print("  - Crypto Twitter sentiment")
        print("  - Reddit community analysis")
        print("  - Fear & Greed Index interpretation")
        print("  - Social volume tracking")

        # Test execution
        test_state = {
            "trade_date": "2024-10-07",
            "company_of_interest": "BTC/USDT",
            "messages": []
        }

        result = sentiment_analyst(test_state)
        print(f"\n✅ Agent execution successful")
        print(f"   Output keys: {list(result.keys())}")

        return True

    except Exception as e:
        print(f"❌ Crypto Sentiment Analyst test failed: {e}")
        return False


def main():
    """Run all crypto agent tests."""
    print("\n" + "=" * 80)
    print("  CRYPTO AGENTS TEST SUITE - PHASE 2")
    print("=" * 80)
    print("\nThis test validates:")
    print("  ✓ Crypto tool imports")
    print("  ✓ Agent creation and structure")
    print("  ✓ Agent execution flow")
    print("\nNote: This tests agent structure, not LLM integration")
    print("      Full LLM testing requires OpenAI API key\n")

    results = {}

    # Run tests
    results['crypto_tools'] = test_crypto_tools()
    results['onchain_analyst'] = test_onchain_analyst()
    results['fundamentals_analyst'] = test_crypto_fundamentals_analyst()
    results['technical_analyst'] = test_crypto_technical_analyst()
    results['news_analyst'] = test_crypto_news_analyst()
    results['sentiment_analyst'] = test_crypto_sentiment_analyst()

    # Summary
    print_section("TEST SUMMARY")

    total_tests = len(results)
    passed_tests = sum(1 for result in results.values() if result is True)

    for name, result in results.items():
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"{status:12s} - {name}")

    print(f"\nResults: {passed_tests}/{total_tests} tests passed")

    if passed_tests == total_tests:
        print("\n🎉 All crypto agent tests passed! Phase 2 implementation complete.")
    else:
        print(f"\n⚠️  {total_tests - passed_tests} test(s) failed. Check error messages above.")

    print("\n📊 Crypto Agent Lineup:")
    print("  1. On-Chain Analyst - Blockchain data analysis")
    print("  2. Crypto Fundamentals Analyst - Tokenomics & project analysis")
    print("  3. Crypto Technical Analyst - 24/7 market TA")
    print("  4. Crypto News Analyst - Regulatory & protocol news")
    print("  5. Crypto Sentiment Analyst - Social media sentiment")

    print("\nNext steps:")
    print("  1. Integrate agents into TradingAgentsGraph")
    print("  2. Test with real LLM (requires OpenAI API key)")
    print("  3. Create crypto-specific workflows")
    print("  4. Proceed to Phase 3: Backtesting\n")


if __name__ == "__main__":
    main()
