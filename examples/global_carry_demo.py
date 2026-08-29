"""
Global Investment Committee - End-to-End Demo
==============================================
Demonstrates the complete system:
1. Fetches global interest rates
2. Fetches FX rates
3. Identifies carry trade opportunities
4. Analyzes risk
5. Designs strategy
6. Plans execution

Usage:
    python -m examples.global_carry_demo
    # or
    python examples/global_carry_demo.py
"""

import asyncio
import json
from datetime import datetime
from typing import Dict, List

# Import our new components
from tradingagents.dataflows.providers.interest_rates import GlobalInterestRatesProvider
from tradingagents.dataflows.providers.fx_multi_currency import MultiCurrencyFXProvider
from tradingagents.agents.analysts.carry_trade_analyst import (
    analyze_carry_trade,
    assess_fx_risk,
    design_carry_strategy,
)
from tradingagents.chains.carry_trade_prototypes import GlobalCarryStrategies
from tradingagents.chains.executor import ChainExecutor


def print_header(title: str):
    """Print a formatted header"""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def print_section(title: str):
    """Print a formatted section"""
    print(f"\n--- {title} ---")


def format_rate(country: str, rate: float, currency: str) -> str:
    """Format a rate for display"""
    return f"{country:4s} ({currency}): {rate:6.2f}%"


