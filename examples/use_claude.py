#!/usr/bin/env python3
"""
Example: Using Claude (Anthropic) instead of OpenAI with TradingAgents

This example shows how to configure TradingAgents to use Claude models
for superior reasoning and analysis.

Setup:
1. Get your Anthropic API key from: https://console.anthropic.com/
2. Add to .env file: ANTHROPIC_API_KEY=your_key_here
3. Run this script!
"""

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.llm_factory import LLMFactory
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

def main():
    print("\n" + "="*70)
    print("🤖 Using Claude (Anthropic) with TradingAgents")
    print("="*70 + "\n")

    # Check if Anthropic is configured
    print("1️⃣  Validating Anthropic Setup...")
    validation = LLMFactory.validate_provider_setup("anthropic")

    if not validation["valid"]:
        print("❌ Anthropic is not properly configured:")
        for error in validation["errors"]:
            print(f"   • {error}")
        print("\nSetup instructions:")
        print("   1. Get API key: https://console.anthropic.com/")
        print("   2. Add to .env: ANTHROPIC_API_KEY=your_key_here")
        print("   3. Install package: pip install langchain-anthropic")
        return

    print("✅ Anthropic is configured!")
    print(f"   • Package installed: {validation['package_installed']}")
    print(f"   • API key set: {validation['api_key_set']}")

    # Show recommended models
    print("\n2️⃣  Recommended Claude Models:")
    models = LLMFactory.get_recommended_models("anthropic")
    for use_case, model in models.items():
        print(f"   • {use_case:15} → {model}")

    # Configure TradingAgents to use Claude
    print("\n3️⃣  Configuring TradingAgents with Claude...")
    config = DEFAULT_CONFIG.copy()
    config["llm_provider"] = "anthropic"

    # Use Claude 3.5 Sonnet (best model as of Nov 2024)
    config["deep_think_llm"] = "claude-3-5-sonnet-20241022"
    config["quick_think_llm"] = "claude-3-5-sonnet-20241022"

    # Optional: adjust debate rounds for faster response
    config["max_debate_rounds"] = 1
    config["max_risk_discuss_rounds"] = 1

    print(f"✅ Using Claude 3.5 Sonnet for both deep and quick thinking")

    # Create TradingAgents graph
    print("\n4️⃣  Initializing TradingAgents...")
    try:
        ta = TradingAgentsGraph(
            selected_analysts=["market", "fundamentals"],  # Start simple
            config=config,
            debug=False
        )
        print("✅ TradingAgents initialized with Claude!")

        # Run analysis
        print("\n5️⃣  Running Analysis on NVDA...")
        print("   (This will use Claude's superior reasoning...)\n")

        _, decision = ta.propagate("NVDA", "2024-05-10")

        print("\n" + "="*70)
        print("📊 ANALYSIS RESULTS (Powered by Claude)")
        print("="*70)
        print(f"\nDecision: {decision}")
        print("\n✅ Analysis complete!")
        print("\nClaude's advantages:")
        print("   • Superior reasoning capabilities")
        print("   • Better at nuanced financial analysis")
        print("   • More reliable and consistent outputs")
        print("   • Competitive pricing")

    except Exception as e:
        print(f"❌ Error: {e}")
        print("\nTroubleshooting:")
        print("   • Ensure ANTHROPIC_API_KEY is set in .env")
        print("   • Check internet connection")
        print("   • Verify API key is valid")

    print("\n" + "="*70)
    print("💡 TIP: Claude 3.5 Sonnet is excellent for financial analysis!")
    print("="*70 + "\n")


def compare_providers():
    """Quick comparison of available providers."""
    print("\n" + "="*70)
    print("📊 LLM Provider Comparison")
    print("="*70 + "\n")

    providers = ["openai", "anthropic", "google"]

    for provider in providers:
        print(f"\n{provider.upper()}:")
        validation = LLMFactory.validate_provider_setup(provider)
        status = "✅ Ready" if validation["valid"] else "❌ Not configured"
        print(f"   Status: {status}")

        if validation["valid"]:
            models = LLMFactory.get_recommended_models(provider)
            print(f"   Best model: {models['deep_thinking']}")


if __name__ == "__main__":
    main()

    # Uncomment to see provider comparison
    # compare_providers()
