"""
Example: How to integrate crypto agents into TradingAgentsGraph
Demonstrates crypto agent usage with the framework
"""
import os
import sys

# Add project root to path (go up 3 levels: examples -> crypto_trading -> TradingAgents)
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

from langchain_openai import ChatOpenAI
from tradingagents.agents.analysts.onchain_analyst import create_onchain_analyst
from crypto_trading.src.agents.crypto_fundamentals_analyst import create_crypto_fundamentals_analyst
from crypto_trading.src.agents.crypto_technical_analyst import create_crypto_technical_analyst
from crypto_trading.src.agents.crypto_news_analyst import create_crypto_news_analyst
from crypto_trading.src.agents.crypto_sentiment_analyst import create_crypto_sentiment_analyst
from tradingagents.crypto_config import get_crypto_config
from tradingagents.dataflows.config import set_config


def example_create_crypto_agents():
    """Example 1: Create crypto analyst agents."""
    print("\n" + "=" * 80)
    print("EXAMPLE 1: Creating Crypto Agents")
    print("=" * 80 + "\n")

    # Initialize LLM
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

    # Create crypto-specific agents
    onchain_analyst = create_onchain_analyst(llm)
    fundamentals_analyst = create_crypto_fundamentals_analyst(llm)
    technical_analyst = create_crypto_technical_analyst(llm)
    news_analyst = create_crypto_news_analyst(llm)
    sentiment_analyst = create_crypto_sentiment_analyst(llm)

    print("✅ Created 5 crypto-specific agents:")
    print("   1. On-Chain Analyst - Blockchain metrics")
    print("   2. Fundamentals Analyst - Tokenomics")
    print("   3. Technical Analyst - 24/7 market analysis")
    print("   4. News Analyst - Crypto news")
    print("   5. Sentiment Analyst - Social media\n")

    return {
        'onchain': onchain_analyst,
        'fundamentals': fundamentals_analyst,
        'technical': technical_analyst,
        'news': news_analyst,
        'sentiment': sentiment_analyst
    }


def example_analyze_bitcoin():
    """Example 2: Analyze Bitcoin using crypto agents."""
    print("\n" + "=" * 80)
    print("EXAMPLE 2: Bitcoin Analysis with Crypto Agents")
    print("=" * 80 + "\n")

    # Set up crypto config
    crypto_config = get_crypto_config()
    set_config(crypto_config)
    print("✅ Crypto configuration activated\n")

    # Create state for Bitcoin analysis
    state = {
        "trade_date": "2024-10-07",
        "company_of_interest": "BTC/USDT",
        "messages": []
    }

    print(f"Analyzing: {state['company_of_interest']}")
    print(f"Date: {state['trade_date']}\n")

    # Initialize LLM
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

    # Run each analyst
    print("Running crypto analysts...\n")

    # 1. On-Chain Analysis
    print("1. On-Chain Analyst - Analyzing blockchain metrics...")
    onchain_analyst = create_onchain_analyst(llm)
    # Note: Would call onchain_analyst(state) here with real API keys

    # 2. Fundamentals Analysis
    print("2. Fundamentals Analyst - Analyzing tokenomics...")
    fundamentals_analyst = create_crypto_fundamentals_analyst(llm)
    # Note: Would call fundamentals_analyst(state) here

    # 3. Technical Analysis
    print("3. Technical Analyst - Analyzing price action...")
    technical_analyst = create_crypto_technical_analyst(llm)
    # Note: Would call technical_analyst(state) here

    # 4. News Analysis
    print("4. News Analyst - Analyzing recent news...")
    news_analyst = create_crypto_news_analyst(llm)
    # Note: Would call news_analyst(state) here

    # 5. Sentiment Analysis
    print("5. Sentiment Analyst - Analyzing social sentiment...")
    sentiment_analyst = create_crypto_sentiment_analyst(llm)
    # Note: Would call sentiment_analyst(state) here

    print("\n✅ All analysts configured. Ready to execute with real data.")
    print("\nTo run with real data:")
    print("  1. Set OPENAI_API_KEY in .env")
    print("  2. Set GLASSNODE_API_KEY for on-chain data (optional)")
    print("  3. Run agents with state dictionary")