def main():
    """Main demo function"""
    
    print_header("GLOBAL INVESTMENT COMMITTEE - CARRY TRADE DEMO")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # ============================================================
    # STEP 1: Fetch Global Interest Rates
    # ============================================================
    print_section("STEP 1: Fetching Global Interest Rates")
    
    rates_provider = GlobalInterestRatesProvider()
    
    try:
        all_rates = rates_provider.get_all_rates()
        
        print(f"\nFetched {len(all_rates)} central bank rates:\n")
        
        # Sort by rate (highest first)
        sorted_rates = sorted(all_rates.items(), key=lambda x: x[1].rate, reverse=True)
        
        for country, rate_data in sorted_rates:
            print(format_rate(country, rate_data.rate, rate_data.currency))
        
        # Find highest and lowest
        highest = sorted_rates[0]
        lowest = sorted_rates[-1]
        
        print(f"\nHighest: {highest[0]} at {highest[1].rate}%")
        print(f"Lowest: {lowest[0]} at {lowest[1].rate}%")
        print(f"Maximum spread: {highest[1].rate - lowest[1].rate:.2f}%")
        
    finally:
        rates_provider.close()
    
    # ============================================================
    # STEP 2: Fetch FX Rates
    # ============================================================
    print_section("STEP 2: Fetching FX Rates")
    
    fx_provider = MultiCurrencyFXProvider()
    
    try:
        # Get key FX rates
        key_pairs = [
            ("USD", "EUR"),
            ("USD", "GBP"),
            ("USD", "JPY"),
            ("USD", "BRL"),
            ("USD", "MXN"),
            ("USD", "ARS"),
            ("USD", "INR"),
            ("USD", "CLP"),
            ("USD", "ZAR"),
            ("USD", "TRY"),
        ]
        
        print("\nKey FX Rates:\n")
        
        fx_rates = {}
        for base, quote in key_pairs:
            rate = fx_provider.get_rate(base, quote)
            if rate:
                fx_rates[f"{base}_{quote}"] = rate.rate
                print(f"{base}/{quote}: {rate.rate:.4f} ({rate.source})")
        
        # Get cross rates
        print("\nCross Rates (vs USD):")
        all_fx = fx_provider.get_all_rates("USD")
        print(f"Available currencies: {len(all_fx)}")
        
    finally:
        fx_provider.close()
    
    # ============================================================
    # STEP 3: Identify Carry Trade Opportunities
    # ============================================================
    print_section("STEP 3: Identifying Carry Trade Opportunities")
    
    rates_provider = GlobalInterestRatesProvider()
    
    try:
        opportunities = rates_provider.get_carry_opportunities(min_spread=1.0)
        
        print(f"\nFound {len(opportunities)} opportunities with spread > 1%:\n")
        
        # Show top 10
        for i, opp in enumerate(opportunities[:10], 1):
            print(f"{i:2d}. {opp['funding_currency']} -> {opp['investing_currency']}")
            print(f"    Funding: {opp['funding_rate']:.2f}% | Investing: {opp['investing_rate']:.2f}%")
            print(f"    Spread: {opp['spread']:.2f}%")
            print()
        
    finally:
        rates_provider.close()
    
    # ============================================================
    # STEP 4: Analyze Specific Carry Trade (USD/BRL)
    # ============================================================
    print_section("STEP 4: Analyzing USD/BRL Carry Trade")
    
    # Get current rates
    us_rate = all_rates.get("US")
    br_rate = all_rates.get("BR")
    
    if us_rate and br_rate:
        print(f"\nFunding: USD at {us_rate.rate}%")
        print(f"Investing: BRL at {br_rate.rate}%")
        print(f"Interest Differential: {br_rate.rate - us_rate.rate:.2f}%")
        
        # Get FX volatility
        fx_provider = MultiCurrencyFXProvider()
        try:
            volatility = fx_provider.get_fx_volatility("USD", "BRL", days=30)
            if volatility:
                print(f"30-day FX Volatility: {volatility:.2%}")
                
                # Calculate risk-adjusted return
                interest_diff = br_rate.rate - us_rate.rate
                risk_adjusted = interest_diff - (volatility * 100)
                print(f"Risk-Adjusted Return: {risk_adjusted:.2f}%")
        finally:
            fx_provider.close()
    
    # ============================================================
    # STEP 5: Design Strategy
    # ============================================================
    print_section("STEP 5: Strategy Design (Prototype)")
    
    # Show available strategies
    strategies = GlobalCarryStrategies.get_all_strategies()
    
    print(f"\nAvailable Carry Trade Strategies:\n")
    
    for strategy in strategies:
        print(f"Strategy: {strategy.name}")
        print(f"  Description: {strategy.description}")
        print(f"  Steps: {len(strategy.steps)}")
        print(f"  Veredicto: {strategy.veredicto}")
        print(f"  Reasoning: {strategy.reasoning}")
        print()
    
    # ============================================================
    # STEP 6: Execute in Dry Run Mode
    # ============================================================
    print_section("STEP 6: Dry Run Execution")
    
    # Select a strategy
    usd_brl_strategy = GlobalCarryStrategies.usd_brl_carry(
        investment_amount=100000,
        horizon_months=6,
    )
    
    print(f"\nExecuting strategy: {usd_brl_strategy.name}")
    print(f"Investment: $100,000 USD")
    print(f"Horizon: 6 months")
    print(f"Strategy: {usd_brl_strategy.description}")
    
    # Execute in dry run
    executor = ChainExecutor(dry_run=True)
    
    result = executor.execute_chain(usd_brl_strategy)
    
    print(f"\nExecution Result:")
    print(f"  Status: {result.status}")
    print(f"  Steps Completed: {result.completed_steps}/{result.total_steps}")
    print(f"  Total PnL: ${result.total_pnl:,.2f}")
    print(f"  Duration: {result.execution_time:.2f} seconds")
    
    # ============================================================
    # SUMMARY
    # ============================================================
    print_header("SUMMARY")
    
    print("""
The Global Investment Committee system can:
    
1. Fetch real-time interest rates from 15+ central banks
2. Get FX rates for 30+ currencies
3. Identify carry trade opportunities automatically
4. Analyze risk and volatility
5. Design complete trading strategies
6. Execute in dry run mode (paper trading)

To go live, you need:
- OPENAI_API_KEY (for LLM agents)
- Exchange/Broker API keys (for execution)
- WorldMonitor API key (optional, for macro data)
    """)
    
    print("\n" + "=" * 70)
    print("  Demo complete!")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
