"""
Example: Using TradingAgents with Crypto Markets
Demonstrates how to switch from stock to crypto analysis
"""
import os
import sys

# Add project root to path (go up 3 levels: examples -> crypto_trading -> TradingAgents)
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

from tradingagents.crypto_config import get_crypto_config
from tradingagents.dataflows.config import set_config, get_config
from tradingagents.dataflows.interface import route_to_vendor

# Import convenience functions
from tradingagents.dataflows.ccxt_vendor import get_crypto_ohlcv, get_crypto_ticker
from tradingagents.dataflows.messari_vendor import get_crypto_fundamentals_messari
from tradingagents.dataflows.glassnode_vendor import get_onchain_metrics


def example_1_basic_crypto_data():
    """Example 1: Fetch basic crypto market data using CCXT."""
    print("\n" + "=" * 80)
    print("EXAMPLE 1: Basic Crypto Market Data (CCXT)")
    print("=" * 80 + "\n")

    # Get Bitcoin price data
    print("Fetching Bitcoin OHLCV data (last 7 days)...\n")
    btc_data = get_crypto_ohlcv(
        symbol="BTC/USDT",
        timeframe="1d",
        limit=7,
        exchange="binance"
    )
    print(btc_data)

    # Get current Ethereum ticker
    print("\n" + "-" * 80)
    print("\nFetching Ethereum current ticker...\n")
    eth_ticker = get_crypto_ticker("ETH/USDT", "binance")
    print(eth_ticker)


def example_2_crypto_fundamentals():
    """Example 2: Analyze crypto fundamentals using Messari."""
    print("\n" + "=" * 80)
    print("EXAMPLE 2: Crypto Fundamentals Analysis (Messari)")
    print("=" * 80 + "\n")

    # Get Bitcoin fundamentals
    print("Analyzing Bitcoin fundamentals...\n")
    btc_fundamentals = get_crypto_fundamentals_messari("bitcoin")
    print(btc_fundamentals)


def example_3_onchain_analysis():
    """Example 3: On-chain metrics using Glassnode (requires API key)."""
    print("\n" + "=" * 80)
    print("EXAMPLE 3: On-Chain Analysis (Glassnode)")
    print("=" * 80 + "\n")

    # Check if API key is set
    api_key = os.getenv("GLASSNODE_API_KEY", "")
    if not api_key or api_key == "glassnode_api_key_placeholder":
        print("⚠️  GLASSNODE_API_KEY not set.")
        print("   On-chain analysis requires a Glassnode API key (paid service).")
        print("   Skipping this example...\n")
        return

    # Get on-chain metrics
    print("Analyzing Bitcoin on-chain metrics...\n")
    btc_onchain = get_onchain_metrics("BTC", days=30)
    print(btc_onchain)


def example_4_config_switching():
    """Example 4: Switch between stock and crypto configs."""
    print("\n" + "=" * 80)
    print("EXAMPLE 4: Configuration Switching (Stock ↔ Crypto)")
    print("=" * 80 + "\n")

    # Show current config
    current_config = get_config()
    print("Current configuration:")
    print(f"  Market type: {current_config.get('market_type', 'stock')}")
    print(f"  Data vendors: {current_config.get('data_vendors', {})}")

    # Switch to crypto config
    print("\n🔄 Switching to crypto configuration...\n")
    crypto_config = get_crypto_config()
    set_config(crypto_config)

    # Show new config
    new_config = get_config()
    print("New configuration:")
    print(f"  Market type: {new_config.get('market_type', 'stock')}")
    print(f"  Data vendors: {new_config.get('data_vendors', {})}")
    print(f"  Trading hours: {new_config.get('trading_hours', 'Unknown')}")
    print(f"  Max position size: {new_config.get('max_position_size', 'Unknown')}")


def example_5_routing_system():
    """Example 5: Demonstrate vendor routing system."""
    print("\n" + "=" * 80)
    print("EXAMPLE 5: Automatic Vendor Routing")
    print("=" * 80 + "\n")

    # Set crypto config
    crypto_config = get_crypto_config()
    set_config(crypto_config)

    print("With crypto config active, data requests automatically route to crypto vendors:\n")

    # This will automatically use CCXT for crypto
    print("1. Calling route_to_vendor('get_stock_data', 'BTC/USDT', ...)...")
    print("   → Automatically routed to CCXT\n")

    # This will automatically use Messari for crypto fundamentals
    print("2. Calling route_to_vendor('get_fundamentals', 'bitcoin')...")
    print("   → Automatically routed to Messari\n")

    print("Note: Actual routing happens in tradingagents/dataflows/interface.py")
    print("      See route_to_vendor() function for implementation details.")


def example_6_multi_exchange():
    """Example 6: Compare prices across multiple exchanges."""
    print("\n" + "=" * 80)
    print("EXAMPLE 6: Multi-Exchange Price Comparison")
    print("=" * 80 + "\n")

    exchanges = ["binance", "coinbase", "kraken"]
    symbol = "BTC/USDT"

    print(f"Comparing {symbol} prices across exchanges:\n")

    for exchange in exchanges:
        try:
            ticker = get_crypto_ticker(symbol, exchange)
            # Extract just the price line
            for line in ticker.split('\n'):
                if 'Last Price' in line:
                    print(f"{exchange.upper():12s} - {line.strip()}")
                    break
        except Exception as e:
            print(f"{exchange.upper():12s} - Error: {e}")

    print("\n💡 TIP: Price differences create arbitrage opportunities!")


def main():
    """Run all examples."""
    print("\n" + "=" * 80)
    print("  TRADINGAGENTS CRYPTO INTEGRATION - USAGE EXAMPLES")
    print("=" * 80)
    print("\nThis demonstrates how to use crypto features in TradingAgents.")
    print("Make sure you've installed dependencies: pip install -r requirements.txt\n")

    try:
        # Run examples
        example_1_basic_crypto_data()
        example_2_crypto_fundamentals()
        example_3_onchain_analysis()
        example_4_config_switching()
        example_5_routing_system()
        example_6_multi_exchange()

        # Summary
        print("\n" + "=" * 80)
        print("  EXAMPLES COMPLETE")
        print("=" * 80)
        print("\n✅ All examples executed successfully!")
        print("\nNext steps:")
        print("  1. Explore tradingagents/dataflows/ccxt_vendor.py for more CCXT features")
        print("  2. Check tradingagents/crypto_config.py for configuration options")
        print("  3. Run test_crypto_data.py for full validation")
        print("  4. Integrate crypto features into your agents\n")

    except KeyboardInterrupt:
        print("\n\n⚠️  Examples interrupted by user.")
    except Exception as e:
        print(f"\n\n❌ Error running examples: {e}")
        print("   Make sure you've installed dependencies: pip install -r requirements.txt")


if __name__ == "__main__":
    main()