def example_crypto_vs_stock_config():
    """Example 3: Compare crypto vs stock configurations."""
    print("\n" + "=" * 80)
    print("EXAMPLE 3: Crypto vs Stock Configuration")
    print("=" * 80 + "\n")

    from tradingagents.default_config import DEFAULT_CONFIG
    from tradingagents.crypto_config import get_crypto_config

    # Stock config
    print("STOCK CONFIGURATION:")
    print(f"  Data Vendors: {DEFAULT_CONFIG['data_vendors']}")
    print(f"  Max Position: {DEFAULT_CONFIG.get('max_position_size', 'N/A')}")
    print(f"  Trading Hours: {DEFAULT_CONFIG.get('trading_hours', '9:30-16:00')}")

    # Crypto config
    crypto_config = get_crypto_config()
    print("\nCRYPTO CONFIGURATION:")
    print(f"  Data Vendors: {crypto_config['data_vendors']}")
    print(f"  Max Position: {crypto_config['max_position_size']}")
    print(f"  Trading Hours: {crypto_config['trading_hours']}")
    print(f"  Risk Multiplier: {crypto_config['risk_multiplier']}x")

    print("\nKey Differences:")
    print("  ✓ Crypto uses CCXT, Messari, Glassnode")
    print("  ✓ Crypto has 3x risk multiplier (higher volatility)")
    print("  ✓ Crypto trades 24/7 (vs market hours)")
    print("  ✓ Crypto has tier-based position limits")


def example_multi_crypto_analysis():
    """Example 4: Analyze multiple cryptocurrencies."""
    print("\n" + "=" * 80)
    print("EXAMPLE 4: Multi-Crypto Analysis")
    print("=" * 80 + "\n")

    # Set crypto config
    crypto_config = get_crypto_config()
    set_config(crypto_config)

    # Define crypto assets to analyze
    crypto_assets = [
        ("BTC/USDT", "Bitcoin - Digital Gold"),
        ("ETH/USDT", "Ethereum - Smart Contract Platform"),
        ("SOL/USDT", "Solana - High-Performance L1"),
    ]

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

    print("Analyzing multiple cryptocurrencies:\n")

    for symbol, description in crypto_assets:
        print(f"📊 {symbol} - {description}")

        state = {
            "trade_date": "2024-10-07",
            "company_of_interest": symbol,
            "messages": []
        }

        # Create analysts for this asset
        technical_analyst = create_crypto_technical_analyst(llm)
        fundamentals_analyst = create_crypto_fundamentals_analyst(llm)

        print(f"   ✓ Technical Analyst ready")
        print(f"   ✓ Fundamentals Analyst ready")
        print(f"   (Execute with: analyst(state))\n")

    print("✅ Multi-crypto analysis framework ready")


def example_agent_prompts():
    """Example 5: View agent system prompts."""
    print("\n" + "=" * 80)
    print("EXAMPLE 5: Agent Specializations")
    print("=" * 80 + "\n")

    print("🔗 ON-CHAIN ANALYST")
    print("   Focus: Blockchain-level data")
    print("   Tools: get_onchain_metrics, get_exchange_flows, get_whale_activity")
    print("   Output: Network health, exchange flows, whale movements\n")

    print("💰 CRYPTO FUNDAMENTALS ANALYST")
    print("   Focus: Tokenomics and project analysis")
    print("   Tools: get_crypto_fundamentals, get_tokenomics, get_market_overview")
    print("   Output: Supply dynamics, inflation, utility, competitive position\n")

    print("📈 CRYPTO TECHNICAL ANALYST")
    print("   Focus: 24/7 price action and order books")
    print("   Tools: get_crypto_market_data, get_crypto_ticker, get_order_book_analysis")
    print("   Output: Multi-timeframe TA, support/resistance, entry/exit zones\n")

    print("📰 CRYPTO NEWS ANALYST")
    print("   Focus: Regulatory and protocol news")
    print("   Tools: get_crypto_news")
    print("   Output: News sentiment, regulatory impact, market implications\n")

    print("😊 CRYPTO SENTIMENT ANALYST")
    print("   Focus: Social media and Fear & Greed")
    print("   Tools: (Framework mode - requires social media API integration)")
    print("   Output: Twitter/Reddit sentiment, contrarian signals\n")


def main():
    """Run all examples."""
    print("\n" + "=" * 80)
    print("  CRYPTO AGENT INTEGRATION EXAMPLES")
    print("=" * 80)
    print("\nDemonstrates how to use crypto-specific agents in TradingAgents.\n")

    try:
        # Run examples
        example_create_crypto_agents()
        example_analyze_bitcoin()
        example_crypto_vs_stock_config()
        example_multi_crypto_analysis()
        example_agent_prompts()

        # Summary
        print("\n" + "=" * 80)
        print("  EXAMPLES COMPLETE")
        print("=" * 80)
        print("\n✅ All examples executed successfully!")
        print("\nQuick Start:")
        print("  1. Set crypto config: set_config(get_crypto_config())")
        print("  2. Create agents with LLM")
        print("  3. Define state with ticker and date")
        print("  4. Execute: result = analyst(state)")
        print("\nNext Steps:")
        print("  - Integrate into TradingAgentsGraph workflow")
        print("  - Test with real OpenAI API key")
        print("  - Add agent routing logic for crypto vs stock\n")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("   Make sure dependencies are installed")


if __name__ == "__main__":
    main()
